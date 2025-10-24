from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import Optional

import logfire
from PIL import Image as PILImage
from PIL.Image import Image as PILImageT
from rich.console import Console
from rich.table import Table
from textual_image.renderable import ConsoleImage


def setup_logging() -> None:
  """Configure logging for the application."""
  # Suppress all logging from third-party libraries
  logging.getLogger("playwright-captcha").setLevel(logging.CRITICAL)
  logfire.configure(console=logfire.ConsoleOptions(verbose=True))
  logfire.instrument_httpx()
  logfire.instrument_pydantic_ai()


class TTYLogger:
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
    display_image_in_terminal(pil_image)


def display_image_in_terminal(image: PILImageT) -> None:
  with Console() as console:
    console.print(ConsoleImage(image, width="30%", height="auto"))
