from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel

from gemini_supply.utils.currency import parse_price_cents


class ItemAddedResult(BaseModel):
  item_name: str
  price_text: str
  quantity: int = 1

  def price_cents(self) -> int:
    """Computed price in cents from price_text."""
    return parse_price_cents(self.price_text)


class ItemNotFoundResult(BaseModel):
  item_name: str
  explanation: str


class ItemStatus(StrEnum):
  NEEDS_ACTION = "needs_action"
  COMPLETED = "completed"


@dataclass(slots=True)
class ShoppingListItem:
  id: str
  name: str
  status: ItemStatus


def _empty_added_results() -> list[ItemAddedResult]:
  return []


def _empty_not_found_results() -> list[ItemNotFoundResult]:
  return []


def _empty_str_list() -> list[str]:
  return []


@dataclass(slots=True)
class ShoppingSummary:
  added_items: list[ItemAddedResult] = field(default_factory=_empty_added_results)
  not_found_items: list[ItemNotFoundResult] = field(default_factory=_empty_not_found_results)
  out_of_stock_items: list[str] = field(default_factory=_empty_str_list)
  duplicate_items: list[str] = field(default_factory=_empty_str_list)
  failed_items: list[str] = field(default_factory=_empty_str_list)
  total_cost_cents: int = 0
  total_cost_text: str = "$0.00"
  default_fills: list[str] = field(default_factory=_empty_str_list)
  new_defaults: list[str] = field(default_factory=_empty_str_list)
