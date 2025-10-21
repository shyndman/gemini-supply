from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class NormalizedItem(BaseModel):
  model_config = ConfigDict(extra="forbid", frozen=True)

  canonical_key: str
  category_label: str
  original_text: str
  quantity: int = Field(default=1, ge=1)
  brand: str | None = None
  qualifiers: list[str] = Field(default_factory=list)

  @field_validator("canonical_key", "category_label", "original_text")
  @classmethod
  def _strip_required(cls, value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
      raise ValueError("value must be a non-empty string")
    return trimmed

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


class ProductOption(BaseModel):
  model_config = ConfigDict(extra="forbid", frozen=True)

  title: str
  url: str | None = None
  description: str | None = None
  notes: str | None = None
  price_text: str | None = None
  price_cents: int | None = Field(default=None, ge=0)

  @field_validator("title")
  @classmethod
  def _validate_title(cls, value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
      raise ValueError("title must be non-empty")
    return trimmed

  @field_validator("description", "notes", "price_text")
  @classmethod
  def _normalize_optional_string(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      return None
    return trimmed

  @field_validator("url")
  @classmethod
  def _normalize_url(cls, value: str | None) -> str | None:
    if value is None:
      return None
    trimmed = value.strip()
    if not trimmed:
      return None
    return trimmed

  @model_validator(mode="after")
  def _ensure_price_text_prefix(self) -> ProductOption:
    if self.price_text is not None and not self.price_text.startswith("$"):
      object.__setattr__(self, "price_text", f"${self.price_text}")
    return self


class ProductChoiceRequest(BaseModel):
  model_config = ConfigDict(extra="forbid", frozen=True)

  canonical_key: str
  category_label: str
  original_text: str
  options: list[ProductOption]

  @field_validator("canonical_key", "category_label", "original_text")
  @classmethod
  def _strip_required(cls, value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
      raise ValueError("value must be a non-empty string")
    return trimmed

  @model_validator(mode="after")
  def _limit_options(self) -> ProductChoiceRequest:
    if len(self.options) > 10:
      object.__setattr__(self, "options", self.options[:10])
    return self


class ProductChoiceResult(BaseModel):
  model_config = ConfigDict(extra="forbid")

  decision: Literal["selected", "alternate", "skip"]
  selected_index: int | None = Field(default=None, ge=1)
  selected_option: ProductOption | None = None
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
