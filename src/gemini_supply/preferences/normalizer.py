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

SYSTEM_PROMPT = """You are a shopping list item parser. Analyze a shopping list entry and extract structured fields.

Return a JSON object with:
1. quantity: integer (default 1) representing how many product units are requested.
2. brand: string or null when no brand is supplied.
3. category: string describing the general product type. REMOVE strength or quality qualifiers (e.g., "1%", "organic", "unsalted") and size descriptors ("1L", "dozen", "500 g"). Keep the category stable and minimal (e.g., "Milk", "Butter", "Eggs").
4. qualifiers: array of short strings capturing important adjectives or phrases that were removed from category but matter for shopping (e.g., "1%", "organic", "for baking"). Preserve order of appearance, omit duplicates, and never include size descriptors.

Guidance:
- Quantity indicators include numeric prefixes ("2x", "3") or words ("two", "dozen"). Normalize "dozen" to quantity 12 only when explicitly stated like "two dozen"; otherwise default quantity to 1.
- Treat brand names as proper nouns ("Lactantia", "PC", "No Name", "Compliments").
- Exclude size or packaging text from both category and qualifiers (e.g., "1L", "6-pack", "500 g").
- Preserve helpful usage hints in qualifiers, such as "for baking", "gluten free", "unsalted".
- Be case insensitive, but output brand and qualifiers in the capitalization provided by the user when possible.
- Handle common abbreviations ("oz", "lb", "kg") when determining quantity or size; sizes should be discarded.

Examples:
- "2x Lactantia 1% Milk" → {"quantity": 2, "brand": "Lactantia", "category": "Milk", "qualifiers": ["1%"]}
- "Bread" → {"quantity": 1, "brand": null, "category": "Bread", "qualifiers": []}
- "3 PC Chicken Breasts" → {"quantity": 3, "brand": "PC", "category": "Chicken Breasts", "qualifiers": []}
- "Dozen eggs" → {"quantity": 12, "brand": null, "category": "Eggs", "qualifiers": []}
- "Milk for baking" → {"quantity": 1, "brand": null, "category": "Milk", "qualifiers": ["for baking"]}
- "Unsalted Butter 454g" → {"quantity": 1, "brand": null, "category": "Butter", "qualifiers": ["unsalted"]}

Respond with ONLY valid JSON matching the schema. No explanations, markdown, or extra text."""


class _NormalizationModel(BaseModel):
  quantity: int = Field(ge=1, description="The number of items requested.")
  brand: str | None = Field(default=None, description="The brand name if specified.")
  category: str = Field(min_length=1, description="The general product category or type.")
  qualifiers: list[str] = Field(
    default_factory=list, description="Qualifiers removed from category."
  )


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
    qualifiers: list[str] = []
    for value in data.qualifiers:
      if not isinstance(value, str):
        continue
      trimmed = value.strip()
      if not trimmed:
        continue
      qualifiers.append(trimmed)
    return NormalizedItem(
      canonical_key=_slugify(category),
      category_label=category,
      original_text=item_text.strip(),
      quantity=int(data.quantity),
      brand=data.brand.strip() if isinstance(data.brand, str) and data.brand.strip() else None,
      qualifiers=qualifiers,
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
