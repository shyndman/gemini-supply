#!/usr/bin/env -S uv run
"""Test the normalizer with command-line arguments.

Usage:
  ./normalize.py "2x Lactantia 1% Milk" "Bread" "3 PC Chicken Breasts"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import gemini_supply
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gemini_supply.config import load_config
from gemini_supply.preferences.normalizer import NormalizationAgent
from gemini_supply.term import ActivityLog


async def main() -> None:
  if len(sys.argv) < 2:
    print("Usage: ./normalize.py ITEM1 [ITEM2 ...]", file=sys.stderr)
    print("\nExample:", file=sys.stderr)
    print('  ./normalize.py "2x Lactantia 1% Milk" "Bread"', file=sys.stderr)
    sys.exit(1)

  # Load config
  try:
    config = load_config(None)
  except Exception as exc:
    print(f"Error loading config: {exc}", file=sys.stderr)
    sys.exit(1)

  # Create normalizer from config
  prefs = config.preferences
  log = ActivityLog()
  agent = NormalizationAgent(
    model_name=prefs.normalizer_model,
    base_url=prefs.normalizer_api_base_url,
    api_key=prefs.normalizer_api_key,
    log=log,
  )

  # Process each item
  items = sys.argv[1:]
  print(f"Normalizing {len(items)} item(s)...\n")

  for idx, item_text in enumerate(items, start=1):
    print(f"[{idx}/{len(items)}] Input: {item_text!r}")
    try:
      result = await agent.normalize(item_text)
      # Print all fields from the model
      for field_name in result.__class__.model_fields:
        value = getattr(result, field_name)
        print(f"  {field_name}: {value!r}")
      print()
    except Exception as exc:
      print(f"  ERROR: {exc}", file=sys.stderr)
      print()


if __name__ == "__main__":
  asyncio.run(main())
