from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from gemini_supply.config import HomeAssistantShoppingListConfig
from gemini_supply.grocery.types import (
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


class _EntityItemsData(BaseModel):
  """Data for a specific entity's items."""

  model_config = ConfigDict(extra="allow")

  items: list[_HomeAssistantItemModel] = []


# --- Home Assistant provider ---


@dataclass
class HomeAssistantShoppingListProvider:
  config: HomeAssistantShoppingListConfig
  no_retry: bool = False

  # Accumulators for summary sections this provider controls
  _duplicates: list[str] = None  # type: ignore[assignment]
  _out_of_stock: list[str] = None  # type: ignore[assignment]

  def __post_init__(self) -> None:
    self._duplicates = []
    self._out_of_stock = []

  # --- Public API ---

  def get_uncompleted_items(self) -> list[ShoppingListItem]:
    items = self._get_items()
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
        self._tag_dupe(it.uid, raw_name)
        continue
      seen.add(norm)
      if not it.uid:
        continue
      ret.append(ShoppingListItem(id=it.uid, name=base, status=ItemStatus.NEEDS_ACTION))
    return ret

  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None:
    # Strip error tags, keep quantity text if present in name (result has canonical item_name)
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    self._update_item(item_id, {"name": base, "status": "completed"})

  def mark_not_found(self, item_id: str, result: ItemNotFoundResult) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#not_found"})
    self._update_item(item_id, {"name": name, "status": "needs_action"})

  def mark_out_of_stock(self, item_id: str) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    name = self._apply_tags(base, {"#out_of_stock"})
    self._update_item(item_id, {"name": name, "status": "needs_action"})
    self._out_of_stock.append(base)

  def mark_failed(self, item_id: str, error: str) -> None:
    current = self._get_item_name(item_id)
    base = self._strip_tags(current)
    # '#failed' is exclusive; only apply if no other error tags present
    if self._has_any_tag(current):
      # Already has another error tag; do not apply failed
      return
    name = self._apply_tags(base, {"#failed"})
    self._update_item(item_id, {"name": name, "status": "needs_action"})

  def send_summary(self, summary: ShoppingSummary) -> None:
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
      self._notify_persistent(md)
    except Exception:
      # Minimal logging only
      pass

  # --- Helpers ---

  def _headers(self) -> dict[str, str]:
    return {
      "Authorization": f"Bearer {self.config.token}",
      "Content-Type": "application/json",
    }

  def _get_items(self) -> list[_HomeAssistantItemModel]:
    import json
    import urllib.request
    from urllib.error import HTTPError, URLError

    url = f"{self.config.url}/api/services/todo/get_items?return_response"
    payload = {"entity_id": self.config.entity_id}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
    try:
      with urllib.request.urlopen(req, timeout=5) as resp:  # type: ignore[reportUnknownMemberType]
        raw_data = json.loads(resp.read().decode("utf-8"))
        response = _TodoGetItemsResponse.model_validate(raw_data)
        entity_data = response.service_response.get(self.config.entity_id)
        if entity_data is None:
          return []
        return entity_data.items
    except HTTPError as e:
      if e.code in (401, 403):
        raise RuntimeError(f"Home Assistant auth failed: HTTP {e.code}") from e
      return []
    except (URLError, ValidationError):
      return []

  def _get_item_name(self, item_id: str) -> str:
    items = self._get_items()
    for it in items:
      if it.uid == item_id:
        return it.summary
    return ""

  def _update_item(self, item_uid: str, fields: dict[str, object]) -> None:
    import json
    import urllib.request
    from urllib.error import HTTPError

    url = f"{self.config.url}/api/services/todo/update_item"

    # Map old fields to new service parameters
    payload: dict[str, object] = {"entity_id": self.config.entity_id, "item": item_uid}

    if "name" in fields:
      payload["rename"] = fields["name"]
    if "status" in fields:
      payload["status"] = fields["status"]

    data = json.dumps(payload).encode("utf-8")
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

    url = f"{self.config.url}/api/services/persistent_notification/create"
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
    self._update_item(item_id, {"name": tagged, "status": "needs_action"})
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

    return "".join(lines)
