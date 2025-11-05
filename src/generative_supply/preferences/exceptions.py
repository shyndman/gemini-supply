from __future__ import annotations

from dataclasses import dataclass

from .types import NormalizedItem


@dataclass(slots=True)
class OverrideRequest:
  """Details about a user-specified override of a shopping list entry."""

  previous_text: str
  override_text: str
  normalized: NormalizedItem
  source: str = "telegram"
  supersedes_original: bool = True
