from google.genai.types import GenerateContentResponseUsageMetadata

from generative_supply.usage import (
  CostBreakdown,
  TokenUsage,
  UsageCategory,
  UsageLedger,
  UsageSummaryEntry,
  summarize_usage_rows,
)
from generative_supply.usage_pricing import PricingEngine


def test_token_usage_from_metadata() -> None:
  metadata = GenerateContentResponseUsageMetadata(
    prompt_token_count=100,
    tool_use_prompt_token_count=20,
    cached_content_token_count=40,
    candidates_token_count=60,
  )
  usage = TokenUsage.from_google_metadata(metadata)
  assert usage.input_tokens == 120
  assert usage.cache_read_tokens == 40
  assert usage.output_tokens == 60


def test_pricing_engine_computer_use_override() -> None:
  engine = PricingEngine()
  metadata = GenerateContentResponseUsageMetadata(
    prompt_token_count=150_000,
    candidates_token_count=100_000,
  )
  quote = engine.quote_from_google_metadata(
    model_name="gemini-2.5-computer-use-preview-10-2025",
    category=UsageCategory.SHOPPER,
    metadata=metadata,
  )
  assert quote is not None
  assert quote.cost.total_cents == 119


def test_usage_ledger_snapshot_and_total() -> None:
  ledger = UsageLedger()
  engine = PricingEngine()
  metadata = GenerateContentResponseUsageMetadata(
    prompt_token_count=50_000,
    candidates_token_count=50_000,
  )
  quote = engine.quote_from_google_metadata(
    model_name="gemini-2.5-computer-use-preview-10-2025",
    category=UsageCategory.SHOPPER,
    metadata=metadata,
  )
  assert quote is not None
  ledger.record(quote)
  entries = ledger.snapshot()
  assert len(entries) == 1
  entry = entries[0]
  assert entry.cost.total_cents == quote.cost.total_cents
  assert ledger.total_cost_cents() == quote.cost.total_cents


def test_summarize_usage_rows() -> None:
  entry = UsageSummaryEntry(
    category=UsageCategory.SHOPPER,
    model_name="gemini",
    provider_id="google",
    token_usage=TokenUsage(input_tokens=10, output_tokens=5),
    cost=CostBreakdown(input_cents=1, output_cents=2, total_cents=3),
  )
  rows = summarize_usage_rows([entry])
  assert rows == [("shopper:gemini", "in=10 | out=5 | cost=$0.03")]
