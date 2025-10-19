from __future__ import annotations

import time
import os
from pathlib import Path
from enum import StrEnum
from typing import Literal, TypedDict
from datetime import timedelta

import termcolor

from gemini_supply.agent import BrowserAgent
from gemini_supply.computers import (
  AuthExpiredError,
  ScreenSize,
  CamoufoxHost,
)
from gemini_supply.grocery.shopping_list import (
  ShoppingListProvider,
  YAMLShoppingListProvider,
  HomeAssistantShoppingListProvider,
)
from gemini_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingSummary,
)
from gemini_supply.profile import resolve_profile_dir, resolve_camoufox_exec
from gemini_supply.config import load_config, DEFAULT_CONFIG_PATH


def _build_task_prompt(item_name: str, postal_code: str) -> str:
  return (
    "Goal: Add ONE specific item to metro.ca cart\n"
    f"Item: {item_name}\n\n"
    "Instructions:\n"
    "  1. Use metro.ca to find the product.\n"
    "  2. Prefer using navigate to open the search results page (SRP) directly: \n"
    "     https://www.metro.ca/en/online-grocery/search?filter={ENCODED_QUERY}\n"
    "     Otherwise, use the header search input present on all pages.\n"
    "  3. From the SRP, choose the best-matching result. CLICK THE PRODUCT IMAGE or name to open the product's page.\n"
    "  4. On the product page, press 'Add to Cart'. If a postal code form appears, enter the postal code exactly as: \n"
    f"     {postal_code}\n"
    '     If the "Delivery or Pickup?" form appears, click the "I haven\'t made my choice yet" link at the bottom to defer selection, then press \'Add to Cart\' again on the product page.\n'
    "  5. Verify success: The 'Add to Cart' button becomes a quantity control (with +/−).\n"
    "     If it does not change, try again or explain why it failed.\n"
    "  6. Call report_item_added(item_name, price_text, price_cents, url, quantity) when successful.\n"
    "     The 'url' MUST be the product page URL (NOT the search results page).\n"
    "  7. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).\n\n"
    "Constraints:\n"
    "  - Stay on metro.ca and allowed resources only.\n"
    "  - Do NOT navigate to checkout, payment, or account pages.\n"
    "  - Focus solely on adding the requested item.\n"
  )


class LoopStatus(StrEnum):
  COMPLETE = "COMPLETE"
  CONTINUE = "CONTINUE"


class ItemAddedOutcome(TypedDict):
  type: Literal["added"]
  result: ItemAddedResult


class ItemNotFoundOutcome(TypedDict):
  type: Literal["not_found"]
  result: ItemNotFoundResult


class ItemFailedOutcome(TypedDict):
  type: Literal["failed"]
  error: str


Outcome = ItemAddedOutcome | ItemNotFoundOutcome | ItemFailedOutcome


# Removed legacy single-page path; all runs use host+tab now.


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
) -> Outcome:
  termcolor.cprint(f"🛒 (tab) Shopping for: {item['name']}", color="cyan")
  prompt = _build_task_prompt(item["name"], postal_code)
  start = time.monotonic()
  budget_seconds = time_budget.total_seconds()
  turns = 0

  tab = await host.new_tab()
  agent: BrowserAgent | None = None
  try:
    agent = BrowserAgent(browser_computer=tab, query=prompt, model_name=model_name)
    status: LoopStatus = LoopStatus.CONTINUE
    while status == LoopStatus.CONTINUE:
      turns += 1
      if turns > max_turns:
        provider.mark_failed(item["id"], f"max_turns_exceeded: {max_turns}")
        termcolor.cprint("Max turns exceeded; marking failed.", color="yellow")
        return {"type": "failed", "error": f"max_turns_exceeded: {max_turns}"}

      if time.monotonic() - start > budget_seconds:
        provider.mark_failed(item["id"], f"time_budget_exceeded: {time_budget}")
        termcolor.cprint("Time budget exceeded; marking failed.", color="yellow")
        return {"type": "failed", "error": f"time_budget_exceeded: {time_budget}"}

      try:
        res = await agent.run_one_iteration()
        status = LoopStatus(res)
      except AuthExpiredError:
        provider.mark_failed(item["id"], "auth_expired")
        termcolor.cprint("Authentication expired; stopping session.", color="red")
        return {"type": "failed", "error": "auth_expired"}

      if agent.last_custom_tool_call is not None:
        name = agent.last_custom_tool_call["name"]
        payload = agent.last_custom_tool_call["payload"]
        if name == "report_item_added":
          provider.mark_completed(item["id"], payload)  # type: ignore[arg-type]
          return {"type": "added", "result": payload}  # type: ignore[dict-item]
        elif name == "report_item_not_found":
          provider.mark_not_found(item["id"], payload)  # type: ignore[arg-type]
          return {"type": "not_found", "result": payload}  # type: ignore[dict-item]
        else:
          provider.mark_failed(item["id"], f"unexpected_custom_tool: {name}")
          return {"type": "failed", "error": f"unexpected_custom_tool: {name}"}

    provider.mark_failed(item["id"], "completed_without_reporting")
    return {"type": "failed", "error": "completed_without_reporting"}
  finally:
    try:
      await tab.close()
    except Exception:
      pass
    if agent is not None:
      agent.close()


async def run_shopping(
  *,
  list_path: Path | None,
  model_name: str,
  highlight_mouse: bool,
  screen_size: ScreenSize | tuple[int, int] = ScreenSize(1440, 900),
  time_budget: timedelta = timedelta(minutes=5),
  max_turns: int = 40,
  postal_code: str | None,
  no_retry: bool = False,
  config_path: Path | None = None,
  concurrency: int | None = None,
) -> int:
  # Choose provider from config (if present), else YAML file path
  cfg = load_config(config_path or DEFAULT_CONFIG_PATH)
  # Resolve postal code from CLI or config
  resolved_postal: str | None = postal_code
  if not resolved_postal and cfg:
    pc = cfg.get("postal_code")
    if isinstance(pc, str) and pc.strip():
      resolved_postal = pc.strip()
  if not resolved_postal:
    raise ValueError("Postal code is required via --postal-code or config postal_code")
  provider: ShoppingListProvider
  if cfg and cfg.get("shopping_list", {}).get("provider") == "home_assistant":
    ha = cfg.get("home_assistant", {})
    url = str(ha.get("url", "")).strip()
    token = str(ha.get("token", "")).strip()
    if not url or not token:
      raise ValueError("home_assistant.url and home_assistant.token are required in config")
    provider = HomeAssistantShoppingListProvider(ha_url=url, token=token, no_retry=no_retry)
  else:
    if list_path is None:
      raise ValueError("--shopping-list is required for YAML provider")
    provider = YAMLShoppingListProvider(path=list_path)
  normalized_screen_size = (
    screen_size if isinstance(screen_size, ScreenSize) else ScreenSize(*screen_size)
  )

  # Resolve persistent profile directory (env or default), ensure it exists, and announce once
  profile_dir = resolve_profile_dir()
  termcolor.cprint(f"Using profile: {profile_dir}", color="cyan")

  # Resolve Camoufox executable path (required)
  camoufox_exec = resolve_camoufox_exec()

  items = provider.get_uncompleted_items()
  if not items:
    termcolor.cprint("No uncompleted items found.", color="yellow")
    return 0

  added: list[ItemAddedResult] = []
  not_found: list[ItemNotFoundResult] = []
  failed: list[str] = []
  total_cents = 0

  # Resolve effective concurrency: CLI > config > default 1
  eff_conc: int = 1
  if concurrency is not None and concurrency > 0:
    eff_conc = concurrency
  elif cfg and isinstance(cfg.get("concurrency"), int) and int(cfg.get("concurrency")) >= 1:  # type: ignore[arg-type]
    eff_conc = int(cfg.get("concurrency"))  # type: ignore[call-overload]

  # Guard YAML provider from concurrent writes; force sequential
  if isinstance(provider, YAMLShoppingListProvider) and eff_conc > 1:
    termcolor.cprint(
      "YAML provider does not support parallel writes; forcing concurrency=1.",
      color="yellow",
    )
    eff_conc = 1

  # Disable inline screenshots for parallel runs to keep terminal readable
  prev_img = os.environ.get("GEMINI_SUPPLY_IMG_ENABLE", "1")
  if eff_conc > 1:
    os.environ["GEMINI_SUPPLY_IMG_ENABLE"] = "0"

  try:
    # Always use a single host; run sequentially or in parallel tabs.
    # Headless by default for shop; allow override via PLAYWRIGHT_HEADLESS=0
    env_h = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()
    headless = False if env_h in ("0", "false", "no") else True
    async with CamoufoxHost(
      screen_size=normalized_screen_size,
      user_data_dir=profile_dir,
      initial_url="https://www.metro.ca",
      highlight_mouse=highlight_mouse,
      enforce_restrictions=True,
      executable_path=camoufox_exec,
      headless=headless,
    ) as host:
      import asyncio

      if eff_conc <= 1:
        for item in items:
          try:
            out = await _shop_single_item_in_tab(
              host=host,
              item=item,
              provider=provider,
              model_name=model_name,
              highlight_mouse=highlight_mouse,
              time_budget=time_budget,
              max_turns=max_turns,
              postal_code=resolved_postal,
            )
            if out["type"] == "added":
              res = out["result"]
              added.append(res)
              total_cents += res["price_cents"]
            elif out["type"] == "not_found":
              not_found.append(out["result"])
            else:
              failed.append(out["error"])
          except Exception as e:  # noqa: BLE001
            import traceback
            import sys

            tb = traceback.format_exc()
            termcolor.cprint("Exception while shopping item:", color="red")
            print(tb, file=sys.stderr)
            failed.append(f"{item['name']}: {e}")
            provider.mark_failed(item["id"], f"exception: {e}\n{tb}")
      else:
        sem = asyncio.Semaphore(eff_conc)
        results: list[tuple[ShoppingListItem, Outcome | Exception]] = []

        async def run_one(it: ShoppingListItem) -> None:
          async with sem:
            try:
              out = await _shop_single_item_in_tab(
                host=host,
                item=it,
                provider=provider,
                model_name=model_name,
                highlight_mouse=highlight_mouse,
                time_budget=time_budget,
                max_turns=max_turns,
                postal_code=resolved_postal,
              )
              results.append((it, out))
            except Exception as e:  # noqa: BLE001
              results.append((it, e))

        tg: asyncio.TaskGroup
        async with asyncio.TaskGroup() as tg:
          for it in items:
            tg.create_task(run_one(it))

        for it, res in results:
          if isinstance(res, Exception):
            import traceback
            import sys

            tb = traceback.format_exc()
            termcolor.cprint("Exception while shopping item:", color="red")
            print(tb, file=sys.stderr)
            failed.append(f"{it['name']}: {res}")
            provider.mark_failed(it["id"], f"exception: {res}\n{tb}")
          else:
            outcome = res
            if outcome["type"] == "added":
              r = outcome["result"]
              added.append(r)
              total_cents += r["price_cents"]
            elif outcome["type"] == "not_found":
              not_found.append(outcome["result"])
            else:
              failed.append(outcome["error"])
  finally:
    if eff_conc > 1:
      os.environ["GEMINI_SUPPLY_IMG_ENABLE"] = prev_img

  # Best-effort summary compilation from provider is not available here; assemble minimal
  summary: ShoppingSummary = {
    "added_items": added,
    "not_found_items": not_found,
    "out_of_stock_items": [],
    "duplicate_items": [],
    "failed_items": failed,
    "total_cost_cents": total_cents,
    "total_cost_text": f"${total_cents / 100:.2f}",
  }
  provider.send_summary(summary)
  return 0
