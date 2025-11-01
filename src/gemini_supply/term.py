from __future__ import annotations

from io import BytesIO

from PIL import Image as PILImage
from PIL.Image import Image as PILImageT
from PIL.Image import Resampling
from rich.console import Console
from rich.table import Table
from textual_image.renderable import Image as ConsoleImage


class CategoryLogger:
  """Prefixed logger delegate for a specific category."""

  def __init__(self, console: Console, prefix: str) -> None:
    self._console = console
    self._prefix = prefix

  def operation(self, message: str) -> None:
    """Log an operation in progress (cyan)."""
    self._console.print(f"[cyan]\\[{self._prefix}] {message}[/cyan]")

  def success(self, message: str) -> None:
    """Log a successful completion (green)."""
    self._console.print(f"[green]\\[{self._prefix}] {message}[/green]")

  def warning(self, message: str) -> None:
    """Log a warning or unusual state (yellow)."""
    self._console.print(f"[yellow]\\[{self._prefix}] {message}[/yellow]")

  def important(self, message: str) -> None:
    """Log important data or information (magenta)."""
    self._console.print(f"[magenta]\\[{self._prefix}] {message}[/magenta]")

  def failure(self, message: str) -> None:
    """Log an error or failure (red)."""
    self._console.print(f"[red]\\[{self._prefix}] {message}[/red]")

  def starting(self, message: str) -> None:
    """Log the start of a process (blue)."""
    self._console.print(f"[blue]\\[{self._prefix}] {message}[/blue]")

  def debug(self, message: str) -> None:
    """Log debug information (white)."""
    self._console.print(f"[white]\\[{self._prefix}] {message}[/white]")

  def thinking(self, message: str) -> None:
    """Log model thinking output (dim)."""
    self._console.print(f"[dim]\\[{self._prefix}] {message}[/dim]")

  def trace(self, message: str) -> None:
    """Log low-level debug information (grey70)."""
    self._console.print(f"[grey70]\\[{self._prefix}] {message}[/grey70]")


class ActivityLog:
  """Concurrency-safe terminal logger for reasoning and screenshots."""

  def __init__(self) -> None:
    self._console = Console()

    # Static category loggers
    self.auth = CategoryLogger(self._console, "auth")
    self.stage = CategoryLogger(self._console, "stage")
    self.normalizer = CategoryLogger(self._console, "normalizer")
    self.denature = CategoryLogger(self._console, "denature")
    self.unrestricted = CategoryLogger(self._console, "unrestricted")

  def agent(self, label: str) -> CategoryLogger:
    """Create a logger for a specific agent."""
    return CategoryLogger(self._console, label)

  def prefix(self, name: str) -> CategoryLogger:
    """Create a logger with a custom prefix."""
    return CategoryLogger(self._console, name)

  # Root-level semantic methods (no prefix)
  def operation(self, message: str) -> None:
    """Log an operation in progress (cyan)."""
    self._console.print(f"[cyan]{message}[/cyan]")

  def success(self, message: str) -> None:
    """Log a successful completion (green)."""
    self._console.print(f"[green]{message}[/green]")

  def warning(self, message: str) -> None:
    """Log a warning or unusual state (yellow)."""
    self._console.print(f"[yellow]{message}[/yellow]")

  def important(self, message: str) -> None:
    """Log important data or information (magenta)."""
    self._console.print(f"[magenta]{message}[/magenta]")

  def failure(self, message: str) -> None:
    """Log an error or failure (red)."""
    self._console.print(f"[red]{message}[/red]")

  def starting(self, message: str) -> None:
    """Log the start of a process (blue)."""
    self._console.print(f"[blue]{message}[/blue]")

  def debug(self, message: str) -> None:
    """Log debug information (white)."""
    self._console.print(f"[white]{message}[/white]")

  def thinking(self, message: str) -> None:
    """Log model thinking output (dim)."""
    self._console.print(f"[dim]{message}[/dim]")

  def trace(self, message: str) -> None:
    """Log low-level debug information (grey70)."""
    self._console.print(f"[grey70]{message}[/grey70]")

  def print_reasoning(self, *, label: str | None, turn_index: int, table: Table) -> None:
    if label:
      self._console.print(f"[bold green]{label}[/bold green] — Turn {turn_index}")
    self._console.print(table, end="\n\n")

  def show_screenshot(
    self,
    *,
    label: str | None,
    action_name: str,
    url: str,
    png_bytes: bytes,
  ) -> None:
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
