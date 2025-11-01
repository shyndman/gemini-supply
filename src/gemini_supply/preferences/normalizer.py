from __future__ import annotations

from functools import cached_property
from typing import cast

from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.providers.google import GoogleProvider
from gemini_supply.term import ActivityLog
from .constants import DEFAULT_NORMALIZER_MODEL
from .types import _PartialNormalizedItem, NormalizedItem

SYSTEM_PROMPT = """You are a shopping list item parser. Analyze a shopping list entry and extract structured fields.

Return a JSON object with:
1. quantity: integer (default 1) representing how many product units are requested.
2. quantity_string: string or null. The exact quantity expression as written (e.g., "1x", "10 X", "x6", "4", "two dozen"). If no quantity expression is present, set to null.
3. unit_descriptor: string or null. The unit or container descriptor if present (e.g., "box of", "box", "loaf of", "can of", "can", "bunch of", "wedge", "small container"). May or may not include the word "of". May include adjectives modifying the unit ("small jar", "large bag"). Preserve capitalization as written. If not specified, set to null. **CRITICAL: If extracted to unit_descriptor, DO NOT include in qualifiers.**
4. brand: string or null. ONLY extract actual brand names (manufacturer or store brands like "Lactantia", "PC", "No Name", "Compliments", "Aunt Jemima's", "Dad's"). Descriptive words like "1%", "organic", "unsalted" are NOT brands - leave brand as null if no explicit brand name exists. **Possessive forms (words ending in 's or s') always indicate a brand name. CRITICAL: If extracted as brand, DO NOT include in qualifiers.**
5. category: string describing the general product type. You may infer broader categories when appropriate (e.g., "Feta" → "Cheese", "Cheddar" → "Cheese", "Sourdough" → "Bread"). REMOVE strength or quality qualifiers (e.g., "1%", "organic", "unsalted"), size descriptors ("1L", "dozen", "500 g"), and unit descriptors ("box of", "loaf of", "can of"). Keep the category stable and minimal (e.g., "Milk", "Butter", "Eggs", "Cheese").
6. qualifiers: array of short strings capturing important adjectives or phrases that were removed from category but matter for shopping (e.g., "1%", "organic", "for baking"). **Parenthetical content should be preserved as complete phrases, not broken into separate tokens** (e.g., "(or 5 individual)" → ["or 5 individual"]). Preserve order of appearance, omit duplicates. **CRITICAL: NEVER include unit descriptors, size descriptors, or brand names in qualifiers. These belong in their own dedicated fields.**

**CRITICAL RULE - NO DUPLICATION:**
Each word or phrase must appear in EXACTLY ONE field. A word cannot appear in multiple fields:
- If it's a unit_descriptor → do NOT put it in qualifiers
- If it's a brand → do NOT put it in qualifiers
- If it's a size descriptor → do NOT put it anywhere (exclude entirely)
- If it's part of the base category → do NOT put it in qualifiers
- When inferring broader categories, the specific variety MUST go in qualifiers

Guidance:
- Quantity indicators include numeric prefixes ("2x", "3"), numeric suffixes ("x2", "x3"), or words ("two", "dozen"). Normalize "dozen" to quantity 12 only when explicitly stated like "two dozen"; otherwise default quantity to 1.
- **quantity_string captures the exact text:** Preserve the original quantity expression exactly as written, including spacing, capitalization, and format (e.g., "1x", "10 X", "x6", "4", "five", "one"). If no quantity is expressed, set to null.
- **Unit descriptors:** Words or phrases that specify a unit, container, or form factor of the product:
  - Containers (may have adjectives): "box of", "box", "bag of", "small bag", "can of", "can", "bottle of", "jar of", "small container", "large jar"
  - Form factors: "loaf of", "loaf", "bunch of", "bunch", "head of", "stick of", "wedge", "wedge of", "slice", "piece", "chunk", "block"
  - May or may not include "of"
  - Preserve capitalization as written
  - Extract to unit_descriptor field; strip from category; **NEVER include in qualifiers**
- **Size descriptors to EXCLUDE entirely:** Volume/weight measurements like "1L", "pints", "gallons", "oz", "lb", "kg", "500g", "ml". These should not appear in unit_descriptor, qualifiers, or category.
- **Parenthetical content:** Content in parentheses should be treated as complete phrases and added to qualifiers as single strings, not tokenized into separate words. Remove the parentheses but keep the content intact (e.g., "(or 5 individual)" becomes the qualifier "or 5 individual").
- **Category inference:** You may infer broader, more general categories when the item name is a specific variety or type. For example, "Feta" can be inferred as "Cheese", "Sourdough" as "Bread", "Granny Smith" as "Apples". **When you infer a broader category, always preserve the specific variety as a qualifier** (e.g., "cheddar" when category is "Cheese", "feta" when category is "Cheese", "sourdough" when category is "Bread", "parmesan" when category is "Cheese", "cilantro" when category is "Herbs"). Use your judgment to create stable, general categories that would be useful for shopping organization.
- **Brand identification:** A brand is ONLY a proper noun referring to a manufacturer or store label. Words like "organic", "1%", "unsalted", "whole", "skim" are descriptive qualifiers, NOT brands. When uncertain whether something is a brand, default to null and put the word in qualifiers instead.
- **Possessives always indicate brands:** Any word with a possessive form ('s or s') is a brand name. Extract it as the brand and **never include it in qualifiers**.
- Preserve helpful usage hints in qualifiers, such as "for baking", "gluten free", "unsalted".
- Be case insensitive, but output brand and qualifiers in the capitalization provided by the user when possible.
- Handle common abbreviations ("oz", "lb", "kg") when determining quantity or size; sizes should be discarded.

Examples:
- "2x Lactantia 1% Milk" → {"quantity": 2, "quantity_string": "2x", "unit_descriptor": null, "brand": "Lactantia", "category": "Milk", "qualifiers": ["1%"]}
- "Bread" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": null, "category": "Bread", "qualifiers": []}
- "3 PC Chicken Breasts" → {"quantity": 3, "quantity_string": "3", "unit_descriptor": null, "brand": "PC", "category": "Chicken Breasts", "qualifiers": []}
- "Dozen eggs" → {"quantity": 12, "quantity_string": "Dozen", "unit_descriptor": null, "brand": null, "category": "Eggs", "qualifiers": []}
- "Milk for baking" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": null, "category": "Milk", "qualifiers": ["for baking"]}
- "Unsalted Butter 454g" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": null, "category": "Butter", "qualifiers": ["unsalted"]}
- "Organic 1% Milk" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": null, "category": "Milk", "qualifiers": ["organic", "1%"]}
- "Milk x2" → {"quantity": 2, "quantity_string": "x2", "unit_descriptor": null, "brand": null, "category": "Milk", "qualifiers": []}
- "Dad's Milk" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": "Dad's", "category": "Milk", "qualifiers": []}
- "Aunt Jemima's Pancake Mix" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": "Aunt Jemima's", "category": "Pancake Mix", "qualifiers": []}
- "1x Box of Dad's cookies" → {"quantity": 1, "quantity_string": "1x", "unit_descriptor": "Box of", "brand": "Dad's", "category": "Cookies", "qualifiers": []}
- "five apples" → {"quantity": 5, "quantity_string": "five", "unit_descriptor": null, "brand": null, "category": "Apples", "qualifiers": []}
- "One loaf of bread" → {"quantity": 1, "quantity_string": "One", "unit_descriptor": "loaf of", "brand": null, "category": "Bread", "qualifiers": []}
- "Feta" → {"quantity": 1, "quantity_string": null, "unit_descriptor": null, "brand": null, "category": "Cheese", "qualifiers": ["feta"]}
- "can tomatoes" → {"quantity": 1, "quantity_string": null, "unit_descriptor": "can", "brand": null, "category": "Tomatoes", "qualifiers": []}
- "wedge parmesan" → {"quantity": 1, "quantity_string": null, "unit_descriptor": "wedge", "brand": null, "category": "Cheese", "qualifiers": ["parmesan"]}
- "small container ricotta" → {"quantity": 1, "quantity_string": null, "unit_descriptor": "small container", "brand": null, "category": "Cheese", "qualifiers": ["ricotta"]}
- "1x Balderson old cheddar" → {"quantity": 1, "quantity_string": "1x", "unit_descriptor": null, "brand": "Balderson", "category": "Cheese", "qualifiers": ["old", "cheddar"]}
- "1x Wedge of Parmesan cheese" → {"quantity": 1, "quantity_string": "1x", "unit_descriptor": "Wedge of", "brand": null, "category": "Cheese", "qualifiers": ["Parmesan"]}
- "3x Pints of chicken stock" → {"quantity": 3, "quantity_string": "3x", "unit_descriptor": null, "brand": null, "category": "Stock", "qualifiers": ["chicken"]}
- "1x Bunch of cilantro" → {"quantity": 1, "quantity_string": "1x", "unit_descriptor": "Bunch of", "brand": null, "category": "Herbs", "qualifiers": ["cilantro"]}
- "1x Box of shallots (or 5 individual)" → {"quantity": 1, "quantity_string": "1x", "unit_descriptor": "Box of", "brand": null, "category": "Shallots", "qualifiers": ["or 5 individual"]}

Respond with ONLY valid JSON matching the schema. No explanations, markdown, or extra text.

/nothink
"""


class NormalizationAgent:
  def __init__(
    self,
    model_name: str = DEFAULT_NORMALIZER_MODEL,
    base_url: str | None = None,
    api_key: str | None = None,
    log: ActivityLog | None = None,
  ) -> None:
    self._model_name = model_name
    self._base_url = base_url.strip() if isinstance(base_url, str) and base_url.strip() else None
    self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
    self._log = log or ActivityLog()

  async def normalize(self, item_text: str) -> NormalizedItem:
    run_result = await self._agent.run(
      user_prompt=f"{SYSTEM_PROMPT}\n\nItem for analysis:{item_text}"
    )

    # Log model thinking if available
    thinking = run_result.response.thinking
    if thinking:
      self._log.normalizer.operation(f"Model thinking for '{item_text}':")
      self._log.normalizer.thinking(f"  {thinking}")

    partial = run_result.output
    json: dict[str, object] = {
      "original_text": item_text,
      **partial.model_dump(),
    }
    return NormalizedItem.model_validate(json)

  @cached_property
  def _agent(self) -> Agent[None, _PartialNormalizedItem]:
    # base_url = self._base_url
    # provider_api_key = self._api_key
    # provider = OllamaProvider(base_url=base_url, api_key=provider_api_key)
    # model = OpenAIChatModel(model_name=self._model_name, provider=provider)
    provider = GoogleProvider()
    model = GoogleModel(
      model_name="gemini-flash-lite-latest",
      provider=provider,
      settings=GoogleModelSettings(
        google_thinking_config={"include_thoughts": True, "thinking_budget": 2048}
      ),
    )
    return cast(
      Agent[None, _PartialNormalizedItem],
      Agent(
        model=model,
        output_type=_PartialNormalizedItem,
      ),
    )
