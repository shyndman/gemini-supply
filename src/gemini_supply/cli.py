from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from pathlib import Path
from typing import Callable, Sequence

import clypi.parsers as cp
from clypi import Command, arg
from typing_extensions import override
from playwright.async_api import expect
from gemini_supply.computers import ScreenSize
from gemini_supply.computers.browser_host import CamoufoxHost, build_camoufox_options
from gemini_supply.config import DEFAULT_CONFIG_PATH, ConcurrencyConfig, load_config
from gemini_supply.models import ShoppingSettings
from gemini_supply.orchestrator import run_shopping, load_init_scripts
from gemini_supply.profile import resolve_camoufox_exec, resolve_profile_dir

PLAYWRIGHT_SCREEN_SIZE = (1024, 768)


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


class Browse(Command):
  """Open a headed browser using the Gemini Supply profile"""

  initial_url: str = arg("https://www.metro.ca", help="Initial URL to open")

  @override
  async def run(self) -> None:
    # Force headed mode
    os.environ["PLAYWRIGHT_HEADLESS"] = "false"

    profile_dir = resolve_profile_dir()
    camoufox_exec = resolve_camoufox_exec()

    async with CamoufoxHost(
      screen_size=ScreenSize(*PLAYWRIGHT_SCREEN_SIZE),
      user_data_dir=profile_dir,
      initial_url=self.initial_url,
      init_scripts=load_init_scripts(),
      enforce_restrictions=False,
      executable_path=camoufox_exec,
      camoufox_options=build_camoufox_options(),
    ) as host:
      await host.new_page()
      print(f"Browser opened at {self.initial_url}. Press Ctrl+C to exit.")
      try:
        await asyncio.sleep(float("inf"))
      except asyncio.CancelledError:
        pass


class ClearStorage(Command):
  """Open a headed browser using the Gemini Supply profile"""

  @override
  async def run(self) -> None:
    # Force headed mode
    os.environ["PLAYWRIGHT_HEADLESS"] = "true"

    profile_dir = resolve_profile_dir()
    camoufox_exec = resolve_camoufox_exec()
    initial_url = "https://www.whatismyip.com/"

    async with CamoufoxHost(
      screen_size=ScreenSize(*PLAYWRIGHT_SCREEN_SIZE),
      user_data_dir=profile_dir,
      initial_url=initial_url,
      enforce_restrictions=False,
      executable_path=camoufox_exec,
      camoufox_options=build_camoufox_options(),
    ) as host:
      page = await host.new_page()
      print(f"Browser opened at {initial_url}. Press Ctrl+C to exit.")
      # Wait for IPv4 address to appear
      isp_element = page.locator(".ip-address-isp")
      # Wait for content to contain a valid IPv4 pattern
      await expect(isp_element).to_have_text("ISP:Coextro", timeout=10000)

      await host.context.clear_cookies(domain="auth.moiid.ca")
      await host.context.clear_cookies(domain="www.metro.ca")
      print("Cleared cookies for auth.moiid.ca and metro.ca")

      await page.goto("https://www.metro.ca")
      await page.evaluate("localStorage.clear()")
      print("Cleared local storage for metro.ca")


class Cli(Command):
  """Gemini Supply CLI."""

  subcommand: Shop | Browse | ClearStorage


def run() -> int:
  try:
    cmd = Cli.parse()
    cmd.start()
    return 0
  except KeyboardInterrupt:
    print("\nInterrupted by user (Ctrl+C). Exiting cleanly.")
    return 130


__all__ = ["run", "Cli", "Shop", "Browse"]
