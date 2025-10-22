from __future__ import annotations
from datetime import timedelta
from pathlib import Path
from typing import Callable, Literal, Sequence

import clypi.parsers as cp
from clypi import Command, arg
from typing_extensions import override

from gemini_supply.computers import ScreenSize
from gemini_supply import DEFAULT_CONFIG_PATH, load_config
from gemini_supply.shopping import run_shopping
from gemini_supply.shopping import ConcurrencySetting, ShoppingSettings

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


def _parse_concurrency(raw: str) -> int | Literal["len"]:
  value = raw.strip().lower()
  if value == "len":
    return "len"
  try:
    parsed = int(value)
  except ValueError as exc:
    raise ValueError("concurrency must be a non-negative integer or 'len'") from exc
  if parsed < 0:
    raise ValueError("concurrency must be a non-negative integer or 'len'")
  return parsed


def _concurrency_parser() -> Callable[[Sequence[str] | str], int | Literal["len"]]:
  def _parser(raw: Sequence[str] | str) -> int | Literal["len"]:
    if isinstance(raw, str):
      return _parse_concurrency(raw)
    if not raw:
      raise ValueError("concurrency value missing")
    return _parse_concurrency(raw[0])

  return _parser


class Shop(Command):
  """Shop all uncompleted items from a shopping list on metro.ca"""

  shopping_list: Path | None = arg(
    None, help="Path to the shopping list YAML (YAML provider)", parser=cp.Path(exists=True)
  )
  model: str = arg("gemini-2.5-computer-use-preview-10-2025", help="Model to use")
  highlight_mouse: bool = arg(False, help="Highlight mouse for debugging")
  time_budget: timedelta = arg(
    timedelta(minutes=5), help="Time budget per item", parser=cp.TimeDelta()
  )
  max_turns: int = arg(40, help="Max agent turns per item")
  postal_code: str | None = arg(None, help="Postal code to use; may also be set in config")
  concurrency: int | Literal["len"] = arg(
    0,
    help="Number of items to process in parallel (tabs). Use 'len' to match item count (max 20).",
    parser=_concurrency_parser(),
  )
  no_retry: bool = arg(
    False,
    help="Skip items already tagged (#not_found, #out_of_stock, #failed, #dupe)",
  )
  config: Path | None = arg(
    None, help="Path to config.yaml (defaults to ~/.config/gemini-supply/config.yaml)"
  )

  @override
  async def run(self) -> None:
    config_path = self.config.expanduser() if self.config else DEFAULT_CONFIG_PATH
    config = load_config(config_path)
    postal_code = self.postal_code or (
      config.postal_code if config and config.postal_code else None
    )
    if not postal_code:
      raise ValueError("Postal code is required via --postal-code or config postal_code")
    concurrency_setting = ConcurrencySetting.from_inputs(
      cli_value=self.concurrency,
      config_value=config.concurrency if config else None,
    )
    settings = ShoppingSettings(
      model_name=self.model,
      highlight_mouse=self.highlight_mouse,
      screen_size=ScreenSize(*PLAYWRIGHT_SCREEN_SIZE),
      time_budget=self.time_budget,
      max_turns=self.max_turns,
      postal_code=postal_code,
      concurrency=concurrency_setting,
    )
    await run_shopping(
      list_path=self.shopping_list.expanduser() if self.shopping_list else None,
      settings=settings,
      no_retry=self.no_retry,
      config=config,
      config_path=config_path,
    )


class Cli(Command):
  """Gemini Supply CLI."""

  subcommand: Shop


def run() -> int:
  try:
    cmd = Cli.parse()
    cmd.start()
    return 0
  except KeyboardInterrupt:
    print("\nInterrupted by user (Ctrl+C). Exiting cleanly.")
    return 130


__all__ = ["run", "Cli", "Shop"]
