from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PreferenceMetadata(BaseModel):
  model_config = ConfigDict(extra="forbid")

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
  model_config = ConfigDict(extra="forbid")

  product_name: str
  product_url: str
  metadata: PreferenceMetadata = Field(default_factory=PreferenceMetadata)

  @field_validator("product_name", "product_url")
  @classmethod
  def _require_non_empty(cls, value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
      raise ValueError("value must be a non-empty string")
    return trimmed


class NormalizedItem(TypedDict):
  canonical_key: str
  category_label: str
  original_text: str
  quantity: int
  brand: str | None
  qualifiers: list[str]


class ProductOption(TypedDict, total=False):
  title: str
  url: str | None
  description: str | None
  notes: str | None


class ProductChoiceRequest(TypedDict):
  canonical_key: str
  category_label: str
  original_text: str
  options: list[ProductOption]


class ProductChoiceResult(TypedDict, total=False):
  decision: Literal["selected", "alternate", "skip"]
  selected_index: int | None
  selected_option: ProductOption | None
  alternate_text: str | None
  message: str | None
  make_default: bool
