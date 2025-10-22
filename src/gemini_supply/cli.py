from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Callable, Sequence

import clypi.parsers as cp
from clypi import Command, arg
from typing_extensions import override

from gemini_supply.computers import ScreenSize
from gemini_supply.config import DEFAULT_CONFIG_PATH, ConcurrencyConfig, load_config
from gemini_supply.models import ShoppingSettings
from gemini_supply.orchestrator import run_shopping

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


def _concurrency_parser() -> Callable[[Sequence[str] | str], ConcurrencyConfig]:
  def _parser(raw: Sequence[str] | str) -> ConcurrencyConfig:
    if isinstance(raw, str):
      return ConcurrencyConfig.parse(raw)
    if not raw:
      raise ValueError("concurrency value missing")
    return ConcurrencyConfig.parse(raw[0])

  return _parser


class Shop(Command):
  """Shop all uncompleted items from a shopping list on metro.ca"""

  shopping_list: Path | None = arg(
    None, help="Path to the shopping list YAML (YAML provider)", parser=cp.Path(exists=True)
  )
  model: str = arg("gemini-2.5-computer-use-preview-10-2025", help="Model to use")
  time_budget: timedelta = arg(
    timedelta(minutes=5), help="Time budget per item", parser=cp.TimeDelta()
  )
  max_turns: int = arg(40, help="Max agent turns per item")
  concurrency: ConcurrencyConfig | None = arg(
    None,
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
    concurrency_setting = self.concurrency if self.concurrency is not None else config.concurrency
    settings = ShoppingSettings(
      model_name=self.model,
      screen_size=ScreenSize(*PLAYWRIGHT_SCREEN_SIZE),
      time_budget=self.time_budget,
      max_turns=self.max_turns,
      concurrency=concurrency_setting,
    )
    await run_shopping(
      list_path=self.shopping_list.expanduser() if self.shopping_list else None,
      settings=settings,
      no_retry=self.no_retry,
      config=config,
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
