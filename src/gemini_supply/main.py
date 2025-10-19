# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
from datetime import timedelta
from pathlib import Path

import clypi.parsers as cp
from clypi import Command, arg
from typing_extensions import override

from gemini_supply.computers import CamoufoxHost
from gemini_supply.grocery_main import run_shopping
from gemini_supply.profile import resolve_profile_dir, resolve_camoufox_exec

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


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
  concurrency: int = arg(
    0,
    help="Number of items to process in parallel (tabs). 0 = use config or default 1",
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
    # shop delegates profile/executable resolution to grocery_main
    await run_shopping(
      list_path=self.shopping_list.expanduser() if self.shopping_list else None,
      model_name=self.model,
      highlight_mouse=self.highlight_mouse,
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      time_budget=self.time_budget,
      max_turns=self.max_turns,
      postal_code=self.postal_code,
      no_retry=self.no_retry,
      config_path=self.config.expanduser() if self.config else None,
      concurrency=self.concurrency,
    )


class AuthSetup(Command):
  """Open metro.ca to authenticate using a persistent profile"""

  highlight_mouse: bool = arg(False, help="Highlight mouse for debugging")

  @override
  async def run(self) -> None:
    profile_dir = resolve_profile_dir()
    camou_exec = resolve_camoufox_exec()
    print(f"Using profile: {profile_dir}")

    async with CamoufoxHost(
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      user_data_dir=profile_dir,
      initial_url="https://www.metro.ca",
      highlight_mouse=self.highlight_mouse,
      enforce_restrictions=False,
      executable_path=camou_exec,
      headless=False,
    ) as host:
      # Acquire a tab so the window opens, then wait for user
      tab = await host.new_tab()
      try:
        print(
          "A browser window has opened. Please log in to metro.ca, then press Enter to finish..."
        )
        await asyncio.to_thread(input)
      finally:
        try:
          await tab.close()
        except Exception:
          pass
    print("Authentication session complete. Credentials persisted in the profile.")


class Cli(Command):
  """Gemini Supply CLI"""

  subcommand: Shop | AuthSetup


def main() -> int:
  try:
    cmd = Cli.parse()
    cmd.start()
    return 0
  except KeyboardInterrupt:
    # Graceful exit on Ctrl+C without stack trace
    print("\nInterrupted by user (Ctrl+C). Exiting cleanly.")
    return 130
