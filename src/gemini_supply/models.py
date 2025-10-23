from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal, TYPE_CHECKING

from gemini_supply.computers import ScreenSize
from gemini_supply.config import ConcurrencyConfig
from gemini_supply.grocery.types import (
  ItemAddedResult,
  ItemNotFoundResult,
  ShoppingSummary,
)
from gemini_supply.preferences.types import ProductChoice, ProductDecision

if TYPE_CHECKING:
  from gemini_supply.grocery import ShoppingListItem, ShoppingListProvider
  from gemini_supply.preferences import PreferenceItemSession


def _empty_added_results() -> list[ItemAddedResult]:
  return []


def _empty_not_found_results() -> list[ItemNotFoundResult]:
  return []


def _empty_str_list() -> list[str]:
  return []


@dataclass(slots=True)
class AddedOutcome:
  result: ItemAddedResult
  used_default: bool = False
  starred_default: bool = False
  type: Literal["added"] = "added"


@dataclass(slots=True)
class NotFoundOutcome:
  result: ItemNotFoundResult
  type: Literal["not_found"] = "not_found"


@dataclass(slots=True)
class FailedOutcome:
  error: str
  type: Literal["failed"] = "failed"


Outcome = AddedOutcome | NotFoundOutcome | FailedOutcome


@dataclass(slots=True)
class ShoppingResults:
  added_items: list[ItemAddedResult] = field(default_factory=_empty_added_results)
  not_found_items: list[ItemNotFoundResult] = field(default_factory=_empty_not_found_results)
  out_of_stock_items: list[str] = field(default_factory=_empty_str_list)
  duplicate_items: list[str] = field(default_factory=_empty_str_list)
  failed_items: list[str] = field(default_factory=_empty_str_list)
  total_cost_cents: int = 0
  default_filled_items: list[str] = field(default_factory=_empty_str_list)
  new_default_items: list[str] = field(default_factory=_empty_str_list)

  def record(self, outcome: Outcome) -> None:
    if isinstance(outcome, AddedOutcome):
      self.added_items.append(outcome.result)
      self.total_cost_cents += outcome.result.price_cents
      if outcome.used_default:
        self.default_filled_items.append(outcome.result.item_name)
      if outcome.starred_default:
        self.new_default_items.append(outcome.result.item_name)
    elif isinstance(outcome, NotFoundOutcome):
      self.not_found_items.append(outcome.result)
    elif isinstance(outcome, FailedOutcome):
      self.failed_items.append(outcome.error)

  def to_summary(self) -> ShoppingSummary:
    return ShoppingSummary(
      added_items=list(self.added_items),
      not_found_items=list(self.not_found_items),
      out_of_stock_items=list(self.out_of_stock_items),
      duplicate_items=list(self.duplicate_items),
      failed_items=list(self.failed_items),
      total_cost_cents=self.total_cost_cents,
      total_cost_text=f"${self.total_cost_cents / 100:.2f}",
      default_fills=list(self.default_filled_items),
      new_defaults=list(self.new_default_items),
    )


@dataclass(slots=True)
class ShoppingSettings:
  model_name: str
  screen_size: ScreenSize
  time_budget: timedelta
  max_turns: int
  concurrency: ConcurrencyConfig


@dataclass(slots=True)
class ShoppingSession:
  """Manages the shopping workflow for a single item, providing tool methods for the agent."""

  item: ShoppingListItem
  provider: ShoppingListProvider
  preference_session: PreferenceItemSession
  result: ItemAddedResult | ItemNotFoundResult | None = None

  def report_item_added(
    self, item_name: str, price_text: str, url: str, quantity: int = 1
  ) -> ItemAddedResult:
    """Report success adding an item to the cart.

    Args:
      item_name: Name of the product added
      price_text: Formatted price string (e.g., "$12.34")
      url: Product page URL
      quantity: Number of units added (default: 1)

    Returns:
      ItemAddedResult with all details including computed price_cents
    """
    self.result = ItemAddedResult(
      item_name=item_name,
      price_text=price_text,
      url=url,
      quantity=quantity,
    )
    self.provider.mark_completed(self.item.id, self.result)
    asyncio.run(self.preference_session.record_success(self.result))
    return self.result

  def report_item_not_found(self, item_name: str, explanation: str) -> ItemNotFoundResult:
    """Report that an item could not be located.

    Args:
      item_name: Name of the item that was not found
      explanation: Description of why the item couldn't be found

    Returns:
      ItemNotFoundResult with the details
    """
    self.result = ItemNotFoundResult(item_name=item_name, explanation=explanation)
    self.provider.mark_not_found(self.item.id, self.result)
    return self.result

  def request_product_choice(self, choices: list[ProductChoice]) -> ProductDecision:
    """Request human input to choose a preferred product.

    Args:
      choices: Up to 10 structured product options containing title, price, and URL

    Returns:
      ProductDecision describing the user's choice (selected index, alternate text, or skip)
    """
    decision = asyncio.run(self.preference_session.request_choice(choices))

    # Handle skip decision immediately without involving the agent further
    if decision.decision == "skip":
      self.report_item_not_found(
        self.item.name, "User chose to skip this item during product selection"
      )

    return decision
