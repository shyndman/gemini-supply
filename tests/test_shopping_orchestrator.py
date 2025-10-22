from __future__ import annotations

from dataclasses import dataclass

from gemini_supply.config import ConcurrencyConfig
from gemini_supply.grocery import (
  ItemAddedResult,
  ItemNotFoundResult,
  ItemStatus,
  ShoppingListItem,
  ShoppingSummary,
)


def _items(count: int) -> list[ShoppingListItem]:
  return [
    ShoppingListItem(
      id=f"item-{idx}",
      name=f"Item {idx}",
      status=ItemStatus.NEEDS_ACTION,
    )
    for idx in range(count)
  ]


@dataclass
class StubProvider:
  """Minimal provider stub for concurrency tests."""

  def get_uncompleted_items(self) -> list[ShoppingListItem]:  # pragma: no cover - not used
    return []

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:  # pragma: no cover
    raise NotImplementedError

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:  # pragma: no cover
    raise NotImplementedError

  def mark_out_of_stock(self, item_id: str) -> None:  # pragma: no cover - not used
    raise NotImplementedError

  def mark_failed(self, item_id: str, error: str) -> None:  # pragma: no cover - not used
    raise NotImplementedError

  def send_summary(self, summary: ShoppingSummary) -> None:  # pragma: no cover
    raise NotImplementedError


def test_concurrency_explicit_int() -> None:
  setting = ConcurrencyConfig(value=4)
  value = setting.resolve(10)
  assert value == 4


def test_concurrency_len_caps_to_item_count() -> None:
  setting = ConcurrencyConfig(value="len")
  value = setting.resolve(5)
  assert value == 5


def test_concurrency_len_caps_maximum() -> None:
  setting = ConcurrencyConfig(value="len")
  value = setting.resolve(25)
  assert value == 20


def test_concurrency_len_empty_list_returns_one() -> None:
  setting = ConcurrencyConfig(value="len")
  value = setting.resolve(0)
  assert value == 1
