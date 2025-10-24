from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gemini_supply.utils.strings import trim

DEFAULT_CONFIG_PATH = Path("~/.config/gemini-supply/config.yaml").expanduser()
DEFAULT_PREFERENCES_PATH = Path("~/.config/gemini-supply/preferences.yaml").expanduser()
MAX_CONCURRENCY = 20


class ConcurrencyConfig(BaseModel):
  model_config = ConfigDict(frozen=True)

  value: int | Literal["len"]

  @classmethod
  def parse(cls, raw: str) -> ConcurrencyConfig:
    """Parse concurrency from a string value (either 'len' or a positive integer)."""
    trimmed = raw.strip().lower()
    if trimmed == "len":
      return cls(value="len")
    try:
      parsed = int(trimmed)
    except ValueError as exc:
      raise ValueError("concurrency must be a positive integer or 'len'") from exc
    if parsed < 1:
      raise ValueError("concurrency must be a positive integer or 'len'")
    return cls(value=parsed)

  def resolve(self, item_count: int) -> int:
    if self.value == "len":
      return 1 if item_count <= 0 else min(item_count, MAX_CONCURRENCY)
    return self.value


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
  entity_id: str = Field(
    default="todo.shopping_list",
    pattern=r"^todo\..+$",
  )

  @field_validator("url", "token", mode="after")
  @classmethod
  def _normalize(cls, value: str) -> str:
    trimmed = trim(value)
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
    trimmed = trim(value)
    if trimmed is None:
      raise ValueError("bot_token must be a non-empty string")
    return trimmed

  @field_validator("chat_id", mode="after")
  @classmethod
  def _validate_chat_id(cls, value: int) -> int:
    if value == 0:
      raise ValueError("chat_id cannot be zero")
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
    trimmed = trim(value)
    if trimmed is None:
      raise ValueError("value must be a non-empty string")
    return trimmed

  @field_validator("normalizer_api_key", mode="after")
  @classmethod
  def _normalize_optional_str(cls, value: str | None) -> str | None:
    return trim(value)


class AppConfig(BaseModel):
  model_config = ConfigDict(extra="forbid")

  shopping_list: ShoppingListConfig
  concurrency: ConcurrencyConfig = Field(default_factory=lambda: ConcurrencyConfig(value="len"))
  preferences: PreferencesConfig

  @field_validator("concurrency", mode="before")
  @classmethod
  def _coerce_concurrency(cls, value: object) -> ConcurrencyConfig:
    if value is None:
      return ConcurrencyConfig(value="len")
    if isinstance(value, ConcurrencyConfig):
      return value
    if isinstance(value, str):
      lowered = value.strip().lower()
      if lowered == "len":
        return ConcurrencyConfig(value="len")
      try:
        value = int(lowered)
      except ValueError as exc:
        raise ValueError(
          "concurrency must be an integer greater than or equal to 1 or 'len'"
        ) from exc
    if isinstance(value, int):
      if value < 1:
        raise ValueError("concurrency must be an integer greater than or equal to 1")
      return ConcurrencyConfig(value=value)
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
  except ValidationError as e:
    raise ValueError(f"Invalid configuration in {p}: {e}") from e
