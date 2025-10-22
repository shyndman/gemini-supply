from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gemini_supply.grocery import (
  ItemAddedResult,
  ItemNotFoundResult,
  ItemStatus,
  ShoppingListItem,
  ShoppingSummary,
  YAMLShoppingListProvider,
)
from gemini_supply.shopping import ConcurrencySetting


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
  setting = ConcurrencySetting.from_inputs(cli_value=4, config_value=2)
  value = setting.resolve(_items(10), StubProvider())
  assert value == 4


def test_concurrency_uses_config_when_cli_zero() -> None:
  setting = ConcurrencySetting.from_inputs(cli_value=0, config_value=3)
  value = setting.resolve(_items(10), StubProvider())
  assert value == 3


def test_concurrency_len_caps_to_item_count() -> None:
  setting = ConcurrencySetting.from_inputs(cli_value="len", config_value=None)
  value = setting.resolve(_items(5), StubProvider())
  assert value == 5


def test_concurrency_len_caps_maximum() -> None:
  setting = ConcurrencySetting.from_inputs(cli_value="len", config_value=None)
  value = setting.resolve(_items(25), StubProvider())
  assert value == 20


def test_concurrency_len_empty_list_returns_one() -> None:
  setting = ConcurrencySetting.from_inputs(cli_value="len", config_value=None)
  value = setting.resolve([], StubProvider())
  assert value == 1


def test_yaml_provider_forces_single_concurrency(tmp_path: Path) -> None:
  yaml_provider = YAMLShoppingListProvider(path=tmp_path / "list.yaml")
  setting = ConcurrencySetting.from_inputs(cli_value=5, config_value=None)
  value = setting.resolve(_items(5), yaml_provider)
  assert value == 1
