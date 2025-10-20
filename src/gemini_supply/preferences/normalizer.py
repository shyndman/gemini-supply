from __future__ import annotations

import os
from functools import cached_property

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from .constants import DEFAULT_NORMALIZER_MODEL
from .types import NormalizedItem

SYSTEM_PROMPT = """You are a shopping list item parser. Your task is to analyze a shopping list item and extract structured information from it.

For each item, extract:
1. quantity: The number of items requested (default to 1 if not specified)
2. brand: The specific brand name, if mentioned (null if no brand specified)
3. category: The general product category or type of item

Guidelines:
- Quantity indicators include: numbers like "2x", "3", "two", etc.
- Quantity refers to the number of product units (packages/containers), not individual pieces
- Brand names are proper nouns like "Lactantia", "PC", "No Name", "Compliments", etc.
- Category should be the general product type (e.g., "Milk", "Bread", "Eggs", "Chicken Breast")
- Include product qualifiers in the category (e.g., "1%", "whole wheat", "organic") but NOT size descriptors
- Size descriptors like "dozen", "1L", "500g", "large", "small" should be omitted from the category
- Be case-insensitive when parsing
- Handle common abbreviations (e.g., "oz", "lb", "kg")

Examples:
- "2x Lactantia 1% Milk" → quantity: 2, brand: "Lactantia", category: "1% Milk"
- "Bread" → quantity: 1, brand: null, category: "Bread"
- "3 PC Chicken Breasts" → quantity: 3, brand: "PC", category: "Chicken Breasts"
- "Dozen eggs" → quantity: 1, brand: null, category: "Eggs"
- "2 dozen eggs" → quantity: 2, brand: null, category: "Eggs"
- "Large whole wheat bread" → quantity: 1, brand: null, category: "Whole Wheat Bread"

You must respond with ONLY valid JSON matching the specified schema. Do not include any explanatory text, markdown formatting, or code blocks - only the raw JSON object."""


class _NormalizationModel(BaseModel):
  quantity: int = Field(ge=1, description="The number of items requested.")
  brand: str | None = Field(default=None, description="The brand name if specified.")
  category: str = Field(min_length=1, description="The general product category or type.")


class NormalizationAgent:
  def __init__(
    self,
    model_name: str = DEFAULT_NORMALIZER_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
  ) -> None:
    self._model_name = model_name
    self._base_url = base_url.strip() if isinstance(base_url, str) and base_url.strip() else None
    self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None

  async def normalize(self, item_text: str) -> NormalizedItem:
    run_result = await self._agent.run(user_prompt=item_text)
    data = run_result.output
    category = data.category.strip()
    return NormalizedItem(
      canonical_key=_slugify(category),
      category_label=category,
      original_text=item_text.strip(),
      quantity=int(data.quantity),
      brand=data.brand.strip() if isinstance(data.brand, str) and data.brand.strip() else None,
    )

  @cached_property
  def _agent(self) -> Agent[None, _NormalizationModel]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
      raise RuntimeError("GEMINI_API_KEY is required for normalization.")
    base_url = self._base_url or os.environ.get("OLLAMA_BASE_URL")
    provider_api_key = self._api_key or os.environ.get("OLLAMA_API_KEY")
    if base_url:
      provider = OllamaProvider(base_url=base_url, api_key=provider_api_key)
      model = OpenAIChatModel(model_name=self._model_name, provider=provider)
    else:
      api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
      if not api_key:
        raise RuntimeError(
          "Set OPENAI_API_KEY for normalization, or configure preferences.normalizer_api_key / OLLAMA_BASE_URL."
        )
      provider = OpenAIProvider(api_key=api_key)
      model = OpenAIChatModel(model_name=self._model_name, provider=provider)
    return Agent(
      model=model,
      output_type=_NormalizationModel,
      system_prompt=SYSTEM_PROMPT,
    )


def _slugify(value: str) -> str:
  lowered = value.lower()
  chars: list[str] = []
  prev_hyphen = False
  for ch in lowered:
    if ch.isalnum():
      chars.append(ch)
      prev_hyphen = False
    else:
      if not prev_hyphen:
        chars.append("-")
        prev_hyphen = True
  slug = "".join(chars).strip("-")
  return slug or "item"
