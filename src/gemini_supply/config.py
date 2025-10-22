from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gemini_supply.shopping.models import ConcurrencySetting


DEFAULT_CONFIG_PATH = Path("~/.config/gemini-supply/config.yaml").expanduser()
DEFAULT_PREFERENCES_PATH = Path("~/.config/gemini-supply/preferences.yaml").expanduser()


def _trim(value: str | None) -> str | None:
  if value is None:
    return None
  trimmed = value.strip()
  if not trimmed:
    return None
  return trimmed


class YAMLShoppingListConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  provider: Literal["yaml"]
  path: Path

  @field_validator("path", mode="after")
  @classmethod
  def _expand_path(cls, value: Path) -> Path:
    return value.expanduser()


class HomeAssistantShoppingListConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  provider: Literal["home_assistant"]
  url: str
  token: str

  @field_validator("url", "token", mode="after")
  @classmethod
  def _normalize(cls, value: str) -> str:
    trimmed = _trim(value)
    if trimmed is None:
      raise ValueError("value must be a non-empty string")
    return trimmed


ShoppingListConfig = Annotated[
  YAMLShoppingListConfig | HomeAssistantShoppingListConfig,
  Field(discriminator="provider"),
]


class PreferencesTelegramConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  bot_token: str
  chat_id: int
  nag_minutes: float = 30.0

  @field_validator("bot_token", mode="after")
  @classmethod
  def _normalize_bot_token(cls, value: str) -> str:
    trimmed = _trim(value)
    if trimmed is None:
      raise ValueError("bot_token must be a non-empty string")
    return trimmed

  @field_validator("chat_id", mode="after")
  @classmethod
  def _validate_chat_id(cls, value: int) -> int:
    if value <= 0:
      raise ValueError("chat_id must be greater than zero")
    return value

  @field_validator("nag_minutes", mode="after")
  @classmethod
  def _validate_nag_minutes(cls, value: float) -> float:
    if value <= 0:
      raise ValueError("nag_minutes must be greater than zero")
    return value


class PreferencesConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  file: Path = Field(default=DEFAULT_PREFERENCES_PATH)
  telegram: PreferencesTelegramConfig
  normalizer_model: str
  normalizer_api_base_url: str
  normalizer_api_key: str | None = None

  @field_validator("file", mode="after")
  @classmethod
  def _expand_file(cls, value: Path) -> Path:
    return value.expanduser()

  @field_validator("normalizer_model", "normalizer_api_base_url", mode="after")
  @classmethod
  def _normalize_required_str(cls, value: str) -> str:
    trimmed = _trim(value)
    if trimmed is None:
      raise ValueError("value must be a non-empty string")
    return trimmed

  @field_validator("normalizer_api_key", mode="after")
  @classmethod
  def _normalize_optional_str(cls, value: str | None) -> str | None:
    return _trim(value)


class AppConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  shopping_list: ShoppingListConfig
  postal_code: str
  concurrency: ConcurrencySetting = Field(
    default_factory=lambda: ConcurrencySetting.from_inputs("len", None)
  )
  preferences: PreferencesConfig

  @field_validator("postal_code", mode="after")
  @classmethod
  def _normalize_postal_code(cls, value: str) -> str:
    trimmed = _trim(value)
    if trimmed is None:
      raise ValueError("postal_code must be provided")
    return trimmed.replace(" ", "").upper()

  @field_validator("concurrency", mode="before")
  @classmethod
  def _coerce_concurrency(cls, value: object) -> ConcurrencySetting:
    if value is None:
      return ConcurrencySetting.from_inputs("len", None)
    if isinstance(value, ConcurrencySetting):
      return value
    if isinstance(value, str):
      lowered = value.strip().lower()
      if lowered == "len":
        return ConcurrencySetting.from_inputs("len", None)
      try:
        value = int(lowered)
      except ValueError as exc:
        raise ValueError(
          "concurrency must be an integer greater than or equal to 1 or 'len'"
        ) from exc
    if isinstance(value, int):
      if value < 1:
        raise ValueError("concurrency must be an integer greater than or equal to 1")
      return ConcurrencySetting.from_inputs(value, None)
    raise ValueError("concurrency must be an integer or 'len'")


def load_config(path: Path | None) -> AppConfig:
  """Load config YAML, raising on any deviation."""
  p = (path or DEFAULT_CONFIG_PATH).expanduser()
  if not p.exists():
    raise FileNotFoundError(f"Config file not found: {p}")

  try:
    raw = p.read_text(encoding="utf-8")
  except Exception as exc:
    raise ValueError(f"Failed to read configuration from {p}") from exc

  try:
    data = yaml.safe_load(raw)
  except Exception as exc:
    raise ValueError(f"Failed to parse YAML from {p}") from exc

  if data is None:
    raise ValueError(f"Configuration file {p} is empty")
  if not isinstance(data, dict):
    raise ValueError(f"Configuration file {p} must contain a mapping at the top level")

  try:
    return AppConfig.model_validate(data)
  except ValidationError as exc:
    raise ValueError(f"Invalid configuration in {p}: {exc}") from exc
