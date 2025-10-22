from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Literal, Sequence

from gemini_supply.computers import ScreenSize
from gemini_supply.grocery import ShoppingListProvider, YAMLShoppingListProvider
from gemini_supply.grocery import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingSummary,
)


class LoopStatus(StrEnum):
  COMPLETE = "COMPLETE"
  CONTINUE = "CONTINUE"


def _empty_added_results() -> list[ItemAddedResult]:
  return []


def _empty_not_found_results() -> list[ItemNotFoundResult]:
  return []


def _empty_str_list() -> list[str]:
  return []


@dataclass(slots=True)
class AddedOutcome:
  result: ItemAddedResult
  used_default: bool = False
  starred_default: bool = False
  type: Literal["added"] = "added"


@dataclass(slots=True)
class NotFoundOutcome:
  result: ItemNotFoundResult
  type: Literal["not_found"] = "not_found"


@dataclass(slots=True)
class FailedOutcome:
  error: str
  type: Literal["failed"] = "failed"


Outcome = AddedOutcome | NotFoundOutcome | FailedOutcome


@dataclass(slots=True)
class ShoppingResults:
  added_items: list[ItemAddedResult] = field(default_factory=_empty_added_results)
  not_found_items: list[ItemNotFoundResult] = field(default_factory=_empty_not_found_results)
  out_of_stock_items: list[str] = field(default_factory=_empty_str_list)
  duplicate_items: list[str] = field(default_factory=_empty_str_list)
  failed_items: list[str] = field(default_factory=_empty_str_list)
  total_cost_cents: int = 0
  default_filled_items: list[str] = field(default_factory=_empty_str_list)
  new_default_items: list[str] = field(default_factory=_empty_str_list)

  def record(self, outcome: Outcome) -> None:
    if isinstance(outcome, AddedOutcome):
      self.added_items.append(outcome.result)
      self.total_cost_cents += outcome.result.price_cents
      if outcome.used_default:
        self.default_filled_items.append(outcome.result.item_name)
      if outcome.starred_default:
        self.new_default_items.append(outcome.result.item_name)
    elif isinstance(outcome, NotFoundOutcome):
      self.not_found_items.append(outcome.result)
    elif isinstance(outcome, FailedOutcome):
      self.failed_items.append(outcome.error)

  def to_summary(self) -> ShoppingSummary:
    return ShoppingSummary(
      added_items=list(self.added_items),
      not_found_items=list(self.not_found_items),
      out_of_stock_items=list(self.out_of_stock_items),
      duplicate_items=list(self.duplicate_items),
      failed_items=list(self.failed_items),
      total_cost_cents=self.total_cost_cents,
      total_cost_text=f"${self.total_cost_cents / 100:.2f}",
      default_fills=list(self.default_filled_items),
      new_defaults=list(self.new_default_items),
    )


@dataclass(slots=True)
class ConcurrencySetting:
  requested: int | Literal["len"] | None
  config_fallback: int | Literal["len"] | None

  @classmethod
  def from_inputs(
    cls, cli_value: int | Literal["len"] | None, config_value: int | Literal["len"] | None
  ) -> ConcurrencySetting:
    return cls(requested=cli_value, config_fallback=config_value)

  def resolve(self, items: Sequence[ShoppingListItem], provider: ShoppingListProvider) -> int:
    base = self._base_value()
    effective = self._materialize_len(base, len(items))
    return self._apply_provider_caps(effective, provider)

  def _base_value(self) -> int | Literal["len"]:
    if self.requested == "len":
      return "len"
    if isinstance(self.requested, int) and self.requested > 0:
      return self.requested
    if self.config_fallback == "len":
      return "len"
    if isinstance(self.config_fallback, int) and self.config_fallback > 0:
      return self.config_fallback
    return 1

  @staticmethod
  def _materialize_len(base: int | Literal["len"], item_count: int) -> int:
    if base == "len":
      return 1 if item_count <= 0 else min(item_count, 20)
    return base

  @staticmethod
  def _apply_provider_caps(value: int, provider: ShoppingListProvider) -> int:
    if isinstance(provider, YAMLShoppingListProvider) and value > 1:
      import termcolor

      termcolor.cprint(
        "YAML provider does not support parallel writes; forcing concurrency=1.",
        color="yellow",
      )
      return 1
    return value


@dataclass(slots=True)
class ShoppingSettings:
  model_name: str
  highlight_mouse: bool
  screen_size: ScreenSize
  time_budget: timedelta
  max_turns: int
  postal_code: str
  concurrency: ConcurrencySetting


__all__ = [
  "LoopStatus",
  "AddedOutcome",
  "NotFoundOutcome",
  "FailedOutcome",
  "Outcome",
  "ShoppingResults",
  "ConcurrencySetting",
  "ShoppingSettings",
]
