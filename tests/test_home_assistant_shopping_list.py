"""Tests for HomeAssistantShoppingListProvider to lock in behavior before refactoring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gemini_supply.config import HomeAssistantShoppingListConfig
from gemini_supply.grocery.home_assistant_shopping_list import (
  HomeAssistantShoppingListProvider,
)
from gemini_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ItemStatus,
  ShoppingSummary,
)


@pytest.fixture
def provider() -> HomeAssistantShoppingListProvider:
  """Create a provider instance for testing."""
  config = HomeAssistantShoppingListConfig(
    provider="home_assistant",
    url="http://localhost:8123",
    token="test-token",
  )
  return HomeAssistantShoppingListProvider(config=config, no_retry=False)


@pytest.fixture
def provider_no_retry() -> HomeAssistantShoppingListProvider:
  """Create a provider instance with no_retry=True."""
  config = HomeAssistantShoppingListConfig(
    provider="home_assistant",
    url="http://localhost:8123",
    token="test-token",
  )
  return HomeAssistantShoppingListProvider(config=config, no_retry=True)


class TestGetUncompletedItems:
  """Tests for get_uncompleted_items method."""

  async def test_returns_only_incomplete_items(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should only return items where complete=False."""
    with patch.object(provider, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="Milk", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="Eggs", status="completed"),
        _HomeAssistantItemModel(uid="3", summary="Bread", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      assert len(items) == 2
      assert items[0].name == "Milk"
      assert items[1].name == "Bread"

  async def test_filters_empty_names(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should skip items with empty or whitespace-only names."""
    with patch.object(provider, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="   ", status="needs_action"),
        _HomeAssistantItemModel(uid="3", summary="Milk", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      assert len(items) == 1
      assert items[0].name == "Milk"

  async def test_filters_items_without_ids(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should skip items that don't have an ID."""
    with patch.object(provider, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="", summary="Milk", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="Eggs", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      assert len(items) == 1
      assert items[0].name == "Eggs"

  async def test_deduplicates_items_case_insensitive(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should detect duplicates case-insensitively and tag them."""
    with (
      patch.object(provider, "_get_items") as mock_get,
      patch.object(provider, "_update_item") as mock_update,
    ):
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="Milk", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="MILK", status="needs_action"),
        _HomeAssistantItemModel(uid="3", summary="milk", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      # Only first occurrence should be returned
      assert len(items) == 1
      assert items[0].name == "Milk"

      # Duplicates should be tagged
      assert mock_update.call_count == 2
      mock_update.assert_any_call("2", {"name": "MILK #dupe", "status": "needs_action"})
      mock_update.assert_any_call("3", {"name": "milk #dupe", "status": "needs_action"})

  async def test_strips_tags_from_item_names(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should strip known tags from item names."""
    with patch.object(provider, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="Milk #not_found", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="Eggs #out_of_stock", status="needs_action"),
        _HomeAssistantItemModel(uid="3", summary="Bread #failed", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      assert len(items) == 3
      assert items[0].name == "Milk"
      assert items[1].name == "Eggs"
      assert items[2].name == "Bread"

  async def test_filters_tagged_items_when_no_retry(
    self, provider_no_retry: HomeAssistantShoppingListProvider
  ) -> None:
    """Should skip items with any tag when no_retry=True."""
    with patch.object(provider_no_retry, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="Milk", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="Eggs #not_found", status="needs_action"),
        _HomeAssistantItemModel(uid="3", summary="Bread #failed", status="needs_action"),
      ]

      items = await provider_no_retry.get_uncompleted_items()

      assert len(items) == 1
      assert items[0].name == "Milk"

  async def test_all_items_have_needs_action_status(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """All returned items should have NEEDS_ACTION status."""
    with patch.object(provider, "_get_items") as mock_get:
      from gemini_supply.grocery.home_assistant_shopping_list import _HomeAssistantItemModel

      mock_get.return_value = [
        _HomeAssistantItemModel(uid="1", summary="Milk", status="needs_action"),
        _HomeAssistantItemModel(uid="2", summary="Eggs", status="needs_action"),
      ]

      items = await provider.get_uncompleted_items()

      assert all(item.status == ItemStatus.NEEDS_ACTION for item in items)


class TestMarkCompleted:
  """Tests for mark_completed method."""

  async def test_strips_tags_and_marks_complete(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should strip tags and set complete=True."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk #not_found"
      result = ItemAddedResult(item_name="Milk", quantity=1, price_text="$4.99")

      await provider.mark_completed("item-123", result)

      mock_update.assert_called_once_with("item-123", {"name": "Milk", "status": "completed"})

  async def test_preserves_base_name(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should preserve the original base name without tags."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "x3 Apples"
      result = ItemAddedResult(item_name="Apples", quantity=3, price_text="$2.99")

      await provider.mark_completed("item-123", result)

      mock_update.assert_called_once_with("item-123", {"name": "x3 Apples", "status": "completed"})


class TestMarkNotFound:
  """Tests for mark_not_found method."""

  async def test_strips_tags_and_adds_not_found_tag(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should strip existing tags and add #not_found tag."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk #failed"
      result = ItemNotFoundResult(item_name="Milk", explanation="No matching products")

      await provider.mark_not_found("item-123", result)

      mock_update.assert_called_once_with(
        "item-123", {"name": "Milk #not_found", "status": "needs_action"}
      )

  async def test_keeps_status_needs_action(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should set status=needs_action."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk"
      result = ItemNotFoundResult(item_name="Milk", explanation="No matching products")

      await provider.mark_not_found("item-123", result)

      call_args = mock_update.call_args[0][1]
      assert call_args["status"] == "needs_action"


class TestMarkOutOfStock:
  """Tests for mark_out_of_stock method."""

  async def test_strips_tags_and_adds_out_of_stock_tag(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should strip existing tags and add #out_of_stock tag."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk"

      await provider.mark_out_of_stock("item-123")

      mock_update.assert_called_once_with(
        "item-123", {"name": "Milk #out_of_stock", "status": "needs_action"}
      )

  async def test_adds_to_internal_out_of_stock_list(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should add base name to internal _out_of_stock list."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item"),
    ):
      mock_get_name.return_value = "Milk"

      await provider.mark_out_of_stock("item-123")

      assert "Milk" in provider._out_of_stock


class TestMarkFailed:
  """Tests for mark_failed method."""

  async def test_adds_failed_tag_when_no_existing_tags(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should add #failed tag when no other tags present."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk"

      await provider.mark_failed("item-123", "Some error")

      mock_update.assert_called_once_with(
        "item-123", {"name": "Milk #failed", "status": "needs_action"}
      )

  async def test_does_not_add_failed_tag_when_existing_tags(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should not add #failed tag if another error tag exists."""
    with (
      patch.object(provider, "_get_item_name") as mock_get_name,
      patch.object(provider, "_update_item") as mock_update,
    ):
      mock_get_name.return_value = "Milk #not_found"

      await provider.mark_failed("item-123", "Some error")

      # Should not be called because item already has a tag
      mock_update.assert_not_called()


class TestTagHelpers:
  """Tests for tag helper methods."""

  def test_strip_tags_removes_all_known_tags(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should remove all known tags from the end of a name."""
    assert provider._strip_tags("Milk #not_found") == "Milk"
    assert provider._strip_tags("Milk #out_of_stock") == "Milk"
    assert provider._strip_tags("Milk #failed") == "Milk"
    assert provider._strip_tags("Milk #dupe") == "Milk"
    assert provider._strip_tags("Milk #not_found #out_of_stock") == "Milk"

  def test_strip_tags_preserves_non_tag_text(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should not strip tags that appear in the middle of names."""
    assert provider._strip_tags("Milk") == "Milk"
    assert provider._strip_tags("x3 Apples") == "x3 Apples"

  def test_has_any_tag_detects_tags(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should detect presence of any known tag."""
    assert provider._has_any_tag("Milk #not_found") is True
    assert provider._has_any_tag("Milk #out_of_stock") is True
    assert provider._has_any_tag("Milk #failed") is True
    assert provider._has_any_tag("Milk #dupe") is True
    assert provider._has_any_tag("Milk") is False

  async def test_apply_tags_in_correct_order(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should apply tags in the defined order."""
    assert provider._apply_tags("Milk", {"#failed", "#not_found"}) == "Milk #not_found #failed"
    assert provider._apply_tags("Milk", {"#dupe", "#out_of_stock"}) == "Milk #out_of_stock #dupe"

  def test_apply_tags_returns_base_when_no_tags(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should return base name when no tags to apply."""
    assert provider._apply_tags("Milk", set()) == "Milk"


class TestQuantityParsing:
  """Tests for _parse_quantity method."""

  def test_parses_x_prefix(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should parse 'xN' quantity prefix."""
    assert provider._parse_quantity("x3 Apples") == ("Apples", 3)
    assert provider._parse_quantity("x1 Apple") == ("Apple", 1)

  def test_parses_x_suffix(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should parse 'Nx' quantity suffix."""
    assert provider._parse_quantity("3x Apples") == ("Apples", 3)
    assert provider._parse_quantity("Apples 3x") == ("Apples", 3)

  def test_parses_parentheses(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should parse '(N)' quantity notation."""
    assert provider._parse_quantity("Apples (3)") == ("Apples", 3)

  def test_parses_leading_number(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should parse leading number as quantity."""
    assert provider._parse_quantity("3 Apples") == ("Apples", 3)

  def test_parses_trailing_number(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should parse trailing number as quantity."""
    assert provider._parse_quantity("Apples 3") == ("Apples", 3)

  def test_defaults_to_quantity_one(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should default to quantity 1 when no quantity specified."""
    assert provider._parse_quantity("Apples") == ("Apples", 1)
    assert provider._parse_quantity("Fresh Milk") == ("Fresh Milk", 1)

  def test_enforces_minimum_quantity_one(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should enforce minimum quantity of 1."""
    assert provider._parse_quantity("x0 Apples") == ("Apples", 1)


class TestSummaryFormatting:
  """Tests for send_summary and _format_summary methods."""

  def test_format_summary_includes_timestamp(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should include a timestamp in the summary."""
    summary = ShoppingSummary(
      added_items=[],
      not_found_items=[],
      failed_items=[],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Run:" in formatted

  def test_format_summary_includes_added_items(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should list added items with quantities."""
    summary = ShoppingSummary(
      added_items=[
        ItemAddedResult(item_name="x3 Apples", quantity=3, price_text="$2.99"),
        ItemAddedResult(item_name="Milk", quantity=1, price_text="$4.99"),
      ],
      not_found_items=[],
      failed_items=[],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Added to Cart" in formatted
    assert "Apples ×3" in formatted
    assert "Milk\n" in formatted

  def test_format_summary_shows_default_annotations(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should annotate default and new default items."""
    summary = ShoppingSummary(
      added_items=[
        ItemAddedResult(item_name="Milk", quantity=1, price_text="$4.99"),
      ],
      not_found_items=[],
      failed_items=[],
      default_fills=["Milk"],
      new_defaults=["Milk"],
    )

    formatted = provider._format_summary(summary)

    assert "default" in formatted
    assert "new default set" in formatted

  def test_format_summary_includes_out_of_stock(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should include out of stock items from internal list."""
    provider._out_of_stock = ["Eggs", "Bread"]
    summary = ShoppingSummary(
      added_items=[],
      not_found_items=[],
      failed_items=[],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Out of Stock" in formatted
    assert "Eggs" in formatted
    assert "Bread" in formatted

  def test_format_summary_includes_not_found(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should include not found items."""
    summary = ShoppingSummary(
      added_items=[],
      not_found_items=[
        ItemNotFoundResult(item_name="Exotic Fruit", explanation="No products found"),
      ],
      failed_items=[],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Not Found" in formatted
    assert "Exotic Fruit" in formatted

  def test_format_summary_includes_duplicates(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should include duplicates from internal list."""
    provider._duplicates = ["Milk", "Eggs"]
    summary = ShoppingSummary(
      added_items=[],
      not_found_items=[],
      failed_items=[],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Duplicates" in formatted
    assert "Milk" in formatted
    assert "Eggs" in formatted

  def test_format_summary_includes_failed(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should include failed items."""
    summary = ShoppingSummary(
      added_items=[],
      not_found_items=[],
      failed_items=["Milk", "Eggs"],
      default_fills=[],
      new_defaults=[],
    )

    formatted = provider._format_summary(summary)

    assert "Failed" in formatted
    assert "Milk" in formatted
    assert "Eggs" in formatted

  async def test_send_summary_prints_when_activity(
    self, provider: HomeAssistantShoppingListProvider, capsys: pytest.CaptureFixture[str]
  ) -> None:
    """Should print summary when there's activity."""
    with patch.object(provider, "_notify_persistent"):
      summary = ShoppingSummary(
        added_items=[
          ItemAddedResult(item_name="Milk", quantity=1, price_text="$4.99"),
        ],
        not_found_items=[],
        failed_items=[],
        default_fills=[],
        new_defaults=[],
      )

      await provider.send_summary(summary)

      captured = capsys.readouterr()
      assert "Added to Cart" in captured.out

  async def test_send_summary_prints_no_activity_message(
    self, provider: HomeAssistantShoppingListProvider, capsys: pytest.CaptureFixture[str]
  ) -> None:
    """Should print 'no activity' message when nothing happened."""
    with patch.object(provider, "_notify_persistent"):
      summary = ShoppingSummary(
        added_items=[],
        not_found_items=[],
        failed_items=[],
        default_fills=[],
        new_defaults=[],
      )

      await provider.send_summary(summary)

      captured = capsys.readouterr()
      assert "No shopping activity" in captured.out

  async def test_send_summary_calls_notify_persistent(
    self, provider: HomeAssistantShoppingListProvider
  ) -> None:
    """Should call _notify_persistent with formatted markdown."""
    with patch.object(provider, "_notify_persistent") as mock_notify:
      summary = ShoppingSummary(
        added_items=[],
        not_found_items=[],
        failed_items=[],
        default_fills=[],
        new_defaults=[],
      )

      await provider.send_summary(summary)

      mock_notify.assert_called_once()
      call_args = mock_notify.call_args[0][0]
      assert isinstance(call_args, str)
      assert "Run:" in call_args


class TestInitialization:
  """Tests for provider initialization."""

  def test_normalizes_url(self) -> None:
    """Config should normalize URL via pydantic validators."""
    config = HomeAssistantShoppingListConfig(
      provider="home_assistant",
      url="http://localhost:8123/",
      token="test-token",
    )
    provider = HomeAssistantShoppingListProvider(config=config, no_retry=False)

    # URL should be accessible through config
    assert provider.config.url == "http://localhost:8123/"

  def test_initializes_accumulator_lists(self) -> None:
    """Should initialize empty accumulator lists."""
    config = HomeAssistantShoppingListConfig(
      provider="home_assistant",
      url="http://localhost:8123",
      token="test-token",
    )
    provider = HomeAssistantShoppingListProvider(config=config, no_retry=False)

    assert provider._duplicates == []
    assert provider._out_of_stock == []

  def test_headers_include_auth_token(self, provider: HomeAssistantShoppingListProvider) -> None:
    """Should include Bearer token in headers."""
    headers = provider._headers()

    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"
