#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "pydantic>=2.0",
# ]
# ///

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from pydantic import BaseModel, RootModel


class PathSource(BaseModel):
  """A dependency source specified by filesystem path."""

  path: str


class GitSource(BaseModel):
  """A dependency source specified by git repository."""

  git: str
  rev: str | None = None
  branch: str | None = None
  tag: str | None = None


class UrlSource(BaseModel):
  """A dependency source specified by URL."""

  url: str


DependencySource = PathSource | GitSource | UrlSource | dict[str, object]


class UVSources(RootModel[dict[str, DependencySource | list[DependencySource]]]):
  """UV sources configuration mapping package names to source specifications."""

  pass


class UVConfig(BaseModel):
  """UV tool configuration."""

  sources: UVSources | None = None


class ToolConfig(BaseModel):
  """Tool-specific configuration section."""

  uv: UVConfig | None = None


class PyProject(BaseModel):
  """Minimal pyproject.toml structure for path dependency validation."""

  tool: ToolConfig | None = None


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

  try:
    pyproject = PyProject.model_validate(data)
  except Exception as error:
    print(f"Failed to validate pyproject.toml structure: {error}", file=sys.stderr)
    return 1

  if not pyproject.tool or not pyproject.tool.uv or not pyproject.tool.uv.sources:
    return 0

  path_dependencies = _collect_path_dependencies(pyproject.tool.uv.sources.root)
  if not path_dependencies:
    return 0

  print("pyproject.toml contains path sourced dependencies:", file=sys.stderr)
  for name, paths in path_dependencies.items():
    for path in paths:
      print(f"  - {name!r} -> {path}", file=sys.stderr)
  print("Remove these path entries before committing.", file=sys.stderr)
  return 1


def _collect_path_dependencies(
  sources: dict[str, DependencySource | list[DependencySource]],
) -> dict[str, list[str]]:
  path_dependencies: dict[str, list[str]] = {}
  for name, spec in sources.items():
    paths = _extract_paths(spec)
    if paths:
      path_dependencies[name] = paths
  return path_dependencies


def _extract_paths(spec: DependencySource | list[DependencySource]) -> list[str]:
  if isinstance(spec, list):
    collected: list[str] = []
    for item in spec:
      collected.extend(_extract_paths(item))
    return collected

  if isinstance(spec, PathSource):
    return [spec.path]

  return []


if __name__ == "__main__":
  sys.exit(main())
