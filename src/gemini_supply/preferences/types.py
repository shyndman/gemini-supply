from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
  AfterValidator,
  BaseModel,
  Field,
  RootModel,
  field_validator,
  model_validator,
)
from pydantic.types import StringConstraints

from gemini_supply.utils.currency import parse_price_cents

type NonEmptyString = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


def _strip_trailing_of(value: str) -> str:
  if value.endswith(" of"):
    value = value[:-3]
  if not value:
    raise ValueError("unit_descriptor must not be empty")
  return value


type UnitDescriptorString = Annotated[
  str,
  StringConstraints(min_length=1, strip_whitespace=True),
  AfterValidator(_strip_trailing_of),
]


class PreferenceMetadata(BaseModel):
  category_label: str | None = None
  brand: str | None = None
  updated_at_iso: str | None = None

  @field_validator("category_label", "brand")
  @classmethod
  def _normalize_optional_text(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      return None
    return trimmed

  @field_validator("updated_at_iso")
  @classmethod
  def _normalize_timestamp(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      raise ValueError("updated_at_iso must not be blank if provided")
    return trimmed


class PreferenceRecord(BaseModel):
  product_name: NonEmptyString
  metadata: PreferenceMetadata = Field(default_factory=PreferenceMetadata)


class PreferenceStoreData(RootModel[dict[str, PreferenceRecord]]):
  """
  Represents the entire YAML preference store file structure.

  The root is a dictionary mapping canonical item keys (e.g., "milk", "cheese")
  to their corresponding preference records.
  """

  root: dict[str, PreferenceRecord]

  def get(self, canonical_key: str) -> PreferenceRecord | None:
    """Get a preference record by canonical key."""
    return self.root.get(canonical_key)

  def set(self, canonical_key: str, record: PreferenceRecord) -> None:
    """Set a preference record by canonical key."""
    self.root[canonical_key] = record

  def to_dict(self) -> dict[str, PreferenceRecord]:
    """Get the underlying dictionary."""
    return self.root


class _PartialNormalizedItem(BaseModel):
  quantity: int = Field(ge=1, description="The number of items requested.")
  quantity_string: NonEmptyString | None = Field(
    default=None,
    description="The exact quantity expression as written (e.g., '1x', '10 X', 'x6', '4', 'two'). Null if no quantity expression is present.",
  )
  unit_descriptor: UnitDescriptorString | None = Field(
    default=None,
    description="Unit or container descriptor if present (e.g., 'box of', 'loaf of', 'can of', 'bunch of'). Null if not specified.",
  )
  brand: NonEmptyString | None = Field(default=None, description="The brand name if specified.")
  category: NonEmptyString = Field(
    min_length=1, description="The general product category or type."
  )
  qualifiers: list[NonEmptyString] = Field(
    default_factory=list, description="Qualifiers removed from category."
  )

  def canonical_key(self) -> str:
    """Generate a canonical key for this normalized item."""
    return f"{self.category.strip().lower()}"


class NormalizedItem(_PartialNormalizedItem):
  original_text: NonEmptyString
  """The original item text as provided by the user."""


class ProductChoice(BaseModel):
  title: NonEmptyString
  """The title of the product."""
  # url: HttpUrl
  """The URL of the product page."""
  price_text: NonEmptyString
  """The price of the product as a formatted string, e.g. "$12.34"."""

  def price_cents(self) -> int:
    """Computed price in cents from price_text."""
    return parse_price_cents(self.price_text)

  @model_validator(mode="after")
  def _ensure_price_text_prefix(self) -> ProductChoice:
    if self.price_text is not None and not self.price_text.startswith("$"):
      self.price_text = f"${self.price_text}"
    return self


class ProductChoiceRequest(BaseModel):
  category_label: NonEmptyString
  original_text: NonEmptyString
  choices: list[ProductChoice]

  @model_validator(mode="after")
  def _limit_options(self) -> ProductChoiceRequest:
    if len(self.choices) > 10:
      self.choices = self.choices[:10]
    return self


class ProductDecision(BaseModel):
  # TODO We need to shave this down to what the agent actually needs Also, let's make this a
  # discriminated union (ie ProductDecision | SkipDecision | AlternateDecision) so we can be very
  # specific about the fields, and can make the fields non-null

  decision: Literal["selected", "alternate", "skip"]
  selected_index: int | None = Field(default=None, ge=1)
  selected_choice: ProductChoice | None = None
  alternate_text: str | None = None
  message: str | None = None
  make_default: bool = False

  @field_validator("alternate_text", "message")
  @classmethod
  def _normalize_optional_string(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      return None
    return trimmed
