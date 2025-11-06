from __future__ import annotations

from contextvars import ContextVar
from io import BytesIO

from PIL import Image as PILImage
from PIL.Image import Image as PILImageT
from PIL.Image import Resampling
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from terminaltexteffects import Gradient
from terminaltexteffects.effects.effect_laseretch import LaserEtch
from textual_image.renderable import Image as ConsoleImage


# Context variable for activity log
_activity_log: ContextVar[ActivityLog | None] = ContextVar("activity_log")


def activity_log() -> ActivityLog:
  """Get the current ActivityLog instance from context."""
  log = _activity_log.get()
  if log is None:
    raise RuntimeError("ActivityLog not initialized. Call set_activity_log() first.")
  return log


def set_activity_log(log: ActivityLog) -> None:
  """Set the ActivityLog instance for the current context."""
  _activity_log.set(log)


class CategoryLogger:
  """Prefixed logger delegate for a specific category."""

  def __init__(self, console: Console, prefix: str | None) -> None:
    self._console = console
    self._prefix = prefix

  def _format_with_prefix(self, message: str) -> str:
    if self._prefix:
      return f"[{self._prefix}] {message}"
    return message

  def operation(self, message: str) -> None:
    """Log an operation in progress (cyan)."""
    if self._prefix:
      self._console.print(f"[cyan]\\[{self._prefix}] {message}[/cyan]")
    else:
      self._console.print(f"[cyan]{message}[/cyan]")

  def success(self, message: str) -> None:
    """Log a successful completion (green)."""
    if self._prefix:
      self._console.print(f"[green]\\[{self._prefix}] {message}[/green]")
    else:
      self._console.print(f"[green]{message}[/green]")

  def warning(self, message: str) -> None:
    """Log a warning or unusual state (yellow)."""
    if self._prefix:
      self._console.print(f"[yellow]\\[{self._prefix}] {message}[/yellow]")
    else:
      self._console.print(f"[yellow]{message}[/yellow]")

  def important(self, message: str) -> None:
    """Log important data or information (magenta)."""
    if self._prefix:
      self._console.print(f"[magenta]\\[{self._prefix}] {message}[/magenta]")
    else:
      self._console.print(f"[magenta]{message}[/magenta]")

  def failure(self, message: str) -> None:
    """Log an error or failure (red)."""
    if self._prefix:
      self._console.print(f"[red]\\[{self._prefix}] {message}[/red]")
    else:
      self._console.print(f"[red]{message}[/red]")

  def starting(self, message: str) -> None:
    """Log the start of a process (blue)."""
    if self._prefix:
      self._console.print(f"[blue]\\[{self._prefix}] {message}[/blue]")
    else:
      self._console.print(f"[blue]{message}[/blue]")

  def debug(self, message: str) -> None:
    """Log debug information (white)."""
    if self._prefix:
      self._console.print(f"[white]\\[{self._prefix}] {message}[/white]")
    else:
      self._console.print(f"[white]{message}[/white]")

  def thinking(self, message: str) -> None:
    """Log model thinking output (table format)."""
    text = message.rstrip() or "(no details)"
    table = Table(show_header=False, box=box.SIMPLE, expand=True)
    table.add_column("Context", style="cyan", no_wrap=True)
    table.add_column("Details", style="white")
    context = self._format_with_prefix("Thinking")
    table.add_row(context, text)
    self._console.print(table, end="\n")

  def trace(self, message: str) -> None:
    """Log low-level debug information (grey70)."""
    if self._prefix:
      self._console.print(f"[grey70]\\[{self._prefix}] {message}[/grey70]")
    else:
      self._console.print(f"[grey70]{message}[/grey70]")


class ActivityLog:
  """Concurrency-safe terminal logger for reasoning and screenshots."""

  def __init__(self) -> None:
    self._console = Console()
    self._normalizer_prompt_logged = False
    self._agent_prompt_logged = False

    # Static category loggers
    self.auth = CategoryLogger(self._console, "auth")
    self.stage = CategoryLogger(self._console, "stage")
    self.normalizer = CategoryLogger(self._console, "normalizer")
    self.denature = CategoryLogger(self._console, "denature")
    self.unrestricted = CategoryLogger(self._console, "unrestricted")

  def agent(self, label: str | None) -> CategoryLogger:
    """Create a logger for a specific agent."""
    return CategoryLogger(self._console, label)

  def prefix(self, name: str | None) -> CategoryLogger:
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

  def log_normalizer_prompt(self, prompt: str) -> None:
    if self._normalizer_prompt_logged:
      self.normalizer.debug("Normalizer prompt suppressed (already shown this run).")
      return
    self._normalizer_prompt_logged = True
    panel = Panel.fit(
      prompt.strip(),
      title="[normalizer] Normalizer Prompt",
      border_style="magenta",
    )
    self._console.print(panel)

  def log_agent_prompt(self, agent_label: str | None, display_label: str, prompt: str) -> None:
    if self._agent_prompt_logged:
      self.agent(agent_label).debug(
        f"Computer-use prompt suppressed for '{display_label}' (already shown this run)."
      )
      return
    self._agent_prompt_logged = True
    label = agent_label or "agent"
    title = f"[{label}] Shopper Prompt: {display_label}"
    panel = Panel.fit(prompt.strip(), title=title, border_style="cyan")
    self._console.print(panel)

  def celebrate_addition(self, agent_label: str | None, banner_text: str) -> None:
    effect = LaserEtch(banner_text)
    effect.terminal_config.canvas_width = 0
    effect.terminal_config.canvas_height = 0
    effect.terminal_config.frame_rate = 60
    cfg = effect.effect_config
    cfg.etch_direction = "center_to_outside"
    cfg.final_gradient_direction = Gradient.Direction.HORIZONTAL
    with effect.terminal_output() as terminal:
      for frame in effect:
        terminal.print(frame)


def display_image_bytes_in_terminal(png_bytes: bytes) -> None:
  with PILImage.open(BytesIO(png_bytes)) as pil_image:
    pil_image.resize(
      size=(int(pil_image.width * 0.8), int(pil_image.height * 0.8)), resample=Resampling.BICUBIC
    )
    display_image_in_terminal(pil_image)


def display_image_in_terminal(image: PILImageT) -> None:
  with Console() as console:
    console.print(ConsoleImage(image))
