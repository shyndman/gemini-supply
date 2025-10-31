from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from gemini_supply.grocery import ItemAddedResult

from .exceptions import OverrideRequest, PreferenceOverrideRequested
from .messenger import TelegramPreferenceMessenger
from .normalizer import NormalizationAgent
from .store import PreferenceStore
from .types import (
  NormalizedItem,
  PreferenceMetadata,
  PreferenceRecord,
  ProductChoice,
  ProductChoiceRequest,
  ProductDecision,
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
      pref = await self._coordinator._get_preference(self._normalized.canonical_key())
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

  async def request_choice(self, choices: list[ProductChoice]) -> ProductDecision:
    messenger = self._coordinator.messenger
    if messenger is None:
      return ProductDecision(
        decision="skip",
        selected_index=None,
        selected_choice=None,
        message="Preference prompting is disabled; proceeding without selection.",
        make_default=False,
      )
    self._prompt_invoked = True
    self._make_default_on_success = False
    request = ProductChoiceRequest(
      category_label=self._normalized.category,
      original_text=self._normalized.original_text,
      choices=choices,
    )
    result = await messenger.request_choice(request)
    if result.decision == "alternate":
      override_text = result.alternate_text
      if override_text is None:
        raise ValueError("alternate decision must include alternate_text")
      override = OverrideRequest(
        previous_text=self._normalized.original_text,
        override_text=override_text,
        normalized=self._normalized.model_copy(deep=True),
      )
      self._make_default_on_success = False
      raise PreferenceOverrideRequested(override)
    if result.decision == "selected" and result.make_default:
      self._make_default_on_success = True
    else:
      self._make_default_on_success = False
    return result

  async def record_success(self, added: ItemAddedResult) -> None:
    make_default = self._make_default_on_success
    self._make_default_on_success = False
    metadata = PreferenceMetadata(
      category_label=self._normalized.category,
      brand=self._normalized.brand,
    )
    if make_default:
      record = PreferenceRecord(
        product_name=added.item_name,
        metadata=metadata,
      )
      await self._coordinator.store.set(self._normalized.canonical_key(), record)
      self._cached_preference = record
      self._has_existing_preference = True


class _SentinelType:
  pass


_SENTINEL = _SentinelType()


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
