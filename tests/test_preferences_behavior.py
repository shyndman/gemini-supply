from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest

from gemini_supply.grocery import (
  HomeAssistantShoppingListProvider,
  ItemAddedResult,
  ShoppingSummary,
)
from gemini_supply.models import AddedOutcome, ShoppingResults
from gemini_supply.orchestrator import _is_specific_request
from gemini_supply.preferences import (
  NormalizationAgent,
  NormalizedItem,
  PreferenceCoordinator,
  PreferenceItemSession,
  PreferenceRecord,
  PreferenceStore,
  ProductChoice,
  ProductChoiceRequest,
  ProductDecision,
  TelegramPreferenceMessenger,
  TelegramSettings,
)


class _DummyNormalizer:
  async def normalize(self, item_text: str) -> NormalizedItem:  # pragma: no cover - unused
    raise NotImplementedError


class _FakeStore:
  def __init__(self) -> None:
    self.saved: dict[str, PreferenceRecord] = {}

  async def get(self, canonical_key: str) -> PreferenceRecord | None:
    return self.saved.get(canonical_key)

  async def set(self, canonical_key: str, record: PreferenceRecord) -> None:
    self.saved[canonical_key] = record


class _FakeMessenger:
  def __init__(self, make_default: bool) -> None:
    self._make_default = make_default

  async def request_choice(self, request: ProductChoiceRequest) -> ProductDecision:
    _ = request
    return ProductDecision(
      decision="selected",
      selected_index=1,
      selected_choice=None,
      make_default=self._make_default,
    )


def _normalized_item(
  brand: str | None = None, qualifiers: list[str] | None = None
) -> NormalizedItem:
  return NormalizedItem(
    category="Milk",
    quantity=1,
    brand=brand,
    qualifiers=qualifiers or [],
    original_text="Milk",
  )


def _added_result() -> ItemAddedResult:
  return ItemAddedResult(
    item_name="Lactantia 1% Milk",
    price_text="$5.49",
    url="https://example.com/milk",
    quantity=1,
  )


@pytest.mark.asyncio
async def test_record_success_persists_when_marked_default() -> None:
  store = _FakeStore()
  coordinator = PreferenceCoordinator(
    normalizer=cast(NormalizationAgent, _DummyNormalizer()),
    store=cast(PreferenceStore, store),
    messenger=cast(TelegramPreferenceMessenger, _FakeMessenger(make_default=True)),
  )
  session = PreferenceItemSession(coordinator, _normalized_item())
  await session.request_choice(
    [
      ProductChoice(
        title="Option 1",
        price_text="$1.00",
        # url=HttpUrl("https://example.com/option1"),
      )
    ]
  )
  await session.record_success(_added_result())
  saved = store.saved.get("milk")
  assert saved is not None
  assert saved.product_name == "Lactantia 1% Milk"
  assert session.has_existing_preference


@pytest.mark.asyncio
async def test_record_success_skips_without_default_toggle() -> None:
  store = _FakeStore()
  coordinator = PreferenceCoordinator(
    normalizer=cast(NormalizationAgent, _DummyNormalizer()),
    store=cast(PreferenceStore, store),
    messenger=cast(TelegramPreferenceMessenger, _FakeMessenger(make_default=False)),
  )
  session = PreferenceItemSession(coordinator, _normalized_item())
  await session.request_choice(
    [
      ProductChoice(
        title="Option 1",
        price_text="$1.00",
        # url=HttpUrl("https://example.com/option1"),
      )
    ]
  )
  await session.record_success(_added_result())
  assert store.saved == {}


def test_is_specific_request_detects_brand_and_qualifiers() -> None:
  assert _is_specific_request(_normalized_item(brand="Lactantia")) is True
  assert _is_specific_request(_normalized_item(qualifiers=["unsalted"])) is True
  assert _is_specific_request(_normalized_item()) is False


def test_shopping_results_track_default_flags() -> None:
  results = ShoppingResults()
  results.record(
    AddedOutcome(
      result=_added_result(),
      used_default=True,
      starred_default=False,
    )
  )
  results.record(
    AddedOutcome(
      result=ItemAddedResult(
        item_name="Irrelevant Butter",
        price_text="$4.00",
        url="https://example.com/butter",
        quantity=1,
      ),
      used_default=False,
      starred_default=True,
    )
  )
  summary = results.to_summary()
  assert summary.default_fills == ["Lactantia 1% Milk"]
  assert summary.new_defaults == ["Irrelevant Butter"]


def test_home_assistant_summary_marks_default_notes() -> None:
  from gemini_supply.config import HomeAssistantShoppingListConfig

  config = HomeAssistantShoppingListConfig(
    provider="home_assistant",
    url="http://example",
    token="token",
  )
  provider = HomeAssistantShoppingListProvider(config=config, no_retry=True)
  summary = ShoppingSummary(
    added_items=[
      _added_result(),
      ItemAddedResult(
        item_name="Irrelevant Butter",
        price_text="$4.00",
        url="https://example.com/butter",
        quantity=1,
      ),
    ],
    not_found_items=[],
    out_of_stock_items=[],
    duplicate_items=[],
    failed_items=[],
    total_cost_cents=949,
    total_cost_text="$9.49",
    default_fills=["Lactantia 1% Milk"],
    new_defaults=["Irrelevant Butter"],
  )
  md = provider._format_summary(summary)
  assert "Lactantia 1% Milk (default)" in md
  assert "Irrelevant Butter (new default set)" in md


def test_format_option_block_outputs_markdown_lines() -> None:
  settings = TelegramSettings(bot_token="token", chat_id=123, nag_interval=timedelta(minutes=1))
  messenger = TelegramPreferenceMessenger(settings=settings, nag_strings=[])
  option = ProductChoice(
    title="2L Milk",
    price_text="$4.99",
    # url=HttpUrl("https://example.com/milk"),
  )
  block = messenger._format_choice_block(1, option)
  assert block[0] == "1. *2L Milk*"
  assert "Price:" in block[1]
  assert "$4\\.99" in block[1]
  assert block[-1].startswith("   [View Product]")


def test_format_acknowledgement_includes_price() -> None:
  settings = TelegramSettings(bot_token="token", chat_id=123, nag_interval=timedelta(minutes=1))
  messenger = TelegramPreferenceMessenger(settings=settings, nag_strings=[])
  ack = messenger._format_acknowledgement(
    "✅ Noted",
    ProductChoice(
      title="2L Milk",
      price_text="$4.99",
      # url=HttpUrl("https://example.com/milk"),
    ),
  )
  assert ack.startswith("✅ Noted *2L Milk*")
  assert "$4\\.99" in ack
