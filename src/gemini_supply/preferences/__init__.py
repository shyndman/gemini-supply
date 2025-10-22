from __future__ import annotations

from .constants import DEFAULT_NAG_STRINGS, DEFAULT_NORMALIZER_MODEL
from .messenger import TelegramPreferenceMessenger, TelegramSettings
from .normalizer import NormalizationAgent
from .service import PreferenceCoordinator, PreferenceItemSession, _coerce_options
from .store import PreferenceStore
from .types import (
  NormalizedItem,
  PreferenceMetadata,
  PreferenceRecord,
  ProductChoiceRequest,
  ProductChoiceResult,
  ProductOption,
)

__all__ = [
  # constants
  "DEFAULT_NAG_STRINGS",
  "DEFAULT_NORMALIZER_MODEL",
  # messenger
  "TelegramPreferenceMessenger",
  "TelegramSettings",
  # normalizer
  "NormalizationAgent",
  # service
  "PreferenceCoordinator",
  "PreferenceItemSession",
  "_coerce_options",
  # store
  "PreferenceStore",
  # types
  "NormalizedItem",
  "PreferenceMetadata",
  "PreferenceRecord",
  "ProductChoiceRequest",
  "ProductChoiceResult",
  "ProductOption",
]
