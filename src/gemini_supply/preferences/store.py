from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import yaml  # type: ignore[reportMissingImports]
from pydantic import ValidationError

from .types import PreferenceMetadata, PreferenceRecord, PreferenceStoreData


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
    async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
      raw_text = await f.read()
    loaded_raw: object = yaml.safe_load(raw_text)
    if loaded_raw is None:
      return {}
    try:
      store_data = PreferenceStoreData.model_validate(loaded_raw)
      return store_data.to_dict()
    except ValidationError as e:
      raise ValueError(f"Failed to parse preferences file at {self._path}: {e}") from e

  async def _write(self, data: dict[str, PreferenceRecord]) -> None:
    self._path.parent.mkdir(parents=True, exist_ok=True)
    store_data = PreferenceStoreData(root=data)
    serialized = store_data.model_dump(mode="python", exclude_none=True)
    yaml_text = yaml.safe_dump(serialized, sort_keys=True, allow_unicode=True)
    async with aiofiles.open(self._path, "w", encoding="utf-8") as handle:
      await handle.write(yaml_text)
