"""Utilities for parsing and manipulating price values."""

from decimal import Decimal, InvalidOperation


def _normalize_price_text(price_text: str) -> str:
  """Strip currency fluff while preserving the decimal separator."""

  allowed = {".", ","}
  chars: list[str] = []
  for ch in price_text.strip():
    if ch.isdigit() or ch in allowed:
      chars.append(ch)
  normalized = "".join(chars)
  if normalized.count(",") == 1 and normalized.count(".") == 0:
    # Single comma typically signals decimal in EU/CA locales.
    normalized = normalized.replace(",", ".")
  else:
    # Otherwise assume commas group thousands.
    normalized = normalized.replace(",", "")
  if not normalized:
    raise ValueError(f"price_text '{price_text}' lacks digits")
  return normalized


def parse_price_cents(price_text: str) -> int:
  """Parse price in cents from formatted price text like '$12.34'."""

  normalized = _normalize_price_text(price_text)
  try:
    quantized = (Decimal(normalized) * 100).quantize(Decimal("1"))
  except InvalidOperation as exc:
    # Short rationale: we want bad input to surface early.
    raise ValueError(f"price_text '{price_text}' is not numeric") from exc
  cents = int(quantized)
  if cents < 0:
    raise ValueError("price_text must not be negative")
  return cents
