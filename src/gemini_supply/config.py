from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


DEFAULT_CONFIG_PATH = Path("~/.config/gemini-supply/config.yaml").expanduser()


def _trim(value: str | None) -> str | None:
  if value is None:
    return None
  trimmed = value.strip()
  if not trimmed:
    return None
  return trimmed


class ShoppingListConfig(BaseModel):
  model_config = ConfigDict(extra="ignore")

  provider: str | None = None

  @field_validator("provider", mode="after")
  @classmethod
  def _normalize_provider(cls, value: str | None) -> str | None:
    return _trim(value)


class HomeAssistantConfig(BaseModel):
  model_config = ConfigDict(extra="ignore")

  url: str | None = None
  token: str | None = None

  @field_validator("url", "token", mode="after")
  @classmethod
  def _normalize(cls, value: str | None) -> str | None:
    return _trim(value)


class PreferencesTelegramConfig(BaseModel):
  model_config = ConfigDict(extra="ignore")

  bot_token: str | None = None
  chat_id: int | None = None
  nag_minutes: int | None = None

  @field_validator("bot_token", mode="after")
  @classmethod
  def _normalize_bot_token(cls, value: str | None) -> str | None:
    return _trim(value)

  @field_validator("chat_id", mode="after")
  @classmethod
  def _validate_chat_id(cls, value: int | None) -> int | None:
    if value is None:
      return None
    if value <= 0:
      return None
    return value

  @field_validator("nag_minutes", mode="after")
  @classmethod
  def _validate_nag_minutes(cls, value: int | None) -> int | None:
    if value is None:
      return None
    if value <= 0:
      return None
    return value


class PreferencesConfig(BaseModel):
  model_config = ConfigDict(extra="ignore")

  file: str | None = None
  telegram: PreferencesTelegramConfig | None = None
  normalizer_model: str | None = None
  normalizer_api_base_url: str | None = None
  normalizer_api_key: str | None = None

  @field_validator(
    "file",
    "normalizer_model",
    "normalizer_api_base_url",
    "normalizer_api_key",
    mode="after",
  )
  @classmethod
  def _normalize_optional_str(cls, value: str | None) -> str | None:
    return _trim(value)


class AppConfig(BaseModel):
  model_config = ConfigDict(extra="ignore")

  shopping_list: ShoppingListConfig | None = None
  home_assistant: HomeAssistantConfig | None = None
  postal_code: str | None = None
  concurrency: int | None = None
  preferences: PreferencesConfig | None = None

  @field_validator("postal_code", mode="after")
  @classmethod
  def _normalize_postal_code(cls, value: str | None) -> str | None:
    trimmed = _trim(value)
    if trimmed is None:
      return None
    return trimmed.replace(" ", "").upper()

  @field_validator("concurrency", mode="before")
  @classmethod
  def _coerce_concurrency(cls, value: object) -> int | None:
    if value is None:
      return None
    try:
      conc = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
      raise ValueError("concurrency must be an integer greater than or equal to 1") from exc
    if conc < 1:
      raise ValueError("concurrency must be an integer greater than or equal to 1")
    return conc


def load_config(path: Path | None) -> AppConfig | None:
  """Load config YAML if present.

  Returns None if file missing or YAML cannot be parsed.
  """
  p = (path or DEFAULT_CONFIG_PATH).expanduser()
  if not p.exists():
    return None
  try:
    import yaml  # type: ignore[reportMissingImports]
  except Exception:
    return None
  try:
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
  except Exception:
    return None
  if data is None:
    return AppConfig()
  if not isinstance(data, dict):
    return None
  try:
    return AppConfig.model_validate(data)
  except ValidationError as exc:
    raise ValueError(f"Invalid configuration in {p}: {exc}") from exc
