from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass

from gemini_supply.grocery import ItemAddedResult

from .normalizer import NormalizationAgent
from .store import PreferenceStore
from .messenger import TelegramPreferenceMessenger
from .types import (
  NormalizedItem,
  PreferenceRecord,
  PreferenceMetadata,
  ProductChoiceRequest,
  ProductChoiceResult,
  ProductOption,
)


@dataclass(slots=True)
class PreferenceCoordinator:
  """Coordinates normalization, storage, and chat prompting."""

  normalizer: NormalizationAgent
  store: PreferenceStore
  messenger: TelegramPreferenceMessenger

  async def start(self) -> None:
    if self.messenger is not None:
      await self.messenger.start()

  async def stop(self) -> None:
    if self.messenger is not None:
      await self.messenger.stop()

  async def normalize_item(self, item_text: str) -> NormalizedItem:
    return await self.normalizer.normalize(item_text)

  def create_session(self, normalized: NormalizedItem) -> PreferenceItemSession:
    return PreferenceItemSession(self, normalized)

  async def _get_preference(self, canonical_key: str) -> PreferenceRecord | None:
    return await self.store.get(canonical_key)


class PreferenceItemSession:
  """Per-item helper around the shared coordinator."""

  def __init__(self, coordinator: PreferenceCoordinator, normalized: NormalizedItem) -> None:
    self._coordinator = coordinator
    self._normalized = normalized
    self._cached_preference: PreferenceRecord | _SentinelType = _SENTINEL
    self._has_existing_preference = False
    self._prompt_invoked = False
    self._make_default_on_success = False

  @property
  def normalized(self) -> NormalizedItem:
    return self._normalized

  @property
  def can_request_choice(self) -> bool:
    return self._coordinator.messenger is not None

  @property
  def has_existing_preference(self) -> bool:
    return self._has_existing_preference

  @property
  def prompted_user(self) -> bool:
    return self._prompt_invoked

  @property
  def make_default_pending(self) -> bool:
    return self._make_default_on_success

  async def existing_preference(self) -> PreferenceRecord | None:
    if self._cached_preference is _SENTINEL:
      pref = await self._coordinator._get_preference(self._normalized.canonical_key)
      if pref is not None:
        self._cached_preference = pref
        self._has_existing_preference = True
      else:
        self._has_existing_preference = False
        return None
    cached = self._cached_preference
    if isinstance(cached, PreferenceRecord):
      self._has_existing_preference = True
      return cached
    self._has_existing_preference = False
    return None

  async def request_choice(self, options: Sequence[Mapping[str, object]]) -> ProductChoiceResult:
    messenger = self._coordinator.messenger
    if messenger is None:
      return ProductChoiceResult(
        decision="skip",
        selected_index=None,
        selected_option=None,
        message="Preference prompting is disabled; proceeding without selection.",
        make_default=False,
      )
    self._prompt_invoked = True
    self._make_default_on_success = False
    coerced_options = _coerce_options(options)
    request = ProductChoiceRequest(
      canonical_key=self._normalized.canonical_key,
      category_label=self._normalized.category_label,
      original_text=self._normalized.original_text,
      options=coerced_options[:10],
    )
    result = await messenger.request_choice(request)
    if result.decision == "selected" and result.make_default:
      self._make_default_on_success = True
    else:
      self._make_default_on_success = False
    return result

  async def record_success(self, added: ItemAddedResult, *, default_used: bool) -> None:
    _ = default_used  # Reserved for follow-up reporting/analytics.
    make_default = self._make_default_on_success
    self._make_default_on_success = False
    metadata = PreferenceMetadata(
      category_label=self._normalized.category_label,
      brand=self._normalized.brand,
    )
    if make_default:
      record = PreferenceRecord(
        product_name=added.item_name,
        product_url=added.url,
        metadata=metadata,
      )
      await self._coordinator.store.set(self._normalized.canonical_key, record)
      self._cached_preference = record
      self._has_existing_preference = True


class _SentinelType:
  pass


_SENTINEL = _SentinelType()


def _coerce_options(raw_options: Sequence[Mapping[str, object]]) -> list[ProductOption]:
  coerced: list[ProductOption] = []
  for idx, raw in enumerate(raw_options, start=1):
    title_val = raw.get("title") or raw.get("name") or raw.get("label") or f"Option {idx}"
    title = str(title_val).strip()
    if not title:
      title = f"Option {idx}"
    option_data: dict[str, object] = {"title": title}
    url_val = raw.get("url") or raw.get("href")
    if isinstance(url_val, str) and url_val.strip():
      option_data["url"] = url_val.strip()
    desc_val = raw.get("description") or raw.get("subtitle") or raw.get("notes")
    if isinstance(desc_val, str) and desc_val.strip():
      option_data["description"] = desc_val.strip()
    price_text_val = (
      raw.get("price_text") or raw.get("price") or raw.get("priceText") or raw.get("amount")
    )
    price_text = _normalize_price_text(price_text_val)
    price_cents_val = raw.get("price_cents") or raw.get("priceCents")
    price_cents = _normalize_price_cents(price_cents_val)
    if price_cents is None and price_text is not None:
      price_cents = _derive_price_cents_from_text(price_text)
    if price_text is None and price_cents is not None:
      price_text = f"${price_cents / 100:.2f}"
    if price_text is not None:
      option_data["price_text"] = price_text
    if price_cents is not None:
      option_data["price_cents"] = price_cents
    option = ProductOption.model_validate(option_data)
    coerced.append(option)
  return coerced


def _normalize_price_text(value: object) -> str | None:
  if not isinstance(value, str):
    return None
  text = value.strip()
  if not text:
    return None
  cleaned = text.replace("CAD", "").replace("cad", "").replace("\u00a0", " ").strip()
  return cleaned or None


def _normalize_price_cents(value: object) -> int | None:
  if isinstance(value, int) and value >= 0:
    return value
  if isinstance(value, str):
    stripped = value.strip()
    if stripped.isdigit():
      return int(stripped)
  return None


def _derive_price_cents_from_text(text: str) -> int | None:
  cleaned = text.strip()
  if not cleaned:
    return None
  normalized = (
    cleaned.replace("CAD", "")
    .replace("cad", "")
    .replace("$", "")
    .replace(",", "")
    .replace("\u00a0", "")
    .replace(" ", "")
    .strip()
  )
  if not normalized:
    return None
  try:
    decimal_value = Decimal(normalized)
  except InvalidOperation:
    return None
  cents = int((decimal_value * 100).quantize(Decimal("1")))
  if cents < 0:
    return None
  return cents
