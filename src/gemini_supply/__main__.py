from __future__ import annotations

from gemini_supply.cli import run
from gemini_supply.log import setup_logging


def main() -> int:
  setup_logging()
  return run()


if __name__ == "__main__":
  raise SystemExit(main())
