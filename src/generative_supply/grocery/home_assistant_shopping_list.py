import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from generative_supply.config import HomeAssistantShoppingListConfig
from generative_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ItemStatus,
  ShoppingListItem,
  ShoppingSummary,
)


class _HomeAssistantItemModel(BaseModel):
  model_config = ConfigDict(extra="allow", validate_assignment=True)

  uid: str = ""
  summary: str = ""
  status: str = "needs_action"

  @field_validator("uid", mode="before")
  @classmethod
  def _coerce_uid(cls, value: object) -> str:
    if value is None:
      return ""
    return str(value)

  @field_validator("summary", mode="before")
  @classmethod
  def _coerce_summary(cls, value: object) -> str:
    if value is None:
      return ""
    return str(value)

  @field_validator("status", mode="before")
  @classmethod
  def _coerce_status(cls, value: object) -> str:
    if value is None:
      return "needs_action"
    s = str(value)
    # Normalize to standard values
    if s.lower() in ("completed", "complete", "true"):
      return "completed"
    return "needs_action"


class _TodoGetItemsResponse(BaseModel):
  """Response structure from todo.get_items service call."""

  model_config = ConfigDict(extra="allow")

  service_response: dict[str, "_EntityItemsData"]


def _create_empty_item_list() -> list[_HomeAssistantItemModel]:
  return []


class _EntityItemsData(BaseModel):
  """Data for a specific entity's items."""

  model_config = ConfigDict(extra="allow")

  items: list[_HomeAssistantItemModel] = Field(default_factory=_create_empty_item_list)


# --- Home Assistant provider ---

_str_list_factory = cast(Callable[[], list[str]], list)


@dataclass
class HomeAssistantShoppingListProvider:
  config: HomeAssistantShoppingListConfig
  no_retry: bool = False

  # Accumulators for summary sections this provider controls
  _duplicates: list[str] = field(default_factory=_str_list_factory, init=False)
  _out_of_stock: list[str] = field(default_factory=_str_list_factory, init=False)
  _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

  # --- Public API ---

  async def get_uncompleted_items(self) -> list[ShoppingListItem]:
    items = await self._get_items()
    ret: list[ShoppingListItem] = []
    seen: set[str] = set()
    for it in items:
      if it.status == "completed":
        continue
      raw_name = it.summary.strip()
      if not raw_name:
        continue
      # Skip retriable items if requested
      if self.no_retry and self._has_any_tag(raw_name):
        continue
      base = self._strip_tags(raw_name)
      norm = base.strip().lower()
      if norm in seen:
        # Tag as duplicate and skip processing
        await self._tag_dupe(it.uid, raw_name)
        continue
      seen.add(norm)
      if not it.uid:
        continue
      ret.append(ShoppingListItem(id=it.uid, name=base, status=ItemStatus.NEEDS_ACTION))
    return ret

  async def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:
    # Strip error tags, keep quantity text if present in name (result has canonical item_name)
    current = await self._get_item_name(item_id)
    base = self._strip_tags(current)
    await self._update_item(item_id, {"name": base, "status": "completed"})

  async def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:
    current = await self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#not_found"})
    await self._update_item(item_id, {"name": name, "status": "needs_action"})

  async def mark_out_of_stock(self, item_id: str) -> None:
    current = await self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#out_of_stock"})
    await self._update_item(item_id, {"name": name, "status": "needs_action"})
    async with self._lock:
      self._out_of_stock.append(base)

  async def mark_failed(self, item_id: str, error: str) -> None:
    current = await self._get_item_name(item_id)
    base = self._strip_tags(current)
    # '#failed' is exclusive; only apply if no other error tags present
    if self._has_any_tag(current):
      # Already has another error tag; do not apply failed
      return
    name = self._apply_tags(base, {"#failed"})
    await self._update_item(item_id, {"name": name, "status": "needs_action"})

  async def send_summary(self, summary: ShoppingSummary) -> None:
    # Convert to markdown and send persistent notification
    md = self._format_summary(summary)
    # Print to stdout if anything happened; else short note
    has_activity = (
      bool(summary.added_items)
      or bool(summary.not_found_items)
      or bool(summary.failed_items)
      or bool(self._duplicates)
      or bool(self._out_of_stock)
    )
    if has_activity:
      print(md)
    else:
      print("No shopping activity — nothing to report.")
    try:
      await self._notify_persistent(md)
    except Exception:
      # Minimal logging only
      pass

  # --- Helpers ---

  def _headers(self) -> dict[str, str]:
    return {
      "Authorization": f"Bearer {self.config.token}",
      "Content-Type": "application/json",
    }

  async def _get_items(self) -> list[_HomeAssistantItemModel]:
    url = f"{self.config.url}/api/services/todo/get_items?return_response"
    payload = {"entity_id": self.config.entity_id}
    # Short rationale: bubble HTTP/schema errors so operators see misconfigurations immediately.
    async with httpx.AsyncClient(timeout=5.0) as client:
      resp = await client.post(url, json=payload, headers=self._headers())
      resp.raise_for_status()
      raw_data = resp.json()
      response = _TodoGetItemsResponse.model_validate(raw_data)
      entity_data = response.service_response.get(self.config.entity_id)
      if entity_data is None:
        return []
      return entity_data.items

  async def _get_item_name(self, item_id: str) -> str:
    items = await self._get_items()
    for it in items:
      if it.uid == item_id:
        return it.summary
    return ""

  async def _update_item(self, item_uid: str, fields: dict[str, object]) -> None:
    url = f"{self.config.url}/api/services/todo/update_item"

    # Map old fields to new service parameters
    payload: dict[str, object] = {"entity_id": self.config.entity_id, "item": item_uid}

    if "name" in fields:
      payload["rename"] = fields["name"]
    if "status" in fields:
      payload["status"] = fields["status"]

    # Short rationale: keep writes strict; HA failures should halt the run.
    async with httpx.AsyncClient(timeout=5.0) as client:
      resp = await client.post(url, json=payload, headers=self._headers())
      resp.raise_for_status()

  async def _notify_persistent(self, markdown: str) -> None:
    url = f"{self.config.url}/api/services/persistent_notification/create"
    payload = {"title": "Grocery Shopping Complete", "message": markdown}
    try:
      async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
      if e.response.status_code in (401, 403):
        raise RuntimeError(f"Home Assistant auth failed: HTTP {e.response.status_code}") from e

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

  async def _tag_dupe(self, item_id: str, current_name: str) -> None:
    if not item_id:
      return
    base = self._strip_tags(current_name)
    tagged = self._apply_tags(base, {"#dupe"})
    await self._update_item(item_id, {"name": tagged, "status": "needs_action"})
    async with self._lock:
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
    ts = datetime.now().strftime("%b %d, %Y %I:%M%p").replace("am", "am").replace("pm", "pm")
    lines.append(f"Run: {ts}\n\n")
    default_names = set(summary.default_fills)
    new_default_names = set(summary.new_defaults)

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
    if summary.added_items:
      lines.append("Added to Cart\n")
      for it in summary.added_items:
        base, qty = self._parse_quantity(it.item_name)
        qty_suf = f" ×{qty}" if qty > 1 else ""
        annotations: list[str] = []
        if it.item_name in default_names:
          annotations.append("default")
        if it.item_name in new_default_names:
          annotations.append("new default set")
        note = f" ({', '.join(annotations)})" if annotations else ""
        lines.append(f"- {base}{qty_suf}{note}\n")
      lines.append("\n")

    # Out of Stock / Not Found from this run
    fmt_list("Out of Stock", self._out_of_stock)
    fmt_list("Not Found", [nf.item_name for nf in summary.not_found_items])
    fmt_list("Duplicates", self._duplicates)
    fmt_list("Failed", summary.failed_items)

    if summary.usage_entries:
      lines.append("Gemini Usage\n")
      for entry in summary.usage_entries:
        tokens = entry.token_usage
        lines.append(
          f"- {entry.category.value} ({entry.model_name}) » in={tokens.input_tokens:,} "
          f"out={tokens.output_tokens:,} cost={entry.cost.total_text}\n"
        )
      lines.append(f"Total Gemini Cost: {summary.usage_total_text}\n\n")

    return "".join(lines)
