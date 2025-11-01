from __future__ import annotations

from generative_supply.cli import run
from generative_supply.log import setup_logging


def main() -> int:
  setup_logging()
  return run()


if __name__ == "__main__":
  raise SystemExit(main())
