from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Iterable

from genai_prices import types as price_types
from google.genai.types import UsageMetadata
from pydantic_ai.usage import RunUsage


class UsageCategory(StrEnum):
  SHOPPER = "shopper"
  NORMALIZER = "normalizer"


def decimal_to_cents(value: Decimal) -> int:
  return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_usd_cents(cents: int) -> str:
  dollars = Decimal(cents) / Decimal(100)
  return f"${dollars:.2f}"


@dataclass(slots=True)
class TokenUsage:
  input_tokens: int = 0
  cache_write_tokens: int = 0
  cache_read_tokens: int = 0
  output_tokens: int = 0
  input_audio_tokens: int = 0
  cache_audio_read_tokens: int = 0
  output_audio_tokens: int = 0

  def add(self, other: TokenUsage) -> None:
    self.input_tokens += other.input_tokens
    self.cache_write_tokens += other.cache_write_tokens
    self.cache_read_tokens += other.cache_read_tokens
    self.output_tokens += other.output_tokens
    self.input_audio_tokens += other.input_audio_tokens
    self.cache_audio_read_tokens += other.cache_audio_read_tokens
    self.output_audio_tokens += other.output_audio_tokens

  def copy(self) -> TokenUsage:
    return TokenUsage(
      input_tokens=self.input_tokens,
      cache_write_tokens=self.cache_write_tokens,
      cache_read_tokens=self.cache_read_tokens,
      output_tokens=self.output_tokens,
      input_audio_tokens=self.input_audio_tokens,
      cache_audio_read_tokens=self.cache_audio_read_tokens,
      output_audio_tokens=self.output_audio_tokens,
    )

  def has_usage(self) -> bool:
    return any(
      (
        self.input_tokens,
        self.cache_write_tokens,
        self.cache_read_tokens,
        self.output_tokens,
        self.input_audio_tokens,
        self.cache_audio_read_tokens,
        self.output_audio_tokens,
      )
    )

  def to_price_usage(self) -> price_types.Usage:
    return price_types.Usage(
      input_tokens=self.input_tokens or None,
      cache_write_tokens=self.cache_write_tokens or None,
      cache_read_tokens=self.cache_read_tokens or None,
      output_tokens=self.output_tokens or None,
      input_audio_tokens=self.input_audio_tokens or None,
      cache_audio_read_tokens=self.cache_audio_read_tokens or None,
      output_audio_tokens=self.output_audio_tokens or None,
    )

  @classmethod
  def from_google_metadata(cls, metadata: UsageMetadata | None) -> TokenUsage:
    if metadata is None:
      return cls()
    prompt_tokens = (metadata.prompt_token_count or 0) + (metadata.tool_use_prompt_token_count or 0)
    return cls(
      input_tokens=prompt_tokens,
      cache_read_tokens=metadata.cached_content_token_count or 0,
      output_tokens=metadata.response_token_count or 0,
    )

  @classmethod
  def from_run_usage(cls, usage: RunUsage) -> TokenUsage:
    return cls(
      input_tokens=usage.input_tokens,
      cache_write_tokens=usage.cache_write_tokens,
      cache_read_tokens=usage.cache_read_tokens,
      output_tokens=usage.output_tokens,
      input_audio_tokens=usage.input_audio_tokens,
      cache_audio_read_tokens=usage.cache_audio_read_tokens,
      output_audio_tokens=usage.output_audio_tokens,
    )


@dataclass(slots=True)
class CostBreakdown:
  input_cents: int
  output_cents: int
  total_cents: int

  @property
  def total_text(self) -> str:
    return format_usd_cents(self.total_cents)


@dataclass(slots=True)
class PricingQuote:
  model_name: str
  provider_id: str
  category: UsageCategory
  token_usage: TokenUsage
  model_price: price_types.ModelPrice
  cost: CostBreakdown


@dataclass(slots=True)
class UsageSummaryEntry:
  category: UsageCategory
  model_name: str
  provider_id: str
  token_usage: TokenUsage
  cost: CostBreakdown


@dataclass(slots=True)
class _UsageAccumulator:
  model_name: str
  provider_id: str
  model_price: price_types.ModelPrice
  tokens: TokenUsage = field(default_factory=TokenUsage)

  def add_usage(self, usage: TokenUsage) -> None:
    self.tokens.add(usage)

  def cost(self) -> CostBreakdown:
    prices = self.model_price.calc_price(self.tokens.to_price_usage())
    input_cents = decimal_to_cents(prices["input_price"])
    output_cents = decimal_to_cents(prices["output_price"])
    total_cents = input_cents + output_cents
    return CostBreakdown(
      input_cents=input_cents,
      output_cents=output_cents,
      total_cents=total_cents,
    )


class UsageLedger:
  def __init__(self) -> None:
    self._entries: dict[UsageCategory, _UsageAccumulator] = {}

  def record(self, quote: PricingQuote) -> None:
    entry = self._entries.get(quote.category)
    if entry is None:
      self._entries[quote.category] = _UsageAccumulator(
        model_name=quote.model_name,
        provider_id=quote.provider_id,
        model_price=quote.model_price,
      )
      entry = self._entries[quote.category]
    else:
      if entry.model_name != quote.model_name:
        raise ValueError(
          f"Usage category {quote.category} already bound to {entry.model_name}; "
          f"cannot record {quote.model_name}."
        )
    entry.add_usage(quote.token_usage)

  def snapshot(self) -> list[UsageSummaryEntry]:
    rows: list[UsageSummaryEntry] = []
    for category in UsageCategory:
      if category not in self._entries:
        continue
      accumulator = self._entries[category]
      rows.append(
        UsageSummaryEntry(
          category=category,
          model_name=accumulator.model_name,
          provider_id=accumulator.provider_id,
          token_usage=accumulator.tokens.copy(),
          cost=accumulator.cost(),
        )
      )
    return rows

  def total_cost_cents(self) -> int:
    return sum(entry.cost.total_cents for entry in self.snapshot())

  def __bool__(self) -> bool:
    return bool(self._entries)


def summarize_usage_rows(entries: Iterable[UsageSummaryEntry]) -> list[tuple[str, str]]:
  rows: list[tuple[str, str]] = []
  for entry in entries:
    tokens = entry.token_usage
    left = f"{entry.category.value}:{entry.model_name}"
    right_parts = [
      f"in={tokens.input_tokens:,}",
      f"out={tokens.output_tokens:,}",
      f"cost={entry.cost.total_text}",
    ]
    rows.append((left, " | ".join(right_parts)))
  return rows


__all__ = [
  "CostBreakdown",
  "PricingQuote",
  "TokenUsage",
  "UsageCategory",
  "UsageLedger",
  "UsageSummaryEntry",
  "decimal_to_cents",
  "format_usd_cents",
  "summarize_usage_rows",
]
