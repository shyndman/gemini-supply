from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, computed_field, field_validator, model_validator
from pydantic.types import StringConstraints

from gemini_supply.utils.currency import parse_price_cents

type NonEmptyString = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


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
  product_url: HttpUrl
  metadata: PreferenceMetadata = Field(default_factory=PreferenceMetadata)


class NormalizedItem(BaseModel):
  canonical_key: NonEmptyString
  category_label: NonEmptyString
  original_text: NonEmptyString
  quantity: int = Field(default=1, ge=1)
  brand: str | None = None
  qualifiers: list[str] = Field(default_factory=list)

  @field_validator("brand")
  @classmethod
  def _strip_optional(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      return None
    return trimmed

  @field_validator("qualifiers")
  @classmethod
  def _sanitize_qualifiers(cls, value: list[str]) -> list[str]:
    cleaned: list[str] = []
    for qualifier in value:
      trimmed = qualifier.strip()
      if trimmed:
        cleaned.append(trimmed)
    return cleaned


class ProductChoice(BaseModel):
  title: NonEmptyString
  """The title of the product."""
  url: HttpUrl
  """The URL of the product page."""
  price_text: NonEmptyString
  """The price of the product as a formatted string, e.g. "$12.34"."""

  @computed_field
  @property
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
