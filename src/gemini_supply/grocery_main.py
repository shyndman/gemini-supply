from __future__ import annotations

import time
from pathlib import Path
from enum import StrEnum
from typing import Literal, TypedDict
from datetime import timedelta

import termcolor

from gemini_supply.agent import BrowserAgent
from gemini_supply.computers import AuthExpiredError, CamoufoxMetroBrowser, ScreenSize
from gemini_supply.grocery.shopping_list import ShoppingListProvider, YAMLShoppingListProvider
from gemini_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingSummary,
)
from gemini_supply.profile import resolve_profile_dir, resolve_camoufox_exec


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
    "  5. If a delivery time sidebar opens, click the link to choose/pick the time later (defer selection).\n"
    "     After deferring, press 'Add to Cart' again on the product page.\n"
    "  6. Verify success: The 'Add to Cart' button becomes a quantity control (with +/−).\n"
    "     If it does not change, try again or explain why it failed.\n"
    "  7. Call report_item_added(item_name, price_text, price_cents, url, quantity) when successful.\n"
    "     The 'url' MUST be the product page URL (NOT the search results page).\n"
    "  8. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).\n\n"
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


async def _shop_single_item(
  item: ShoppingListItem,
  provider: ShoppingListProvider,
  screen_size: ScreenSize,
  model_name: str,
  highlight_mouse: bool,
  time_budget: timedelta,
  max_turns: int,
  camoufox_exec: Path,
  user_data_dir: Path,
  postal_code: str,
) -> Outcome:
  termcolor.cprint(f"🛒 Shopping for: {item['name']}", color="cyan")
  prompt = _build_task_prompt(item["name"], postal_code)
  start = time.monotonic()
  budget_seconds = time_budget.total_seconds()
  turns = 0

  # Always use Camoufox in shopping sessions.
  browser_cm = CamoufoxMetroBrowser(
    screen_size=screen_size,
    user_data_dir=user_data_dir,
    initial_url="https://www.metro.ca",
    highlight_mouse=highlight_mouse,
    enforce_restrictions=True,
    executable_path=camoufox_exec,
  )

  async with browser_cm as computer:
    agent = BrowserAgent(browser_computer=computer, query=prompt, model_name=model_name)
    try:
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

        # Terminal on first custom tool call (implementation detail)
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

      # If loop completed without custom tool call, treat as failure with reasoning if available
      provider.mark_failed(item["id"], "completed_without_reporting")
      return {"type": "failed", "error": "completed_without_reporting"}
    finally:
      agent.close()


async def run_shopping(
  *,
  list_path: Path,
  model_name: str,
  highlight_mouse: bool,
  screen_size: ScreenSize | tuple[int, int] = ScreenSize(1440, 900),
  time_budget: timedelta = timedelta(minutes=5),
  max_turns: int = 40,
  postal_code: str,
) -> int:
  provider: ShoppingListProvider = YAMLShoppingListProvider(path=list_path)
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

  for item in items:
    try:
      outcome = await _shop_single_item(
        item=item,
        provider=provider,
        screen_size=normalized_screen_size,
        model_name=model_name,
        highlight_mouse=highlight_mouse,
        time_budget=time_budget,
        max_turns=max_turns,
        camoufox_exec=camoufox_exec,
        user_data_dir=profile_dir,
        postal_code=postal_code,
      )
      if outcome["type"] == "added":
        res = outcome["result"]
        added.append(res)
        total_cents += res["price_cents"]
      elif outcome["type"] == "not_found":
        not_found.append(outcome["result"])
      else:
        failed.append(outcome["error"])
    except Exception as e:  # noqa: BLE001
      import traceback
      import sys

      tb = traceback.format_exc()
      termcolor.cprint("Exception while shopping item:", color="red")
      print(tb, file=sys.stderr)
      failed.append(f"{item['name']}: {e}")
      provider.mark_failed(item["id"], f"exception: {e}\n{tb}")

  # Best-effort summary compilation from provider is not available here; assemble minimal
  summary: ShoppingSummary = {
    "added_items": added,
    "not_found_items": not_found,
    "failed_items": failed,
    "total_cost_cents": total_cents,
    "total_cost_text": f"${total_cents / 100:.2f}",
  }
  provider.send_summary(summary)
  return 0
