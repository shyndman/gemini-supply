from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Optional

from PIL import Image as PILImage
from PIL.Image import Image as PILImageT, Resampling
from rich.console import Console
from rich.table import Table
from textual_image.renderable import Image as ConsoleImage


class ActivityLog:
  """Concurrency-safe terminal logger for reasoning and screenshots."""

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
  ) -> None:
    async with self._lock:
      if label:
        self._console.print(f"[cyan]{label}[/cyan] → {action_name} @ {url}")
      display_image_bytes_in_terminal(png_bytes)


def display_image_bytes_in_terminal(png_bytes: bytes) -> None:
  with PILImage.open(BytesIO(png_bytes)) as pil_image:
    pil_image.resize(
      size=(int(pil_image.width * 0.8), int(pil_image.height * 0.8)), resample=Resampling.BICUBIC
    )
    display_image_in_terminal(pil_image)


def display_image_in_terminal(image: PILImageT) -> None:
  with Console() as console:
    console.print(ConsoleImage(image))
