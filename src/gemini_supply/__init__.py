from __future__ import annotations

from importlib import import_module
from typing import Callable, cast


def main() -> int:
  module = import_module("gemini_supply.__main__")
  main_callable = getattr(module, "main", None)
  if not callable(main_callable):
    raise RuntimeError("gemini_supply.__main__ missing callable 'main'")
  return cast(Callable[[], int], main_callable)()


__all__ = ["main"]
