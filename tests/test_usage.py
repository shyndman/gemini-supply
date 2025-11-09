from google.genai.types import UsageMetadata

from generative_supply.usage import TokenUsage, UsageCategory, UsageLedger
from generative_supply.usage_pricing import PricingEngine


def test_token_usage_from_google_metadata() -> None:
  metadata = UsageMetadata(
    prompt_token_count=100,
    tool_use_prompt_token_count=20,
    cached_content_token_count=40,
    response_token_count=60,
  )
  usage = TokenUsage.from_google_metadata(metadata)
  assert usage.input_tokens == 120
  assert usage.cache_read_tokens == 40
  assert usage.output_tokens == 60


def test_pricing_engine_custom_model_quote() -> None:
  engine = PricingEngine()
  metadata = UsageMetadata(prompt_token_count=150_000, response_token_count=100_000)
  quote = engine.quote_from_google_metadata(
    model_name="gemini-2.5-computer-use-preview-10-2025",
    category=UsageCategory.SHOPPER,
    metadata=metadata,
  )
  assert quote is not None
  assert quote.cost.total_cents == 119  # $1.19 total


def test_usage_ledger_snapshot_accumulates() -> None:
  engine = PricingEngine()
  ledger = UsageLedger()
  metadata = UsageMetadata(prompt_token_count=50_000, response_token_count=50_000)
  quote = engine.quote_from_google_metadata(
    model_name="gemini-2.5-computer-use-preview-10-2025",
    category=UsageCategory.SHOPPER,
    metadata=metadata,
  )
  assert quote is not None
  ledger.record(quote)
  entries = ledger.snapshot()
  assert len(entries) == 1
  assert entries[0].cost.total_cents == quote.cost.total_cents
