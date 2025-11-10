from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from genai_prices import calc_price
from genai_prices import types as price_types
from google.genai.types import GenerateContentResponseUsageMetadata
from pydantic_ai.usage import RunUsage

from generative_supply.usage import (
  CostBreakdown,
  PricingQuote,
  TokenUsage,
  UsageCategory,
  decimal_to_cents,
)

_GOOGLE_PROVIDER_ID = "google"


def _cost_from_decimals(input_price: Decimal, output_price: Decimal) -> CostBreakdown:
  input_cents = decimal_to_cents(input_price)
  output_cents = decimal_to_cents(output_price)
  return CostBreakdown(
    input_cents=input_cents,
    output_cents=output_cents,
    total_cents=input_cents + output_cents,
  )


def _tiered_price(base: str, tier_start: int, tier_price: str) -> price_types.TieredPrices:
  return price_types.TieredPrices(
    base=Decimal(base),
    tiers=[price_types.Tier(start=tier_start, price=Decimal(tier_price))],
  )


@dataclass(slots=True)
class PricingEngine:
  """Calculate Gemini pricing via genai-prices with repo-specific overrides."""

  _overrides: dict[str, price_types.ModelPrice] = field(init=False, repr=False)

  def __post_init__(self) -> None:
    self._overrides = {
      "gemini-2.5-computer-use-preview-10-2025": price_types.ModelPrice(
        input_mtok=_tiered_price("1.25", 200_000, "2.50"),
        output_mtok=_tiered_price("10.00", 200_000, "15.00"),
      )
    }

  def quote_from_google_metadata(
    self,
    *,
    model_name: str,
    category: UsageCategory,
    metadata: GenerateContentResponseUsageMetadata | None,
  ) -> PricingQuote | None:
    tokens = TokenUsage.from_google_metadata(metadata)
    if not tokens.has_usage():
      return None
    return self._quote(model_name=model_name, category=category, tokens=tokens)

  def quote_from_run_usage(
    self,
    *,
    model_name: str,
    category: UsageCategory,
    usage: RunUsage,
  ) -> PricingQuote | None:
    tokens = TokenUsage.from_run_usage(usage)
    if not tokens.has_usage():
      return None
    return self._quote(model_name=model_name, category=category, tokens=tokens)

  def _quote(self, *, model_name: str, category: UsageCategory, tokens: TokenUsage) -> PricingQuote:
    override = self._overrides.get(model_name)
    price_usage = tokens.to_price_usage()
    if override is not None:
      cost_map = override.calc_price(price_usage)
      cost = _cost_from_decimals(cost_map["input_price"], cost_map["output_price"])
      provider_id = _GOOGLE_PROVIDER_ID
      model_price = override
    else:
      calculation = calc_price(
        usage=price_usage,
        model_ref=model_name,
        provider_id=_GOOGLE_PROVIDER_ID,
      )
      cost = _cost_from_decimals(calculation.input_price, calculation.output_price)
      provider_id = calculation.provider.id
      model_price = calculation.model_price

    return PricingQuote(
      model_name=model_name,
      provider_id=provider_id,
      category=category,
      token_usage=tokens,
      model_price=model_price,
      cost=cost,
    )


__all__ = ["PricingEngine"]
