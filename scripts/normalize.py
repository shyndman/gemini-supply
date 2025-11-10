#!/usr/bin/env -S uv run
"""Test the normalizer with command-line arguments.

Usage:
  ./normalize.py "2x Lactantia 1% Milk" "Bread" "3 PC Chicken Breasts"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from rich import print

# Add src to path so we can import generative_supply
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from generative_supply.preferences.normalizer import NormalizationAgent
from generative_supply.usage import UsageLedger
from generative_supply.usage_pricing import PricingEngine


async def main() -> None:
  if len(sys.argv) < 2:
    print("Usage: ./normalize.py ITEM1 [ITEM2 ...]", file=sys.stderr)
    print("\nExample:", file=sys.stderr)
    print('  ./normalize.py "2x Lactantia 1% Milk" "Bread"', file=sys.stderr)
    sys.exit(1)

  # Built-in config keeps expectations simple; no external settings required here.
  agent = NormalizationAgent(
    usage_ledger=UsageLedger(),
    pricing_engine=PricingEngine(),
  )

  # Process each item
  items = sys.argv[1:]
  print(f"Normalizing {len(items)} item(s)...\n")

  for idx, item_text in enumerate(items, start=1):
    print(f"[{idx}/{len(items)}] Input: {item_text!r}")
    try:
      print(await agent.normalize(item_text))
    except Exception as exc:
      print(f"  ERROR: {exc}", file=sys.stderr)
      print()


if __name__ == "__main__":
  asyncio.run(main())
