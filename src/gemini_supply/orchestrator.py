from __future__ import annotations

import asyncio
import os
import textwrap
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from enum import Enum
from typing import Literal, Protocol, Sequence

import termcolor

from gemini_supply.agent import BrowserAgent, LoopStatus
from gemini_supply.auth import AuthManager
from gemini_supply.computers import AuthExpiredError, CamoufoxHost, build_camoufox_options
from gemini_supply.config import (
  AppConfig,
  HomeAssistantShoppingListConfig,
  PreferencesConfig,
  ShoppingListConfig,
  YAMLShoppingListConfig,
)
from gemini_supply.grocery import (
  HomeAssistantShoppingListProvider,
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingListProvider,
  YAMLShoppingListProvider,
)
from gemini_supply.log import TTYLogger
from gemini_supply.models import (
  AddedOutcome,
  FailedOutcome,
  NotFoundOutcome,
  Outcome,
  ShoppingResults,
  ShoppingSession,
  ShoppingSettings,
)
from gemini_supply.preferences import (
  DEFAULT_NAG_STRINGS,
  DEFAULT_NORMALIZER_MODEL,
  NormalizationAgent,
  NormalizedItem,
  PreferenceCoordinator,
  PreferenceItemSession,
  PreferenceRecord,
  PreferenceStore,
  TelegramPreferenceMessenger,
  TelegramSettings,
)
from gemini_supply.profile import resolve_camoufox_exec, resolve_profile_dir


@dataclass(slots=True)
class PreferenceResources:
  coordinator: PreferenceCoordinator
  messenger: TelegramPreferenceMessenger | None = None

  async def stop(self) -> None:
    if self.coordinator is not None:
      await self.coordinator.stop()


class AuthEnsurer(Protocol):
  async def ensure_authenticated(self, *, force: bool = False) -> None: ...


class OrchestrationStage(Enum):
  PRE_SHOP_AUTH = "pre_shop_auth"
  SHOPPING = "shopping"


class OrchestrationState:
  """Tracks orchestration stage and gates pre-shop authentication."""

  __slots__ = ("_stage", "_lock")

  def __init__(self) -> None:
    self._stage = OrchestrationStage.PRE_SHOP_AUTH
    self._lock = asyncio.Lock()

  @property
  def stage(self) -> OrchestrationStage:
    return self._stage

  async def ensure_pre_shop_auth(self, auth_manager: AuthEnsurer, *, force: bool = False) -> None:
    async with self._lock:
      if self._stage is OrchestrationStage.SHOPPING and not force:
        return
      await auth_manager.ensure_authenticated(force=force)
      self._stage = OrchestrationStage.SHOPPING


async def run_shopping(
  *,
  list_path: Path | None,
  settings: ShoppingSettings,
  no_retry: bool = False,
  config: AppConfig,
) -> int:
  provider = _build_provider(list_path, config.shopping_list, no_retry)
  logger = TTYLogger()
  preferences = await _setup_preferences(config.preferences)

  try:
    results = await _run_shopping_flow(provider, settings, logger, preferences)
  finally:
    await preferences.stop()

  provider.send_summary(results.to_summary())
  return 0


def _build_provider(
  list_path: Path | None, config: ShoppingListConfig, no_retry: bool
) -> ShoppingListProvider:
  if isinstance(config, HomeAssistantShoppingListConfig):
    return HomeAssistantShoppingListProvider(
      ha_url=config.url, token=config.token, no_retry=no_retry
    )

  if isinstance(config, YAMLShoppingListConfig):
    path = list_path or config.path
    if path is None:
      raise ValueError("A shopping list path must be provided for the YAML provider")
    return YAMLShoppingListProvider(path=path)

  raise ValueError("Unsupported shopping list configuration")


async def _setup_preferences(pref_cfg: PreferencesConfig) -> PreferenceResources:
  pref_path = pref_cfg.file
  store = PreferenceStore(pref_path)
  normalizer = NormalizationAgent(
    model_name=pref_cfg.normalizer_model or DEFAULT_NORMALIZER_MODEL,
    base_url=pref_cfg.normalizer_api_base_url,
    api_key=pref_cfg.normalizer_api_key,
  )
  messenger: TelegramPreferenceMessenger | None = None
  tel_cfg = pref_cfg.telegram
  messenger = TelegramPreferenceMessenger(
    settings=TelegramSettings(
      bot_token=tel_cfg.bot_token,
      chat_id=tel_cfg.chat_id,
      nag_interval=timedelta(minutes=tel_cfg.nag_minutes),
    ),
    nag_strings=DEFAULT_NAG_STRINGS,
  )

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

  termcolor.cprint(
    f"Loaded shopping list with {len(items)} item{'s' if len(items) != 1 else ''}:",
    color="magenta",
  )
  for entry in items:
    termcolor.cprint(
      f"  • {entry.name} (id={entry.id}, status={entry.status.value})",
      color="magenta",
    )

  effective_concurrency = settings.concurrency.resolve(len(items))
  termcolor.cprint(f"Resolved concurrency: {effective_concurrency}", color="cyan")

  env_h = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()
  if env_h in ("virtual", "v"):
    headless_mode: bool | Literal["virtual"] = "virtual"
  elif env_h in ("0", "false", "no"):
    headless_mode = False
  elif env_h:
    headless_mode = True
  else:
    headless_mode = "virtual"

  termcolor.cprint(
    f"Resolved headless mode: {'virtual' if headless_mode == 'virtual' else 'headed' if headless_mode is False else 'headless'}",
    color="cyan",
  )

  async with CamoufoxHost(
    screen_size=settings.screen_size,
    user_data_dir=profile_dir,
    initial_url="https://www.metro.ca",
    highlight_mouse=True,
    enforce_restrictions=True,
    executable_path=camoufox_exec,
    headless=headless_mode,
    camoufox_options=build_camoufox_options(),
  ) as host:
    auth_manager = AuthManager(host)
    state = OrchestrationState()
    await state.ensure_pre_shop_auth(auth_manager, force=True)
    if effective_concurrency <= 1:
      return await _run_sequential(
        host=host,
        items=items,
        provider=provider,
        settings=settings,
        logger=logger,
        preferences=preferences,
        auth_manager=auth_manager,
        state=state,
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
      state=state,
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
  state: OrchestrationState,
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
        state=state,
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
  state: OrchestrationState,
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
          state=state,
        )
        collected.append((item, outcome))
      except Exception as exc:  # noqa: BLE001
        await _handle_processing_exception(item, exc, provider)
        collected.append((item, FailedOutcome(error=str(exc))))

  async with asyncio.TaskGroup() as tg:
    for shopping_item in items:
      await asyncio.sleep(0.8)
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
  state: OrchestrationState,
) -> Outcome:
  existing_preference: PreferenceRecord | None = None
  specific_request = False
  await state.ensure_pre_shop_auth(auth_manager)

  normalized = await preferences.coordinator.normalize_item(item.name)
  preference_session = preferences.coordinator.create_session(normalized)
  specific_request = _is_specific_request(normalized)
  if not specific_request:
    existing_preference = await preference_session.existing_preference()

  try:
    return await _shop_single_item_in_tab(
      host=host,
      item=item,
      shopping_list_provider=provider,
      model_name=settings.model_name,
      time_budget=settings.time_budget,
      max_turns=settings.max_turns,
      logger=logger,
      preference_session=preference_session,
      existing_preference=existing_preference,
      specific_request=specific_request,
      auth_manager=auth_manager,
    )
  except Exception as exc:  # noqa: BLE001
    await _handle_processing_exception(item, exc, provider)
    return FailedOutcome(error=str(exc))


async def _handle_processing_exception(
  item: ShoppingListItem, exc: Exception, provider: ShoppingListProvider
) -> None:
  import sys
  import traceback

  tb = traceback.format_exc()
  termcolor.cprint("Exception while shopping item:", color="red")
  print(tb, file=sys.stderr)
  provider.mark_failed(item.id, f"exception: {exc}\n{tb}")


def _is_specific_request(normalized: NormalizedItem) -> bool:
  if normalized.brand:
    return True
  return any(qualifier.strip() for qualifier in normalized.qualifiers)


def _build_task_prompt(
  item_name: str,
  normalized: NormalizedItem,
  preference: PreferenceRecord | None,
  specific_request: bool,
) -> str:
  # Build conditional sections
  return "".join(
    [
      f"Detected brand: {normalized.brand}\n" if normalized.brand else "",
      f"Qualifiers: {', '.join(normalized.qualifiers)}\n" if normalized.qualifiers else "",
      "Specific request detected; ignore previously stored defaults.\n\n"
      if specific_request
      else "",
      textwrap.dedent(f"""
      Known preference available:
      - Product: {preference.product_name}
      - URL: {preference.product_url}
      Always prioritise this product unless it is unavailable or clearly incorrect.

      """)
      if preference
      else "",
      textwrap.dedent("""
      Instructions:

      1. Use metro.ca to find the product.
      2. Prefer using navigate to open the search results page (SRP) directly:
        https://www.metro.ca/en/online-grocery/search?filter={{ENCODED_QUERY}}
        Otherwise, use the header search input present on all pages.
      3. From the SRP, choose the best-matching result. CLICK THE PRODUCT IMAGE or name to open the product's page.
      4. On the product page, press 'Add to Cart'.
        If the "Delivery or Pickup?" form appears, click the "I haven't made my choice yet" link at the bottom to defer selection, then press 'Add to Cart' again on the product page.
      5. Verify success: The 'Add to Cart' button becomes a quantity control (with +/−).
        If it does not change, try again or explain why it failed.
      6. Call report_item_added(item_name, price_text, url, quantity) when successful.
        The 'url' MUST be the product page URL (NOT the search results page).
      7. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).
      8. When you cannot confidently pick a product, call request_product_choice with up to 10 promising SRP results.
        Include title, price_text (currency string), and the product URL for each option.
        Wait for the response before continuing.

      Constraints:
        - Stay on metro.ca and allowed resources only.
        - Do NOT navigate to checkout, payment, or account pages.
        - Focus solely on adding the requested item.
  """),
    ]
  )


async def _shop_single_item_in_tab(
  *,
  host: CamoufoxHost,
  item: ShoppingListItem,
  shopping_list_provider: ShoppingListProvider,
  model_name: str,
  time_budget: timedelta,
  max_turns: int,
  logger: TTYLogger,
  preference_session: PreferenceItemSession,
  existing_preference: PreferenceRecord | None = None,
  specific_request: bool = False,
  auth_manager: AuthManager,
) -> Outcome:
  termcolor.cprint(f"🛒 (tab) Shopping for: {item.name}", color="cyan")
  normalized = preference_session.normalized
  prompt = _build_task_prompt(
    item.name,
    normalized,
    existing_preference,
    specific_request,
  )
  max_attempts = 2
  for attempt in range(1, max_attempts + 1):
    needs_retry = False
    tab = await host.new_tab()
    termcolor.cprint(
      f"[agent] Launching browser agent for '{item.name}' (attempt {attempt}/{max_attempts}).",
      color="blue",
    )
    agent: BrowserAgent | None = None
    start = time.monotonic()
    budget_seconds = time_budget.total_seconds()
    turns = 0
    try:
      session = ShoppingSession(
        item=item,
        provider=shopping_list_provider,
        preference_session=preference_session,
      )
      agent = BrowserAgent(
        browser_computer=tab,
        query=prompt,
        model_name=model_name,
        logger=logger,
        output_label=item.name,
        custom_tools=[
          session.report_item_added,
          session.report_item_not_found,
          session.request_product_choice,
        ],
      )
      status: LoopStatus = LoopStatus.CONTINUE
      while status == LoopStatus.CONTINUE:
        turns += 1
        if turns > max_turns:
          shopping_list_provider.mark_failed(item.id, f"max_turns_exceeded: {max_turns}")
          termcolor.cprint("Max turns exceeded; marking failed.", color="yellow")
          return FailedOutcome(error=f"max_turns_exceeded: {max_turns}")

        if time.monotonic() - start > budget_seconds:
          shopping_list_provider.mark_failed(item.id, f"time_budget_exceeded: {time_budget}")
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

        if session.result is not None:
          result = session.result
          if isinstance(result, ItemAddedResult):
            default_used = (
              preference_session.has_existing_preference and not preference_session.prompted_user
            )
            starred_default = preference_session.make_default_pending
            return AddedOutcome(
              result=result,
              used_default=default_used,
              starred_default=starred_default,
            )
          if isinstance(result, ItemNotFoundResult):
            return NotFoundOutcome(result=result)

      if not needs_retry:
        shopping_list_provider.mark_failed(item.id, "completed_without_reporting")
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
        shopping_list_provider.mark_failed(item.id, f"auth_recovery_failed: {auth_exc}")
        termcolor.cprint(
          f"Authentication recovery failed ({auth_exc}); giving up on item.",
          color="red",
        )
        return FailedOutcome(error=f"auth_recovery_failed: {auth_exc}")
      continue

  shopping_list_provider.mark_failed(item.id, "auth_recovery_failed")
  termcolor.cprint(
    "Authentication recovery exhausted; marking item as failed.",
    color="red",
  )
  return FailedOutcome(error="auth_recovery_failed")
