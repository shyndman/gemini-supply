from __future__ import annotations

import asyncio
import textwrap
import time
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from importlib.resources import files
from typing import Mapping, Protocol, Sequence
from urllib.parse import urlparse

import playwright
import playwright.async_api

from generative_supply.agent import BrowserAgent, LoopStatus
from generative_supply.auth import AuthManager
from generative_supply.computers import AuthExpiredError, CamoufoxHost, build_camoufox_options
from generative_supply.config import (
  AppConfig,
  HomeAssistantShoppingListConfig,
  PreferencesConfig,
  ShoppingListConfig,
  YAMLShoppingListConfig,
)
from generative_supply.grocery import (
  HomeAssistantShoppingListProvider,
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingListProvider,
  YAMLShoppingListProvider,
)
from generative_supply.models import (
  AddedOutcome,
  FailedOutcome,
  NotFoundOutcome,
  Outcome,
  ShoppingResults,
  ShoppingSession,
  ShoppingSettings,
)
from generative_supply.preferences import (
  DEFAULT_NAG_STRINGS,
  NormalizationAgent,
  NormalizedItem,
  OverrideRequest,
  PreferenceCoordinator,
  PreferenceItemSession,
  PreferenceRecord,
  PreferenceStore,
  TelegramPreferenceMessenger,
  TelegramSettings,
)
from generative_supply.profile import resolve_camoufox_exec, resolve_profile_dir
from generative_supply.prompt import build_shopper_prompt
from generative_supply.term import ActivityLog, activity_log, set_activity_log

DEMO_WINDOW_POSITION = (8126, 430)


@dataclass(slots=True)
class PreferenceResources:
  coordinator: PreferenceCoordinator
  messenger: TelegramPreferenceMessenger | None = None

  async def stop(self) -> None:
    if self.coordinator is not None:
      await self.coordinator.stop()


class AuthEnsurer(Protocol):
  async def ensure_authenticated(self) -> None: ...


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

  async def ensure_pre_shop_auth(self, auth_manager: AuthEnsurer) -> None:
    async with self._lock:
      activity_log().stage.debug(f"acquired auth gate (stage={self._stage.value})")
      if self._stage is OrchestrationStage.SHOPPING:
        activity_log().stage.important("skipping auth; already shopping.")
        return
      await auth_manager.ensure_authenticated()
      self._stage = OrchestrationStage.SHOPPING
      activity_log().stage.success("promoted stage to shopping.")


async def run_shopping(
  *,
  settings: ShoppingSettings,
  no_retry: bool = False,
  config: AppConfig,
) -> int:
  provider = _build_provider(config.shopping_list, no_retry)
  logger = ActivityLog()
  set_activity_log(logger)  # Set up context for all child calls
  preferences = await _setup_preferences(config.preferences)

  try:
    results = await _run_shopping_flow(provider, settings, logger, preferences)
  finally:
    await preferences.stop()

  await provider.send_summary(results.to_summary())
  return 0


def _build_provider(config: ShoppingListConfig, no_retry: bool) -> ShoppingListProvider:
  if isinstance(config, HomeAssistantShoppingListConfig):
    return HomeAssistantShoppingListProvider(config=config, no_retry=no_retry)

  if isinstance(config, YAMLShoppingListConfig):
    path = config.path
    if path is None:
      raise ValueError("A shopping list path must be provided for the YAML provider")
    return YAMLShoppingListProvider(path=path)

  raise ValueError("Unsupported shopping list configuration")


async def _setup_preferences(pref_cfg: PreferencesConfig) -> PreferenceResources:
  pref_path = pref_cfg.file
  store = PreferenceStore(pref_path)
  # Short rationale: we rely on the baked-in Gemini normalizer to keep behavior consistent.
  normalizer = NormalizationAgent()
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


def load_init_scripts():
  return [
    files("generative_supply.page").joinpath("srp.js").read_text(encoding="utf-8"),
  ]


async def _denature_search_results_page(page: playwright.async_api.Page) -> None:
  url = page.url
  parsed = urlparse(url)

  activity_log().denature.trace(f"{url}")
  if parsed.path != "/en/online-grocery/search":
    return

  activity_log().denature.operation("On search results page")

  # Check for and click any visible overlay close buttons
  close_buttons = page.locator("a.close-overlay-box")
  count = await close_buttons.count()
  activity_log().denature.operation(f"Found {count} overlay close button(s), clicking...")
  for i in range(count):
    button = close_buttons.nth(i)
    if await button.is_visible():
      await button.click()
      activity_log().denature.success(f"Clicked overlay close button {i + 1}/{count}")

  # Replace all a.product-details-link with span elements
  product_links = page.locator("a.product-details-link")
  link_count = await product_links.count()
  if link_count > 0:
    activity_log().denature.operation(f"Replacing {link_count} product link(s) with spans...")
    await page.evaluate("""(() => {
      const links = document.querySelectorAll('a.product-details-link');
      links.forEach(link => {
        const span = document.createElement('span');
        span.className = link.className;
        span.innerHTML = link.innerHTML;
        Array.from(link.attributes).forEach(attr => {
          if (attr.name !== 'href') {
            span.setAttribute(attr.name, attr.value);
          }
        });
        link.parentNode.replaceChild(span, link);
      });
    })()""")
    activity_log().denature.success(f"Replaced {link_count} product links with spans")


async def _run_shopping_flow(
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: ActivityLog,
  preferences: PreferenceResources,
) -> ShoppingResults:
  profile_dir = resolve_profile_dir()
  activity_log().operation(f"Using profile: {profile_dir}")
  camoufox_exec = resolve_camoufox_exec()

  items = await provider.get_uncompleted_items()
  if not items:
    activity_log().warning("No uncompleted items found.")
    return ShoppingResults()

  activity_log().important(
    f"Loaded shopping list with {len(items)} item{'s' if len(items) != 1 else ''}:"
  )
  for entry in items:
    activity_log().important(f"  • {entry.name} (id={entry.id}, status={entry.status.value})")

  effective_concurrency = settings.concurrency.resolve(len(items))
  activity_log().operation(f"Resolved concurrency: {effective_concurrency}")

  agent_labels = {item.id: f"agent-{idx + 1}" for idx, item in enumerate(items)}
  activity_log().stage.starting(f"Initialized orchestration state with {len(agent_labels)} agents.")

  async with CamoufoxHost(
    screen_size=settings.screen_size,
    user_data_dir=profile_dir,
    initial_url="https://www.metro.ca",
    init_scripts=load_init_scripts(),
    pre_iteration_delegate=_denature_search_results_page,
    highlight_mouse=True,
    enforce_restrictions=True,
    executable_path=camoufox_exec,
    camoufox_options=build_camoufox_options(),
    window_position=DEMO_WINDOW_POSITION,
  ) as host:
    auth_manager = AuthManager(host)
    state = OrchestrationState()
    await state.ensure_pre_shop_auth(auth_manager)
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
        agent_labels=agent_labels,
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
      agent_labels=agent_labels,
    )


async def _run_sequential(
  *,
  host: CamoufoxHost,
  items: Sequence[ShoppingListItem],
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: ActivityLog,
  preferences: PreferenceResources,
  auth_manager: AuthManager,
  state: OrchestrationState,
  agent_labels: Mapping[str, str],
) -> ShoppingResults:
  results = ShoppingResults()
  for item in items:
    agent_label = agent_labels.get(item.id, f"agent-{item.id}")
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
        agent_label=agent_label,
      )
    except Exception as exc:  # noqa: BLE001
      await _handle_processing_exception(
        item,
        exc,
        provider,
        agent_label=agent_label,
      )
      outcome = FailedOutcome(error=str(exc))
    results.record(outcome)
  return results


async def _run_concurrent(
  *,
  host: CamoufoxHost,
  items: Sequence[ShoppingListItem],
  provider: ShoppingListProvider,
  settings: ShoppingSettings,
  logger: ActivityLog,
  preferences: PreferenceResources,
  concurrency: int,
  auth_manager: AuthManager,
  state: OrchestrationState,
  agent_labels: Mapping[str, str],
) -> ShoppingResults:
  results = ShoppingResults()
  sem = asyncio.Semaphore(concurrency)
  collected: list[tuple[ShoppingListItem, Outcome]] = []

  async def run_one(item: ShoppingListItem) -> None:
    async with sem:
      agent_label = agent_labels.get(item.id, f"agent-{item.id}")
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
          agent_label=agent_label,
        )
        collected.append((item, outcome))
      except Exception as exc:  # noqa: BLE001
        await _handle_processing_exception(
          item,
          exc,
          provider,
          agent_label=agent_label,
        )
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
  logger: ActivityLog,
  preferences: PreferenceResources,
  auth_manager: AuthManager,
  state: OrchestrationState,
  agent_label: str,
) -> Outcome:
  existing_preference: PreferenceRecord | None = None
  specific_request = False
  activity_log().agent(agent_label).debug(f"Begin pre-shop auth check for '{item.name}'.")
  await state.ensure_pre_shop_auth(auth_manager)
  activity_log().agent(agent_label).debug(f"Stage is {state.stage.value} after auth check.")

  root_normalized = await preferences.coordinator.normalize_item(item.name)
  activity_log().agent(agent_label).warning(f"Normalized '{item.name}' -> {root_normalized}")
  root_original_text = root_normalized.original_text
  active_override: OverrideRequest | None = None
  current_normalized = root_normalized

  while True:
    activity_log().agent(agent_label).warning(
      f"Active shopping text: '{current_normalized.original_text}'."
    )
    preference_session = preferences.coordinator.create_session(current_normalized)
    specific_request = _is_specific_request(current_normalized)
    existing_preference = None
    if not specific_request:
      existing_preference = await preference_session.existing_preference()

    try:
      outcome = await _shop_single_item_in_tab(
        host=host,
        item=item,
        settings=settings,
        shopping_list_provider=provider,
        logger=logger,
        preference_session=preference_session,
        existing_preference=existing_preference,
        specific_request=specific_request,
        auth_manager=auth_manager,
        state=state,
        agent_label=agent_label,
        override=active_override,
        original_entry_text=root_original_text,
      )
    except Exception as exc:  # noqa: BLE001
      await _handle_processing_exception(
        item,
        exc,
        provider,
        agent_label=agent_label,
      )
      return FailedOutcome(error=str(exc))

    if isinstance(outcome, OverrideRequest):
      active_override = outcome
      activity_log().agent(agent_label).operation(
        f"User override received. Using new text "
        f"'{active_override.override_text}' (source={active_override.source})."
      )
      current_normalized = await preferences.coordinator.normalize_item(
        active_override.override_text
      )
      continue
    return outcome


async def _handle_processing_exception(
  item: ShoppingListItem,
  exc: Exception,
  provider: ShoppingListProvider,
  *,
  agent_label: str | None = None,
) -> None:
  import sys
  import traceback

  tb = traceback.format_exc()
  activity_log().agent(agent_label).failure("Exception while shopping item:")
  prefix = f"[{agent_label}] " if agent_label else ""
  print(f"{prefix}{tb}", file=sys.stderr)
  await provider.mark_failed(item.id, f"exception: {exc}\n{tb}")


def _is_specific_request(normalized: NormalizedItem) -> bool:
  if normalized.brand:
    return True
  return any(qualifier.strip() for qualifier in normalized.qualifiers)


async def _shop_single_item_in_tab(
  *,
  host: CamoufoxHost,
  settings: ShoppingSettings,
  item: ShoppingListItem,
  shopping_list_provider: ShoppingListProvider,
  logger: ActivityLog,
  preference_session: PreferenceItemSession,
  existing_preference: PreferenceRecord | None = None,
  specific_request: bool = False,
  auth_manager: AuthManager,
  state: OrchestrationState,
  agent_label: str,
  override: OverrideRequest | None = None,
  original_entry_text: str | None = None,
) -> Outcome | OverrideRequest:
  active_text = preference_session.normalized.original_text
  display_label = active_text
  if override is not None:
    display_label = override.override_text
  activity_log().agent(agent_label).operation(f"🛒 Shopping for '{display_label}'.")
  normalized = preference_session.normalized
  prompt = build_shopper_prompt(
    display_label,
    normalized,
    existing_preference,
    specific_request,
    override_text=override.override_text if override is not None else None,
    original_list_text=original_entry_text,
  )
  activity_log().agent(agent_label).debug(f"Computer-use prompt:\n{textwrap.indent(prompt, '  ')}")
  max_attempts = 2
  for attempt in range(1, max_attempts + 1):
    needs_retry = False
    page = await host.new_agent_managed_page()
    activity_log().agent(agent_label).starting(
      f"Launching browser agent (attempt {attempt}/{max_attempts}) for '{display_label}'."
    )
    agent: BrowserAgent | None = None
    start = time.monotonic()
    budget_seconds = settings.time_budget.total_seconds()
    paused_seconds = 0.0
    turns = 0
    try:
      session = ShoppingSession(
        item=item,
        provider=shopping_list_provider,
        preference_session=preference_session,
      )

      def _on_preference_wait(delta: float) -> None:
        nonlocal paused_seconds
        if delta > 0:
          paused_seconds += delta

      session.on_preference_wait = _on_preference_wait

      agent = BrowserAgent(
        browser_computer=page,
        query=prompt,
        model_name=settings.model_name,
        output_label=f"{agent_label} | {display_label}",
        agent_label=agent_label,
        custom_tools=[
          session.report_item_added,
          session.report_item_not_found,
          session.request_product_choice,
        ],
      )
      status: LoopStatus = LoopStatus.CONTINUE
      while status == LoopStatus.CONTINUE:
        turns += 1
        if turns > settings.max_turns:
          await shopping_list_provider.mark_failed(
            item.id, f"max_turns_exceeded: {settings.max_turns}"
          )
          activity_log().agent(agent_label).warning("Max turns exceeded; marking failed.")
          return FailedOutcome(error=f"max_turns_exceeded: {settings.max_turns}")

        effective_elapsed = time.monotonic() - start - paused_seconds
        if effective_elapsed > budget_seconds:
          await shopping_list_provider.mark_failed(
            item.id, f"time_budget_exceeded: {settings.time_budget}"
          )
          activity_log().agent(agent_label).warning("Time budget exceeded; marking failed.")
          return FailedOutcome(error=f"time_budget_exceeded: {settings.time_budget}")

        try:
          res = await agent.run_one_iteration()
          status = LoopStatus(res)
        except AuthExpiredError:
          needs_retry = True
          activity_log().agent(agent_label).warning(
            f"Authentication expired during attempt {attempt}; scheduling re-auth."
          )
          break

        if session.override_request is not None:
          override = session.override_request
          session.override_request = None
          return override

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
        await shopping_list_provider.mark_failed(item.id, "completed_without_reporting")
        return FailedOutcome(error="completed_without_reporting")
    finally:
      try:
        await page.close()
      except Exception:
        pass
      if agent is not None:
        await agent.close()
    if needs_retry:
      activity_log().agent(agent_label).warning(
        "Authentication refreshed; retrying item from the beginning."
      )
      try:
        await state.ensure_pre_shop_auth(auth_manager)
      except Exception as auth_exc:  # noqa: BLE001
        await shopping_list_provider.mark_failed(item.id, f"auth_recovery_failed: {auth_exc}")
        activity_log().agent(agent_label).failure(
          f"Authentication recovery failed ({auth_exc}); giving up on item."
        )
        return FailedOutcome(error=f"auth_recovery_failed: {auth_exc}")
      continue

  await shopping_list_provider.mark_failed(item.id, "auth_recovery_failed")
  activity_log().agent(agent_label).failure(
    "Authentication recovery exhausted; marking item as failed."
  )
  return FailedOutcome(error="auth_recovery_failed")
