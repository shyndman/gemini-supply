from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast
from datetime import datetime, timezone
from pathlib import Path

import yaml  # type: ignore[reportMissingImports]
from pydantic import ValidationError

from .types import PreferenceMetadata, PreferenceRecord


class PreferenceStore:
  """YAML-backed store for canonical product preferences."""

  def __init__(self, path: Path) -> None:
    self._path = path.expanduser()
    self._lock = asyncio.Lock()

  async def get(self, canonical_key: str) -> PreferenceRecord | None:
    data = await self._read()
    record = data.get(canonical_key)
    if record is None:
      return None
    return record.model_copy(deep=True)

  async def set(self, canonical_key: str, record: PreferenceRecord) -> None:
    async with self._lock:
      data = await self._read()
      updated_iso = datetime.now(timezone.utc).isoformat()
      metadata = PreferenceMetadata(
        category_label=record.metadata.category_label,
        brand=record.metadata.brand,
        updated_at_iso=updated_iso,
      )
      sanitized = PreferenceRecord(
        product_name=record.product_name,
        metadata=metadata,
      )
      data[canonical_key] = sanitized
      await self._write(data)

  async def _read(self) -> dict[str, PreferenceRecord]:
    if not self._path.exists():
      return {}
    raw_text = self._path.read_text(encoding="utf-8")
    loaded_raw: object = yaml.safe_load(raw_text)
    if loaded_raw is None:
      return {}
    if not isinstance(loaded_raw, Mapping):
      return {}
    loaded_mapping = cast(Mapping[str, Any], loaded_raw)
    result: dict[str, PreferenceRecord] = {}
    for key_obj, value_obj in loaded_mapping.items():
      if not isinstance(key_obj, str):
        continue
      try:
        record = PreferenceRecord.model_validate(value_obj)
      except ValidationError:
        continue
      result[key_obj] = record
    return result

  async def _write(self, data: Mapping[str, PreferenceRecord]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    with self._path.open("w", encoding="utf-8") as handle:
      serialized = {
        key: value.model_dump(mode="python", exclude_none=True) for key, value in data.items()
      }
      yaml.safe_dump(serialized, handle, sort_keys=True, allow_unicode=True)
