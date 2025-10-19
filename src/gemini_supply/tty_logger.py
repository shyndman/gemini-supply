from __future__ import annotations

import asyncio
from typing import Optional

from rich.console import Console
from rich.table import Table

from gemini_supply.display import display_image_kitty


class TTYLogger:
  """Concurrency-safe terminal logger for reasoning and screenshots.

  Ensures multi-agent output remains readable by serializing writes.
  """

  def __init__(self, lock: Optional[asyncio.Lock] = None) -> None:
    self._lock = lock or asyncio.Lock()
    self._console = Console()

  async def print_reasoning(self, *, label: str | None, turn_index: int, table: Table) -> None:
    async with self._lock:
      if label:
        self._console.print(f"[bold green]{label}[/bold green] — Turn {turn_index}")
      self._console.print(table)
      print()

  async def show_screenshot(
    self,
    *,
    label: str | None,
    action_name: str,
    url: str,
    png_bytes: bytes,
    max_width: int | None,
  ) -> None:
    async with self._lock:
      if label:
        self._console.print(f"[cyan]{label}[/cyan] → {action_name} @ {url}")
      display_image_kitty(png_bytes, max_width=max_width)
