from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import timedelta
from typing import Literal, Sequence

import termcolor

from gemini_supply.agent import BrowserAgent
from gemini_supply.auth import AuthManager, build_camoufox_options
from gemini_supply.computers import AuthExpiredError, CamoufoxHost
from gemini_supply.config import DEFAULT_CONFIG_PATH, AppConfig, PreferencesConfig, load_config
from gemini_supply.grocery import (
  HomeAssistantShoppingListProvider,
  ShoppingListProvider,
  YAMLShoppingListProvider,
)
from gemini_supply.grocery.types import ShoppingListItem
from gemini_supply.preferences.constants import DEFAULT_NAG_STRINGS, DEFAULT_NORMALIZER_MODEL
from gemini_supply.preferences.messenger import TelegramPreferenceMessenger, TelegramSettings
from gemini_supply.preferences.normalizer import NormalizationAgent
from gemini_supply.preferences.service import PreferenceCoordinator, PreferenceItemSession
from gemini_supply.preferences.store import PreferenceStore
from gemini_supply.preferences.types import NormalizedItem, PreferenceRecord
from gemini_supply.profile import resolve_camoufox_exec, resolve_profile_dir
from gemini_supply.log import TTYLogger
from gemini_supply.shopping.models import (
  AddedOutcome,
  FailedOutcome,
  LoopStatus,
  NotFoundOutcome,
  Outcome,
  ShoppingResults,
  ShoppingSettings,
)


@dataclass(slots=True)
class PreferenceResources:
  coordinator: PreferenceCoordinator | None = None
  messenger: TelegramPreferenceMessenger | None = None

  async def stop(self) -> None:
    if self.coordinator is not None:
      await self.coordinator.stop()


async def run_shopping(
  *,
  list_path: Path | None,
  settings: ShoppingSettings,
  no_retry: bool = False,
  config: AppConfig | None = None,
  config_path: Path | None = None,
) -> int:
  config_obj = config if config is not None else load_config(config_path or DEFAULT_CONFIG_PATH)
  provider = _build_provider(list_path, config_obj, no_retry)
  logger = TTYLogger()
  preferences = await _setup_preferences(config_obj.preferences if config_obj else None)

  try:
    results = await _run_shopping_flow(provider, settings, logger, preferences)
  finally:
    await preferences.stop()

  provider.send_summary(results.to_summary())
  return 0


def _build_provider(
  list_path: Path | None, config: AppConfig | None, no_retry: bool
) -> ShoppingListProvider:
  if (
    config is not None
    and config.shopping_list is not None
    and config.shopping_list.provider == "home_assistant"
  ):
    ha = config.home_assistant
    if ha is None or not ha.url or not ha.token:
      raise ValueError("home_assistant.url and home_assistant.token are required in config")
    return HomeAssistantShoppingListProvider(ha_url=ha.url, token=ha.token, no_retry=no_retry)

  if list_path is None:
    raise ValueError("--shopping-list is required for YAML provider")
  return YAMLShoppingListProvider(path=list_path)


async def _setup_preferences(pref_cfg: PreferencesConfig | None) -> PreferenceResources:
  if pref_cfg is None:
    return PreferenceResources()

  pref_path = Path(pref_cfg.file or "~/.config/gemini-supply/preferences.yaml").expanduser()
  store = PreferenceStore(pref_path)
  normalizer = NormalizationAgent(
    model_name=pref_cfg.normalizer_model or DEFAULT_NORMALIZER_MODEL,
    base_url=pref_cfg.normalizer_api_base_url,
    api_key=pref_cfg.normalizer_api_key,
  )
  messenger: TelegramPreferenceMessenger | None = None
  tel_cfg = pref_cfg.telegram
  if tel_cfg is not None and tel_cfg.bot_token and tel_cfg.chat_id is not None:
    nag_minutes = tel_cfg.nag_minutes or 30
    settings = TelegramSettings(
      bot_token=tel_cfg.bot_token,
      chat_id=tel_cfg.chat_id,
      nag_interval=timedelta(minutes=nag_minutes),
    )
    messenger = TelegramPreferenceMessenger(settings=settings, nag_strings=DEFAULT_NAG_STRINGS)

  coordinator = PreferenceCoordinator(
    normalizer=normalizer,
    store=store,
    messenger=messenger,
  )
  await coordinator.start()
  return PreferenceResources(coordinator=coordinator, messenger=messenger)


async def _run_shopping_flow(
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: TTYLogger,
  preferences: PreferenceResources,
) -> ShoppingResults:
  profile_dir = resolve_profile_dir()
  termcolor.cprint(f"Using profile: {profile_dir}", color="cyan")
  camoufox_exec = resolve_camoufox_exec()

  items = provider.get_uncompleted_items()
  if not items:
    termcolor.cprint("No uncompleted items found.", color="yellow")
    return ShoppingResults()

  effective_concurrency = settings.concurrency.resolve(items, provider)

  env_h = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()
  if env_h in ("virtual", "v"):
    headless_mode: bool | Literal["virtual"] = "virtual"
  elif env_h in ("0", "false", "no"):
    headless_mode = False
  elif env_h:
    headless_mode = True
  else:
    headless_mode = "virtual"

  async with CamoufoxHost(
    screen_size=settings.screen_size,
    user_data_dir=profile_dir,
    initial_url="https://www.metro.ca",
    highlight_mouse=settings.highlight_mouse,
    enforce_restrictions=True,
    executable_path=camoufox_exec,
    headless=headless_mode,
    camoufox_options=build_camoufox_options(),
  ) as host:
    auth_manager = AuthManager(host)
    await auth_manager.ensure_authenticated(force=True)
    if effective_concurrency <= 1:
      return await _run_sequential(
        host=host,
        items=items,
        provider=provider,
        settings=settings,
        logger=logger,
        preferences=preferences,
        auth_manager=auth_manager,
      )
    return await _run_concurrent(
      host=host,
      items=items,
      provider=provider,
      settings=settings,
      logger=logger,
      preferences=preferences,
      concurrency=effective_concurrency,
      auth_manager=auth_manager,
    )


async def _run_sequential(
  *,
  host: CamoufoxHost,
  items: Sequence[ShoppingListItem],
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: TTYLogger,
  preferences: PreferenceResources,
  auth_manager: AuthManager,
) -> ShoppingResults:
  results = ShoppingResults()
  for item in items:
    try:
      outcome = await _process_item(
        host=host,
        item=item,
        provider=provider,
        settings=settings,
        logger=logger,
        preferences=preferences,
        auth_manager=auth_manager,
      )
    except Exception as exc:  # noqa: BLE001
      await _handle_processing_exception(item, exc, provider)
      outcome = FailedOutcome(error=str(exc))
    results.record(outcome)
  return results


async def _run_concurrent(
  *,
  host: CamoufoxHost,
  items: Sequence[ShoppingListItem],
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: TTYLogger,
  preferences: PreferenceResources,
  concurrency: int,
  auth_manager: AuthManager,
) -> ShoppingResults:
  results = ShoppingResults()
  sem = asyncio.Semaphore(concurrency)
  collected: list[tuple[ShoppingListItem, Outcome]] = []

  async def run_one(item: ShoppingListItem) -> None:
    async with sem:
      try:
        outcome = await _process_item(
          host=host,
          item=item,
          provider=provider,
          settings=settings,
          logger=logger,
          preferences=preferences,
          auth_manager=auth_manager,
        )
        collected.append((item, outcome))
      except Exception as exc:  # noqa: BLE001
        await _handle_processing_exception(item, exc, provider)
        collected.append((item, FailedOutcome(error=str(exc))))

  async with asyncio.TaskGroup() as tg:
    for shopping_item in items:
      tg.create_task(run_one(shopping_item))

  for _, outcome in collected:
    results.record(outcome)

  return results


async def _process_item(
  *,
  host: CamoufoxHost,
  item: ShoppingListItem,
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: TTYLogger,
  preferences: PreferenceResources,
  auth_manager: AuthManager,
) -> Outcome:
  preference_session: PreferenceItemSession | None = None
  existing_preference: PreferenceRecord | None = None
  await auth_manager.ensure_authenticated()
  if preferences.coordinator is not None:
    normalized = await preferences.coordinator.normalize_item(item["name"])
    preference_session = preferences.coordinator.create_session(normalized)
    existing_preference = await preference_session.existing_preference()

  try:
    return await _shop_single_item_in_tab(
      host=host,
      item=item,
      provider=provider,
      model_name=settings.model_name,
      highlight_mouse=settings.highlight_mouse,
      time_budget=settings.time_budget,
      max_turns=settings.max_turns,
      postal_code=settings.postal_code,
      logger=logger,
      preference_session=preference_session,
      existing_preference=existing_preference,
      auth_manager=auth_manager,
    )
  except Exception as exc:  # noqa: BLE001
    await _handle_processing_exception(item, exc, provider)
    return FailedOutcome(error=str(exc))


async def _handle_processing_exception(
  item: ShoppingListItem, exc: Exception, provider: ShoppingListProvider
) -> None:
  import traceback
  import sys

  tb = traceback.format_exc()
  termcolor.cprint("Exception while shopping item:", color="red")
  print(tb, file=sys.stderr)
  provider.mark_failed(item["id"], f"exception: {exc}\n{tb}")


def _build_task_prompt(
  item_name: str,
  postal_code: str,
  normalized: NormalizedItem | None,
  preference: PreferenceRecord | None,
  can_request_choice: bool,
) -> str:
  normalized_lines: list[str] = []
  if normalized is not None:
    normalized_lines.append(
      f"Normalized category: {normalized['category_label']} (key: {normalized['canonical_key']})"
    )
    if normalized.get("brand"):
      normalized_lines.append(f"Detected brand: {normalized['brand']}")
    normalized_lines.append(f"Original text: {normalized['original_text']}")
    normalized_lines.append("")
  preference_lines: list[str] = []
  if preference is not None:
    preference_lines.append("Known preference available:")
    preference_lines.append(f"  - Product: {preference.product_name}")
    preference_lines.append(f"  - URL: {preference.product_url}")
    preference_lines.append(
      "  Always prioritise this product unless it is unavailable or clearly incorrect."
    )
    preference_lines.append("")
  instructions = [
    "Instructions:",
    "  1. Use metro.ca to find the product.",
    "  2. Prefer using navigate to open the search results page (SRP) directly: ",
    "     https://www.metro.ca/en/online-grocery/search?filter={ENCODED_QUERY}",
    "     Otherwise, use the header search input present on all pages.",
    "  3. From the SRP, choose the best-matching result. CLICK THE PRODUCT IMAGE or name to open the product's page.",
    "  4. On the product page, press 'Add to Cart'. If a postal code form appears, enter the postal code exactly as:",
    f"     {postal_code}",
    '     If the "Delivery or Pickup?" form appears, click the "I haven\'t made my choice yet" link at the bottom to defer selection, then press \'Add to Cart\' again on the product page.',
    "  5. Verify success: The 'Add to Cart' button becomes a quantity control (with +/−).",
    "     If it does not change, try again or explain why it failed.",
    "  6. Call report_item_added(item_name, price_text, price_cents, url, quantity) when successful.",
    "     The 'url' MUST be the product page URL (NOT the search results page).",
    "  7. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).",
  ]
  if can_request_choice:
    instructions.append(
      "  8. When you cannot confidently pick a product, call request_preference_choice with up to 10 promising SRP results (include titles and product URLs). Wait for the response before continuing."
    )
  instructions_text = "\n".join(instructions) + "\n\n"
  header = f"Goal: Add ONE specific item to metro.ca cart\nItem: {item_name}\n\n"
  constraints = (
    "Constraints:\n"
    "  - Stay on metro.ca and allowed resources only.\n"
    "  - Do NOT navigate to checkout, payment, or account pages.\n"
    "  - Focus solely on adding the requested item.\n"
  )
  return (
    header
    + "\n".join(normalized_lines)
    + "".join(preference_lines)
    + instructions_text
    + constraints
  )


async def _shop_single_item_in_tab(
  *,
  host: CamoufoxHost,
  item: ShoppingListItem,
  provider: ShoppingListProvider,
  model_name: str,
  highlight_mouse: bool,
  time_budget: timedelta,
  max_turns: int,
  postal_code: str,
  logger: TTYLogger | None = None,
  preference_session: PreferenceItemSession | None = None,
  existing_preference: PreferenceRecord | None = None,
  auth_manager: AuthManager,
) -> Outcome:
  termcolor.cprint(f"🛒 (tab) Shopping for: {item['name']}", color="cyan")
  normalized = preference_session.normalized if preference_session is not None else None
  can_request_choice = (
    preference_session.can_request_choice if preference_session is not None else False
  )
  prompt = _build_task_prompt(
    item["name"], postal_code, normalized, existing_preference, can_request_choice
  )
  max_attempts = 2
  for attempt in range(1, max_attempts + 1):
    needs_retry = False
    tab = await host.new_tab()
    agent: BrowserAgent | None = None
    start = time.monotonic()
    budget_seconds = time_budget.total_seconds()
    turns = 0
    try:
      agent = BrowserAgent(
        browser_computer=tab,
        query=prompt,
        model_name=model_name,
        logger=logger,
        output_label=item["name"],
        preference_session=preference_session,
      )
      status: LoopStatus = LoopStatus.CONTINUE
      while status == LoopStatus.CONTINUE:
        turns += 1
        if turns > max_turns:
          provider.mark_failed(item["id"], f"max_turns_exceeded: {max_turns}")
          termcolor.cprint("Max turns exceeded; marking failed.", color="yellow")
          return FailedOutcome(error=f"max_turns_exceeded: {max_turns}")

        if time.monotonic() - start > budget_seconds:
          provider.mark_failed(item["id"], f"time_budget_exceeded: {time_budget}")
          termcolor.cprint("Time budget exceeded; marking failed.", color="yellow")
          return FailedOutcome(error=f"time_budget_exceeded: {time_budget}")

        try:
          res = await agent.run_one_iteration()
          status = LoopStatus(res)
        except AuthExpiredError:
          needs_retry = True
          termcolor.cprint(
            f"Authentication expired during attempt {attempt}; scheduling re-auth.",
            color="yellow",
          )
          break

        if agent.last_custom_tool_call is not None:
          name = agent.last_custom_tool_call["name"]
          payload = agent.last_custom_tool_call["payload"]
          if name == "request_preference_choice":
            agent.last_custom_tool_call = None
            continue
          if name == "report_item_added":
            provider.mark_completed(item["id"], payload)  # type: ignore[arg-type]
            if preference_session is not None:
              await preference_session.record_success(payload)  # type: ignore[arg-type]
            return AddedOutcome(result=payload)  # type: ignore[arg-type]
          if name == "report_item_not_found":
            provider.mark_not_found(item["id"], payload)  # type: ignore[arg-type]
            return NotFoundOutcome(result=payload)  # type: ignore[arg-type]
          provider.mark_failed(item["id"], f"unexpected_custom_tool: {name}")
          return FailedOutcome(error=f"unexpected_custom_tool: {name}")

      if not needs_retry:
        provider.mark_failed(item["id"], "completed_without_reporting")
        return FailedOutcome(error="completed_without_reporting")
    finally:
      try:
        await tab.close()
      except Exception:
        pass
      if agent is not None:
        agent.close()
    if needs_retry:
      termcolor.cprint(
        "Authentication refreshed; retrying item from the beginning.",
        color="yellow",
      )
      try:
        await auth_manager.ensure_authenticated()
      except Exception as auth_exc:  # noqa: BLE001
        provider.mark_failed(item["id"], f"auth_recovery_failed: {auth_exc}")
        termcolor.cprint(
          f"Authentication recovery failed ({auth_exc}); giving up on item.",
          color="red",
        )
        return FailedOutcome(error=f"auth_recovery_failed: {auth_exc}")
      continue

  provider.mark_failed(item["id"], "auth_recovery_failed")
  termcolor.cprint(
    "Authentication recovery exhausted; marking item as failed.",
    color="red",
  )
  return FailedOutcome(error="auth_recovery_failed")
