"""Utilities for parsing and manipulating price values."""

import re


def parse_price_cents(price_text: str) -> int:
  """Parse price in cents from formatted price text like '$12.34'.

  Removes non numeric characters, then parses as integer cents.

  Args:
    price_text: Price string (e.g., "$12.34" or "12.34")

  Returns:
    Price in cents as an integer (e.g., 1234)
  """
  cleaned = re.sub(r"\D", "", price_text)
  return int(cleaned)
