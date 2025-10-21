from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ItemStatus,
  ShoppingListItem,
  ShoppingSummary,
)


class ShoppingListProvider(Protocol):
  def get_uncompleted_items(self) -> list[ShoppingListItem]: ...

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None: ...

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None: ...

  def mark_out_of_stock(self, item_id: str) -> None: ...

  def mark_failed(self, item_id: str, error: str) -> None: ...

  def send_summary(self, summary: ShoppingSummary) -> None: ...


class YAMLShoppingListItemModel(BaseModel):
  model_config = ConfigDict(extra="allow", validate_assignment=True)

  id: str | None = None
  name: str = ""
  status: ItemStatus = ItemStatus.NEEDS_ACTION
  tags: list[str] = Field(default_factory=list)
  explanation: str | None = None
  price_text: str | None = None
  price_cents: int | None = None
  url: str | None = None
  quantity: int | None = None
  error: str | None = None

  @field_validator("id", mode="before")
  @classmethod
  def _coerce_optional_str(cls, value: object) -> str | None:
    if value is None:
      return None
    return str(value)

  @field_validator("name", mode="before")
  @classmethod
  def _coerce_name(cls, value: object) -> str:
    if value is None:
      return ""
    return str(value)

  @field_validator("tags", mode="before")
  @classmethod
  def _coerce_tags(cls, value: object) -> list[str]:
    if value is None:
      return []
    if isinstance(value, list):
      return [str(item) for item in cast(list[object], value)]
    if isinstance(value, str):
      return [value]
    return []

  @field_validator("status", mode="before")
  @classmethod
  def _coerce_status(cls, value: object) -> ItemStatus:
    if isinstance(value, ItemStatus):
      return value
    if isinstance(value, str):
      try:
        return ItemStatus(value)
      except ValueError:
        return ItemStatus.NEEDS_ACTION
    return ItemStatus.NEEDS_ACTION

  @property
  def resolved_id(self) -> str:
    return self.id or self.name or ""


class YAMLShoppingListDocumentModel(BaseModel):
  model_config = ConfigDict(extra="allow", validate_assignment=True)

  @staticmethod
  def _empty_items() -> list[YAMLShoppingListItemModel]:
    return []

  items: list[YAMLShoppingListItemModel] = Field(default_factory=_empty_items)

  @field_validator("items", mode="before")
  @classmethod
  def _coerce_items(cls, value: object) -> list[dict[str, object]]:
    if value is None:
      return []
    if isinstance(value, list):
      typed_items: list[dict[str, object]] = []
      for item in cast(list[object], value):
        if isinstance(item, dict):
          typed_items.append(cast(dict[str, object], item))
      return typed_items
    return []


@dataclass
class YAMLShoppingListProvider:
  path: Path

  def get_uncompleted_items(self) -> list[ShoppingListItem]:
    data = self._read()
    items: list[ShoppingListItem] = []
    for raw in data.items:
      if raw.status != ItemStatus.NEEDS_ACTION:
        continue
      items.append(
        ShoppingListItem(
          id=raw.resolved_id,
          name=raw.name,
          status=ItemStatus.NEEDS_ACTION,
        )
      )
    return items

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:
    data = self._read()
    for raw in data.items:
      if raw.resolved_id == item_id:
        raw.status = ItemStatus.COMPLETED
        raw.price_text = result["price_text"]
        raw.price_cents = result["price_cents"]
        raw.url = result["url"]
        raw.quantity = result["quantity"]
        break
    self._write(data)

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:
    data = self._read()
    for raw in data.items:
      if raw.resolved_id == item_id:
        tags = list(raw.tags)
        if "#not_found" not in tags:
          tags.append("#not_found")
        raw.tags = tags
        raw.explanation = result["explanation"]
        break
    self._write(data)

  def mark_out_of_stock(self, item_id: str) -> None:
    data = self._read()
    for raw in data.items:
      if raw.resolved_id == item_id:
        tags = list(raw.tags)
        if "#out_of_stock" not in tags:
          tags.append("#out_of_stock")
        raw.tags = tags
        break
    self._write(data)

  def mark_failed(self, item_id: str, error: str) -> None:
    data = self._read()
    for raw in data.items:
      if raw.resolved_id == item_id:
        tags = list(raw.tags)
        if "#failed" not in tags:
          tags.append("#failed")
        raw.tags = tags
        raw.error = error
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

  def _read(self) -> YAMLShoppingListDocumentModel:
    # Lazy import to avoid hard dependency if user hasn't installed YAML yet.
    try:
      import yaml  # type: ignore[reportMissingImports]
    except Exception as e:  # noqa: BLE001 - propagate with guidance
      raise RuntimeError(
        "YAML support not available. Please install PyYAML to use YAMLShoppingListProvider."
      ) from e

    if not self.path.exists():
      return YAMLShoppingListDocumentModel()
    raw_text = self.path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw_text)
    if parsed is None:
      parsed_mapping: dict[str, object] = {}
    else:
      if not isinstance(parsed, dict):
        raise ValueError("Invalid YAML format: expected a mapping at the top level")
      parsed_mapping = cast(dict[str, object], parsed)
    try:
      return YAMLShoppingListDocumentModel.model_validate(parsed_mapping)
    except ValidationError as exc:
      raise ValueError("Invalid YAML format: unable to parse items") from exc

  def _write(self, data: YAMLShoppingListDocumentModel) -> None:
    try:
      import yaml  # type: ignore[reportMissingImports]
    except Exception as e:  # noqa: BLE001
      raise RuntimeError(
        "YAML support not available. Please install PyYAML to use YAMLShoppingListProvider."
      ) from e
    parent = self.path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with self.path.open("w", encoding="utf-8") as fh:
      yaml.safe_dump(
        data.model_dump(mode="python", exclude_none=True),
        fh,
        sort_keys=False,
        allow_unicode=True,
      )
