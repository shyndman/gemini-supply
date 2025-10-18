from __future__ import annotations

import time
from pathlib import Path
from enum import StrEnum
from datetime import timedelta

import termcolor

from gemini_supply.agent import BrowserAgent
from gemini_supply.computers import (
  AuthExpiredError,
  CamoufoxMetroBrowser,
)
from gemini_supply.grocery.shopping_list import ShoppingListProvider, YAMLShoppingListProvider
from gemini_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingSummary,
)


def _build_task_prompt(item_name: str) -> str:
  return (
    "Goal: Add ONE specific item to metro.ca cart\n"
    f"Item: {item_name}\n\n"
    "Instructions:\n"
    "  1. Use metro.ca to find the product.\n"
    "  2. Prefer using navigate to open the search results page (SRP) directly: \n"
    "     https://www.metro.ca/en/online-grocery/search?filter={ENCODED_QUERY}\n"
    "     Otherwise, use the header search input present on all pages.\n"
    "  3. Add the item to the cart.\n"
    "  4. Call report_item_added(item_name, price_text, price_cents, url, quantity) when successful.\n"
    "  5. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).\n\n"
    "Constraints:\n"
    "  - Stay on metro.ca and allowed resources only.\n"
    "  - Do NOT navigate to checkout, payment, or account pages.\n"
    "  - Focus solely on adding the requested item.\n"
  )


class LoopStatus(StrEnum):
  COMPLETE = "COMPLETE"
  CONTINUE = "CONTINUE"


async def _shop_single_item(
  item: ShoppingListItem,
  provider: ShoppingListProvider,
  screen_size: tuple[int, int],
  storage_state_path: Path,
  model_name: str,
  highlight_mouse: bool,
  time_budget: timedelta,
  max_turns: int,
  camoufox_exec: str | None,
  user_data_dir: str | None,
) -> None:
  termcolor.cprint(f"🛒 Shopping for: {item['name']}", color="cyan")
  prompt = _build_task_prompt(item["name"])
  start = time.monotonic()
  budget_seconds = time_budget.total_seconds()
  turns = 0

  # Always use Camoufox in shopping sessions.
  browser_cm = CamoufoxMetroBrowser(
    screen_size=screen_size,
    storage_state_path=str(storage_state_path),
    initial_url="https://www.metro.ca",
    highlight_mouse=highlight_mouse,
    enforce_restrictions=True,
    executable_path=camoufox_exec,
    user_data_dir=user_data_dir,
  )

  async with browser_cm as computer:
    agent = BrowserAgent(browser_computer=computer, query=prompt, model_name=model_name)

    status: LoopStatus = LoopStatus.CONTINUE
    while status == LoopStatus.CONTINUE:
      turns += 1
      if turns > max_turns:
        provider.mark_failed(item["id"], f"max_turns_exceeded: {max_turns}")
        termcolor.cprint("Max turns exceeded; marking failed.", color="yellow")
        return

      if time.monotonic() - start > budget_seconds:
        provider.mark_failed(item["id"], f"time_budget_exceeded: {time_budget}")
        termcolor.cprint("Time budget exceeded; marking failed.", color="yellow")
        return

      try:
        res = await agent.run_one_iteration()
        status = LoopStatus(res)
      except AuthExpiredError:
        provider.mark_failed(item["id"], "auth_expired")
        termcolor.cprint("Authentication expired; stopping session.", color="red")
        return

      # Terminal on first custom tool call (implementation detail)
      if agent.last_custom_tool_call is not None:
        name = agent.last_custom_tool_call["name"]
        payload = agent.last_custom_tool_call["payload"]
        if name == "report_item_added":
          provider.mark_completed(item["id"], payload)  # type: ignore[arg-type]
        elif name == "report_item_not_found":
          provider.mark_not_found(item["id"], payload)  # type: ignore[arg-type]
        else:
          provider.mark_failed(item["id"], f"unexpected_custom_tool: {name}")
        return

    # If loop completed without custom tool call, treat as failure with reasoning if available
    provider.mark_failed(item["id"], "completed_without_reporting")


async def run_shopping(
  *,
  list_path: Path,
  model_name: str,
  highlight_mouse: bool,
  screen_size: tuple[int, int] = (1440, 900),
  storage_state_path: Path | None = None,
  time_budget: timedelta = timedelta(minutes=5),
  max_turns: int = 40,
  camoufox_exec: str | None = None,
  user_data_dir: Path | None = None,
) -> int:
  provider: ShoppingListProvider = YAMLShoppingListProvider(path=list_path)
  storage_path = storage_state_path or Path("~/.config/gemini-supply/metro_auth.json").expanduser()

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
      await _shop_single_item(
        item=item,
        provider=provider,
        screen_size=screen_size,
        storage_state_path=storage_path,
        model_name=model_name,
        highlight_mouse=highlight_mouse,
        time_budget=time_budget,
        max_turns=max_turns,
        camoufox_exec=camoufox_exec,
        user_data_dir=str(user_data_dir.expanduser()) if user_data_dir else None,
      )
    except Exception as e:  # noqa: BLE001
      failed.append(f"{item['name']}: {e}")
      provider.mark_failed(item["id"], f"exception: {e}")

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
