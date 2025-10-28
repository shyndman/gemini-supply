#!/usr/bin/env python3

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
import tomllib


def main() -> int:
  pyproject_path = Path("pyproject.toml")
  if not pyproject_path.exists():
    print("pyproject.toml not found; skipping path dependency check.", file=sys.stderr)
    return 0

  try:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
  except tomllib.TOMLDecodeError as error:
    print(f"Failed to parse pyproject.toml: {error}", file=sys.stderr)
    return 1

  tool = data.get("tool")
  if not isinstance(tool, dict):
    return 0

  uv_config = tool.get("uv")
  if not isinstance(uv_config, dict):
    return 0

  sources = uv_config.get("sources")
  path_dependencies = _collect_path_dependencies(sources)
  if not path_dependencies:
    return 0

  print("pyproject.toml contains path sourced dependencies:", file=sys.stderr)
  for name, paths in path_dependencies.items():
    for path in paths:
      print(f"  - {name!r} -> {path}", file=sys.stderr)
  print("Remove these path entries before committing.", file=sys.stderr)
  return 1


def _collect_path_dependencies(sources: object) -> dict[str, tuple[str, ...]]:
  if not isinstance(sources, Mapping):
    return {}

  path_dependencies: dict[str, tuple[str, ...]] = {}
  for name, spec in sources.items():
    if not isinstance(name, str):
      continue
    paths = tuple(_extract_paths(spec))
    if paths:
      path_dependencies[name] = paths
  return path_dependencies


def _extract_paths(spec: object) -> tuple[str, ...]:
  if isinstance(spec, Mapping):
    collected: list[str] = []
    for key, value in spec.items():
      if isinstance(key, str) and key == "path" and isinstance(value, str):
        collected.append(value)
      collected.extend(_extract_paths(value))
    return tuple(collected)

  if isinstance(spec, Sequence) and not isinstance(spec, (str, bytes, bytearray)):
    collected: list[str] = []
    for item in spec:
      collected.extend(_extract_paths(item))
    return tuple(collected)

  return ()


if __name__ == "__main__":
  sys.exit(main())
