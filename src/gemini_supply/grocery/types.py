from typing import TypedDict

from enum import StrEnum

from pydantic import BaseModel, Field


class ItemAddedResult(TypedDict):
  item_name: str
  price_text: str
  price_cents: int
  url: str
  quantity: int


class ItemNotFoundResult(TypedDict):
  item_name: str
  explanation: str


class ItemAddedResultModel(BaseModel):
  item_name: str
  price_text: str
  price_cents: int = Field(ge=0)
  url: str
  quantity: int = 1

  def to_typed(self) -> ItemAddedResult:
    return ItemAddedResult(
      item_name=self.item_name,
      price_text=self.price_text,
      price_cents=self.price_cents,
      url=self.url,
      quantity=self.quantity,
    )


class ItemNotFoundResultModel(BaseModel):
  item_name: str
  explanation: str

  def to_typed(self) -> ItemNotFoundResult:
    return ItemNotFoundResult(item_name=self.item_name, explanation=self.explanation)


class ItemStatus(StrEnum):
  NEEDS_ACTION = "needs_action"
  COMPLETED = "completed"


class ShoppingListItem(TypedDict):
  id: str
  name: str
  status: ItemStatus
  # Optional provider-specific fields can be added by provider implementation


class ShoppingSummary(TypedDict):
  added_items: list[ItemAddedResult]
  not_found_items: list[ItemNotFoundResult]
  failed_items: list[str]
  total_cost_cents: int
  total_cost_text: str
