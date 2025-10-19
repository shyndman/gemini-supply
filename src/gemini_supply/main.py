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

from gemini_supply.computers import CamoufoxMetroBrowser
from gemini_supply.grocery_main import run_shopping
from gemini_supply.profile import resolve_profile_dir, resolve_camoufox_exec

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


class Shop(Command):
  """Shop all uncompleted items from a shopping list on metro.ca"""

  list: Path = arg(help="Path to the shopping list YAML", parser=cp.Path(exists=True))
  model: str = arg("gemini-2.5-computer-use-preview-10-2025", help="Model to use")
  highlight_mouse: bool = arg(False, help="Highlight mouse for debugging")
  time_budget: timedelta = arg(
    timedelta(minutes=5), help="Time budget per item", parser=cp.TimeDelta()
  )
  max_turns: int = arg(40, help="Max agent turns per item")
  postal_code: str = arg(help="Postal code to use if delivery prompt appears (e.g., M5V 1J1)")

  @override
  async def run(self) -> None:
    # shop delegates profile/executable resolution to grocery_main
    await run_shopping(
      list_path=self.list.expanduser(),
      model_name=self.model,
      highlight_mouse=self.highlight_mouse,
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      time_budget=self.time_budget,
      max_turns=self.max_turns,
      postal_code=self.postal_code,
    )


class AuthSetup(Command):
  """Open metro.ca to authenticate using a persistent profile"""

  highlight_mouse: bool = arg(False, help="Highlight mouse for debugging")

  @override
  async def run(self) -> None:
    profile_dir = resolve_profile_dir()
    camou_exec = resolve_camoufox_exec()
    print(f"Using profile: {profile_dir}")

    browser_cm = CamoufoxMetroBrowser(
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      user_data_dir=profile_dir,
      initial_url="https://www.metro.ca",
      highlight_mouse=self.highlight_mouse,
      enforce_restrictions=False,
      executable_path=camou_exec,
    )

    async with browser_cm:
      print("A browser window has opened. Please log in to metro.ca, then press Enter to finish...")
      await asyncio.to_thread(input)
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
