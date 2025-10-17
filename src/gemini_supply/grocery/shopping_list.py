from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from typing import TypedDict

from .types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingListItem,
  ShoppingSummary,
  ItemStatus,
)


class ShoppingListProvider(Protocol):
  def get_uncompleted_items(self) -> list[ShoppingListItem]: ...

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None: ...

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None: ...

  def mark_failed(self, item_id: str, error: str) -> None: ...

  def send_summary(self, summary: ShoppingSummary) -> None: ...


@dataclass
class YAMLShoppingListProvider:
  path: Path

  def get_uncompleted_items(self) -> list[ShoppingListItem]:
    data = self._read()
    items: list[ShoppingListItem] = []
    for raw in data.get("items", []):
      status = str(raw.get("status", ItemStatus.NEEDS_ACTION.value))
      if status == ItemStatus.NEEDS_ACTION.value:
        items.append(
          ShoppingListItem(
            id=str(raw.get("id", raw.get("name", ""))),
            name=str(raw.get("name", "")),
            status=ItemStatus.NEEDS_ACTION,
          )
        )
    return items

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:
    data = self._read()
    for raw in data.get("items", []):
      if str(raw.get("id", raw.get("name", ""))) == item_id:
        raw["status"] = ItemStatus.COMPLETED.value
        raw["price_text"] = result["price_text"]
        raw["price_cents"] = result["price_cents"]
        raw["url"] = result["url"]
        raw["quantity"] = result["quantity"]
        break
    self._write(data)

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:
    data = self._read()
    for raw in data.get("items", []):
      if str(raw.get("id", raw.get("name", ""))) == item_id:
        # Add a #404 tag and explanation
        tags = list(raw.get("tags", []))
        if "#404" not in tags:
          tags.append("#404")
        raw["tags"] = tags
        raw["explanation"] = result["explanation"]
        break
    self._write(data)

  def mark_failed(self, item_id: str, error: str) -> None:
    data = self._read()
    for raw in data.get("items", []):
      if str(raw.get("id", raw.get("name", ""))) == item_id:
        tags = list(raw.get("tags", []))
        if "#failed" not in tags:
          tags.append("#failed")
        raw["tags"] = tags
        raw["error"] = error
        break
    self._write(data)

  def send_summary(self, summary: ShoppingSummary) -> None:
    # Write a plain text summary next to the list file as a simple baseline.
    out = self.path.with_suffix(".summary.txt")
    lines: list[str] = []
    lines.append("Shopping Summary\n")
    lines.append("Added:\n")
    for item in summary["added_items"]:
      lines.append(f"- {item['item_name']} x{item['quantity']} — {item['price_text']}\n")
    lines.append("\nNot Found:\n")
    for nf in summary["not_found_items"]:
      lines.append(f"- {nf['item_name']}: {nf['explanation']}\n")
    lines.append("\nFailed:\n")
    for f in summary["failed_items"]:
      lines.append(f"- {f}\n")
    lines.append(f"\nTotal: {summary['total_cost_text']}\n")
    out.write_text("".join(lines), encoding="utf-8")

  # --- Internal helpers ---

  class _YAMLData(TypedDict):
    items: list[dict[str, object]]

  def _read(self) -> _YAMLData:
    # Lazy import to avoid hard dependency if user hasn't installed YAML yet.
    try:
      import yaml  # type: ignore[reportMissingImports]
    except Exception as e:  # noqa: BLE001 - propagate with guidance
      raise RuntimeError(
        "YAML support not available. Please install PyYAML to use YAMLShoppingListProvider."
      ) from e

    if not self.path.exists():
      return YAMLShoppingListProvider._YAMLData(items=[])
    raw_text = self.path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text) or {}
    if not isinstance(loaded, dict):
      raise ValueError("Invalid YAML format: expected a mapping at the top level")
    # Coerce to YAMLData
    items_val = loaded.get("items", [])
    if not isinstance(items_val, list):
      items_val = []
    return YAMLShoppingListProvider._YAMLData(items=items_val)

  def _write(self, data: _YAMLData) -> None:
    try:
      import yaml  # type: ignore[reportMissingImports]
    except Exception as e:  # noqa: BLE001
      raise RuntimeError(
        "YAML support not available. Please install PyYAML to use YAMLShoppingListProvider."
      ) from e
    parent = self.path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with self.path.open("w", encoding="utf-8") as fh:
      yaml.safe_dump({"items": data["items"]}, fh, sort_keys=False, allow_unicode=True)
