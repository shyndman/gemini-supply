from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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


class HomeAssistantItemModel(BaseModel):
  model_config = ConfigDict(extra="allow", validate_assignment=True)

  id: str = ""
  name: str = ""
  complete: bool = False

  @field_validator("id", mode="before")
  @classmethod
  def _coerce_id(cls, value: object) -> str:
    if value is None:
      return ""
    return str(value)

  @field_validator("name", mode="before")
  @classmethod
  def _coerce_name(cls, value: object) -> str:
    if value is None:
      return ""
    return str(value)

  @field_validator("complete", mode="before")
  @classmethod
  def _coerce_complete(cls, value: object) -> bool:
    return bool(value)


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
        if "#404" not in tags:
          tags.append("#404")
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


# --- Home Assistant provider ---


@dataclass
class HomeAssistantShoppingListProvider:
  ha_url: str
  token: str
  no_retry: bool = False

  # Accumulators for summary sections this provider controls
  _duplicates: list[str] = None  # type: ignore[assignment]
  _out_of_stock: list[str] = None  # type: ignore[assignment]

  def __post_init__(self) -> None:
    self.ha_url = self.ha_url.rstrip("/")
    self._duplicates = []
    self._out_of_stock = []

  # --- Public API ---

  def get_uncompleted_items(self) -> list[ShoppingListItem]:
    items = self._get_items()
    ret: list[ShoppingListItem] = []
    seen: set[str] = set()
    for it in items:
      if it.complete:
        continue
      raw_name = it.name.strip()
      if not raw_name:
        continue
      # Skip retriable items if requested
      if self.no_retry and self._has_any_tag(raw_name):
        continue
      base = self._strip_tags(raw_name)
      norm = base.strip().lower()
      if norm in seen:
        # Tag as duplicate and skip processing
        self._tag_dupe(it.id, raw_name)
        continue
      seen.add(norm)
      if not it.id:
        continue
      ret.append(ShoppingListItem(id=it.id, name=base, status=ItemStatus.NEEDS_ACTION))
    return ret

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:
    # Strip error tags, keep quantity text if present in name (result has canonical item_name)
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    self._update_item(item_id, {"name": base, "complete": True})

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#not_found"})
    self._update_item(item_id, {"name": name, "complete": False})

  def mark_out_of_stock(self, item_id: str) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#out_of_stock"})
    self._update_item(item_id, {"name": name, "complete": False})
    self._out_of_stock.append(base)

  def mark_failed(self, item_id: str, error: str) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    # '#failed' is exclusive; only apply if no other error tags present
    if self._has_any_tag(current):
      # Already has another error tag; do not apply failed
      return
    name = self._apply_tags(base, {"#failed"})
    self._update_item(item_id, {"name": name, "complete": False})

  def send_summary(self, summary: ShoppingSummary) -> None:
    # Convert to markdown and send persistent notification
    md = self._format_summary(summary)
    # Print to stdout if anything happened; else short note
    has_activity = (
      bool(summary["added_items"])
      or bool(summary["not_found_items"])
      or bool(summary["failed_items"])
      or bool(self._duplicates)
      or bool(self._out_of_stock)
    )
    if has_activity:
      print(md)
    else:
      print("No shopping activity — nothing to report.")
    try:
      self._notify_persistent(md)
    except Exception:
      # Minimal logging only
      pass

  # --- Helpers ---

  def _headers(self) -> dict[str, str]:
    return {
      "Authorization": f"Bearer {self.token}",
      "Content-Type": "application/json",
    }

  def _get_items(self) -> list[HomeAssistantItemModel]:
    import json
    import urllib.request
    from urllib.error import HTTPError, URLError

    url = f"{self.ha_url}/api/shopping_list"
    req = urllib.request.Request(url, headers=self._headers(), method="GET")
    try:
      with urllib.request.urlopen(req, timeout=5) as resp:  # type: ignore[reportUnknownMemberType]
        raw_data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(raw_data, list):
          return []
        parsed: list[HomeAssistantItemModel] = []
        for entry in cast(list[object], raw_data):
          if not isinstance(entry, dict):
            continue
          try:
            parsed.append(HomeAssistantItemModel.model_validate(cast(dict[str, object], entry)))
          except ValidationError:
            continue
        return parsed
    except HTTPError as e:
      if e.code in (401, 403):
        raise RuntimeError(f"Home Assistant auth failed: HTTP {e.code}") from e
      return []
    except URLError:
      return []

  def _get_item_name(self, item_id: str) -> str:
    items = self._get_items()
    for it in items:
      if it.id == item_id:
        return it.name
    return ""

  def _update_item(self, item_id: str, fields: dict[str, object]) -> None:
    import json
    import urllib.request
    from urllib.error import HTTPError

    url = f"{self.ha_url}/api/shopping_list/item/{item_id}"
    data = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
    try:
      with urllib.request.urlopen(req, timeout=5):  # type: ignore[reportUnknownMemberType]
        pass
    except HTTPError as e:
      if e.code in (401, 403):
        raise RuntimeError(f"Home Assistant auth failed: HTTP {e.code}") from e
      # Minimal logging; ignore other errors

  def _notify_persistent(self, markdown: str) -> None:
    import json
    import urllib.request
    from urllib.error import HTTPError

    url = f"{self.ha_url}/api/services/persistent_notification/create"
    payload = {"title": "Grocery Shopping Complete", "message": markdown}
    req = urllib.request.Request(
      url,
      data=json.dumps(payload).encode("utf-8"),
      headers=self._headers(),
      method="POST",
    )
    try:
      with urllib.request.urlopen(req, timeout=5):  # type: ignore[reportUnknownMemberType]
        pass
    except HTTPError as e:
      if e.code in (401, 403):
        raise RuntimeError(f"Home Assistant auth failed: HTTP {e.code}") from e

  _TAG_ORDER: tuple[str, ...] = ("#not_found", "#out_of_stock", "#failed", "#dupe")

  def _strip_tags(self, name: str) -> str:
    parts = name.strip().split()
    # Remove trailing tags in known set
    while parts and parts[-1] in self._TAG_ORDER:
      parts.pop()
    return " ".join(parts).strip()

  def _has_any_tag(self, name: str) -> bool:
    return any(t in name.split() for t in self._TAG_ORDER)

  def _apply_tags(self, base: str, tags: set[str]) -> str:
    ordered = [t for t in self._TAG_ORDER if t in tags]
    if not ordered:
      return base
    return f"{base} {' '.join(ordered)}"

  def _tag_dupe(self, item_id: str, current_name: str) -> None:
    if not item_id:
      return
    base = self._strip_tags(current_name)
    tagged = self._apply_tags(base, {"#dupe"})
    self._update_item(item_id, {"name": tagged, "complete": False})
    self._duplicates.append(base)

  def _parse_quantity(self, name: str) -> tuple[str, int]:
    import re

    s = name.strip()
    # xN or Nx
    m = re.search(r"(?i)(?:^|\s)(?:x(\d+)|(\d+)x)(?:\s|$)", s)
    if m:
      q = int(m.group(1) or m.group(2))
      base = re.sub(r"(?i)(?:^|\s)(?:x\d+|\d+x)(?:\s|$)", " ", s).strip()
      return base, max(1, q)
    # (N)
    m = re.search(r"\((\d+)\)$", s)
    if m:
      q = int(m.group(1))
      base = re.sub(r"\(\d+\)$", "", s).strip()
      return base, max(1, q)
    # trailing or leading number
    m = re.search(r"^(\d+)\s+(.+)$", s)
    if m:
      return m.group(2).strip(), max(1, int(m.group(1)))
    m = re.search(r"^(.+?)\s+(\d+)$", s)
    if m:
      return m.group(1).strip(), max(1, int(m.group(2)))
    return s, 1

  def _format_summary(self, summary: ShoppingSummary) -> str:
    from datetime import datetime

    lines: list[str] = []
    ts = (
      datetime.now().strftime("%b %d, %Y %I:%M%p").lower().replace("am", "am").replace("pm", "pm")
    )
    lines.append(f"Run: {ts}\n\n")

    def fmt_list(header: str, items: list[str]) -> None:
      if not items:
        return
      lines.append(f"{header}\n")
      for name in items:
        base, qty = self._parse_quantity(name)
        qty_suf = f" ×{qty}" if qty > 1 else ""
        lines.append(f"- {base}{qty_suf}\n")
      lines.append("\n")

    # Added to Cart
    if summary["added_items"]:
      lines.append("Added to Cart\n")
      for it in summary["added_items"]:
        base, qty = self._parse_quantity(it["item_name"])
        qty_suf = f" ×{qty}" if qty > 1 else ""
        lines.append(f"- {base}{qty_suf}\n")
      lines.append("\n")

    # Out of Stock / Not Found from this run
    fmt_list("Out of Stock", self._out_of_stock)
    fmt_list("Not Found", [nf["item_name"] for nf in summary["not_found_items"]])
    fmt_list("Duplicates", self._duplicates)
    fmt_list("Failed", summary["failed_items"])

    return "".join(lines)
