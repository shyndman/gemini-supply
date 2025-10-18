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
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import clypi.parsers as cp
from clypi import Command, arg
from typing_extensions import override

from gemini_supply.computers import CamoufoxMetroBrowser
from gemini_supply.grocery_main import run_shopping

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
  storage_state: Path | None = arg(None, help="Override storage state path")
  camoufox_exec: Path | None = arg(None, help="Path to Camoufox executable (auto-detects)")
  user_data_dir: Path | None = arg(None, help="User data dir for persistent profile (Camoufox)")

  @override
  async def run(self) -> None:
    def _resolve_camoufox_exec(p: Path | None) -> str | None:
      if p is not None:
        return str(p.expanduser())
      try:
        # Query camoufox-provided path within the current Python environment
        proc = subprocess.run(
          [sys.executable, "-m", "camoufox", "path"],
          check=True,
          capture_output=True,
          text=True,
        )
        resolved = proc.stdout.strip()
        if not resolved:
          return None
        rp = Path(resolved).expanduser()
        # python -m camoufox path returns the root directory; the binary
        # lives directly under it with the same name. Normalize here.
        if rp.is_dir():
          rp = rp / rp.name
        return str(rp)
      except Exception:
        return None

    camou_exec: str | None = _resolve_camoufox_exec(self.camoufox_exec)

    await run_shopping(
      list_path=self.list.expanduser(),
      model_name=self.model,
      highlight_mouse=self.highlight_mouse,
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      storage_state_path=self.storage_state.expanduser() if self.storage_state else None,
      time_budget=self.time_budget,
      max_turns=self.max_turns,
      camoufox_exec=camou_exec,
      user_data_dir=self.user_data_dir.expanduser() if self.user_data_dir else None,
    )


class AuthSetup(Command):
  """Open metro.ca to authenticate and save storage state"""

  storage_state: Path = arg(
    Path("~/.config/gemini-supply/metro_auth.json"), help="Path to save storage state"
  )
  highlight_mouse: bool = arg(False, help="Highlight mouse for debugging")
  user_data_dir: Path | None = arg(None, help="Use this user data dir for a persistent context")
  camoufox_exec: Path | None = arg(None, help="Path to Camoufox executable (auto-detects)")

  @override
  async def run(self) -> None:
    path = self.storage_state.expanduser()
    # Determine user data dir to use
    udir: Path | None = self.user_data_dir.expanduser() if self.user_data_dir else None

    def _resolve_camoufox_exec(p: Path | None) -> str | None:
      if p is not None:
        return str(p.expanduser())
      try:
        proc = subprocess.run(
          [sys.executable, "-m", "camoufox", "path"],
          check=True,
          capture_output=True,
          text=True,
        )
        resolved = proc.stdout.strip()
        if not resolved:
          return None
        rp = Path(resolved).expanduser()
        if rp.is_dir():
          rp = rp / rp.name
        return str(rp)
      except Exception:
        return None

    browser_cm = CamoufoxMetroBrowser(
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
      storage_state_path=str(path),
      initial_url="https://www.metro.ca",
      highlight_mouse=self.highlight_mouse,
      enforce_restrictions=False,
      executable_path=_resolve_camoufox_exec(self.camoufox_exec),
      user_data_dir=str(udir) if udir else None,
    )

    async with browser_cm:
      print("A browser window has opened. Please log in to metro.ca, then press Enter to finish...")
      await asyncio.to_thread(input)
    print(f"Saved authentication state to: {path}")


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
