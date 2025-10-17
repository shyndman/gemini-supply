# Product Preferences

## Overview

When users add generic items like "milk" to a shopping list, the agent needs to resolve them to specific products (e.g., "2L 1% lactose-free milk, President's Choice"). This document describes the product preference system that enables this resolution.

**Design Principle**: User-specific preferences guide agent search behavior through a hybrid search strategy with no automatic substitutions. Items that cannot be found are marked with `#404` tag per the main design document.

## Architecture

```
Shopping List Item: "milk"
         │
         ├──> PreferenceMappingAgent
         │      - Receives: item name + full preference list
         │      - Returns: matched preference key or null
         │
         ├──> PreferencesManager.get_preference(matched_key)
         │
         └──> Preference Found:
                 - search_terms: ["milk 1% lactose free 2L", "milk lactose free", "milk"]
                 - attributes: {fat_content: "1%", dietary: ["lactose-free"], size: "2L"}
                 - description: "2L 1% lactose-free milk"
         │
         └──> Task Prompt Enhanced with Preference Details
                 - Ordered search attempts
                 - Attribute validation requirements
                 - Brand preferences
         │
         └──> Shopping Agent executes hybrid search strategy
         │
         └──> If not found: mark_not_found() → adds #404 tag
```

## Preference Configuration

### File Structure

**Location:** `~/.config/gemini-supply/preferences.yaml`

Preferences map generic item names (normalized, lowercase) to product specifications:

```yaml
preferences:
  milk:
    search_terms:
      - "milk 1% lactose free 2L President's Choice"  # Most specific
      - "milk 1% lactose free 2L"                      # Without brand
      - "milk lactose free"                            # Core requirements
      - "milk"                                         # Generic fallback

    attributes:
      fat_content: "1%"
      dietary: ["lactose-free"]
      size: "2L"
      brand: "President's Choice"

    description: "2L container of 1% lactose-free milk, preferably President's Choice brand"
```

### Attribute Types

Preferences support flexible attributes including:
- **brand**: Preferred brand name
- **size**: Package dimensions (e.g., "2L", "454g")
- **dietary**: Array of dietary requirements (e.g., `["lactose-free", "gluten-free"]`)
- **fat_content**: Fat percentage for dairy
- **organic**: Boolean flag
- **type**: Product sub-category (e.g., "sourdough", "greek")
- **grain**: Grain type for baked goods
- **flavor**: Flavor variant
- **salted**: Boolean for salted vs unsalted

Attributes are extensible—add any key-value pairs relevant to product selection.

## Hybrid Search Strategy

The agent attempts searches in order of decreasing specificity:

1. **Most specific**: Full search term with all preferences
   - If products found → validate against attributes → select best match

2. **Reduced specificity**: Drop brand, keep core attributes
   - If products found → validate against attributes → select best match

3. **Minimal requirements**: Essential attributes only
   - If products found → validate against attributes → select best match

4. **Generic fallback**: Base item name only
   - If products found → validate against attributes → select best match

5. **Not found**: Report to user with explanation

### Validation and Selection

For each search result set, the agent:
- Checks product descriptions/titles for required attributes
- Prioritizes products matching more attributes
- Prefers specified brand when available
- Selects best match based on attribute alignment

### No Automatic Substitution

If the preferred product is unavailable or out of stock:
- Shopping agent calls `report_item_not_found()` with explanation
- Orchestrator calls `provider.mark_not_found(item_id, explanation)`
- Provider adds `#404` tag to item (per main design document)
- No automatic substitution with alternatives
- User maintains control over product choices

**Rationale**: Prevents unwanted substitutions; user gets clear feedback about availability.

## Task Prompt Enhancement

### Without Preferences
Standard prompt searches generically and relies on agent judgment for product selection.

### With Preferences
Enhanced prompt includes:
- Product description for context
- Ordered list of search terms to attempt
- Required attributes for validation
- Brand preference guidance
- Instructions to report if requirements cannot be met

The agent understands both the search strategy and validation criteria before beginning.

## Implementation Components

### PreferenceMappingAgent

**Location:** `src/gemini_supply/grocery/preference_mapper.py`

**Purpose:** Intelligently maps user-written shopping list items to defined preference keys using an LLM agent.

**Problem it solves:** Users write shopping list items in various ways ("milk", "2% milk", "dairy milk", "some milk") but preferences are keyed by canonical names. Direct string matching fails.

**Responsibilities:**
- Receive shopping list item name and full list of available preference keys
- Use Gemini API to determine which preference (if any) matches the user's intent
- Return matched preference key or `None`
- Provide custom tool function: `report_preference_match(preference_key: str | None, confidence: str, reasoning: str)`

**Design:**
- Single-shot agent invocation per item (not a browser agent)
- Lightweight and fast (no browser overhead)
- Prompt includes: user's item name, all available preference keys with descriptions
- Agent responds with tool call containing match result

**Tool Function:**
- `report_preference_match(preference_key, confidence, reasoning)`:
  - `preference_key`: Matched key from preferences, or `None` if no match
  - `confidence`: "high", "medium", "low"
  - `reasoning`: Brief explanation of why this preference was chosen

**Integration with Orchestrator:**
1. Orchestrator retrieves uncompleted item from provider
2. Calls `PreferenceMappingAgent.map_item(item_name, available_preferences)`
3. Agent returns matched preference key or `None`
4. Orchestrator uses matched key to lookup full preference via `PreferencesManager`
5. Continues with shopping agent using preference-enhanced prompt

**Type Definitions:**
- `PreferenceMatchResult`: TypedDict with `preference_key: str | None`, `confidence: str`, `reasoning: str`

### PreferencesManager

**Location:** `src/gemini_supply/grocery/preferences.py`

**Responsibilities:**
- Load preferences from YAML configuration file
- Provide lookup by preference key
- Return structured `ProductPreference` objects
- Default to `~/.config/gemini-supply/preferences.yaml`
- Provide list of all available preference keys with descriptions for mapping agent

**Key Methods:**
- `get_preference(key: str) -> Optional[ProductPreference]`: Retrieve preference by exact key
- `get_all_preference_keys() -> list[str]`: Return all available preference keys
- `get_preference_summaries() -> dict[str, str]`: Return key -> description mapping for agent
- `has_preference(key: str) -> bool`: Check if preference exists

**Type Definitions:**
- `ProductAttributes`: TypedDict for flexible attribute definitions (all fields optional)
- `ProductPreference`: TypedDict containing `search_terms`, `attributes`, and `description`

### Orchestrator Integration

**Modifications to `grocery_main.py`:**

The orchestrator integrates preference mapping and preferences into the shopping flow:

1. Initialize `PreferencesManager` at start of shopping session
2. Initialize `PreferenceMappingAgent` at start of shopping session
3. For each shopping list item:
   - Call `PreferenceMappingAgent.map_item(item.name, preferences_mgr.get_preference_summaries())`
   - If match found with "high" or "medium" confidence:
     - Query `PreferencesManager.get_preference(matched_key)` for full preference
     - Build enhanced task prompt with preference details
   - If no match or "low" confidence:
     - Build standard task prompt without preferences
   - Pass prompt to shopping `BrowserAgent`
4. Shopping agent behavior remains unchanged—preferences are communicated through task prompt only

**Prompt Building:**
- `build_task_prompt(item_name: str, preference: Optional[ProductPreference]) -> str`
- Returns standard prompt if no preference provided
- Returns enhanced prompt with search strategy and validation criteria if preference provided

## Best Practices

### Search Term Design

Structure search terms from most to least specific, with meaningful fallback steps:
- Start with all attributes and brand
- Drop brand for second attempt
- Reduce to core requirements
- End with generic search

Avoid consecutive terms that are too similar (no fallback benefit) or too different (poor progression).

### Attribute Specificity

Be specific but realistic about product availability. Overly specific attributes (exact SKUs, unusual measurements) may never match products on metro.ca.

### Description Clarity

Write descriptions that clearly convey product requirements to the agent:
- Good: "2L 1% lactose-free milk"
- Avoid: "Good milk" or "The milk I like"

## Troubleshooting

### Wrong Product Selected
- Make first search term more specific
- Add detailed attributes for validation
- Clarify description
- Verify preferred product exists on metro.ca

### Item Not Found Despite Availability
- Add more fallback search terms
- Simplify overly specific search terms
- Check product name spelling
- Verify attributes aren't too restrictive

### Preferences Not Loading
- Verify file location: `~/.config/gemini-supply/preferences.yaml`
- Validate YAML syntax (indentation, structure)
- Check file permissions (should be readable)
- Review orchestrator logs for loading errors

### Agent Ignoring Preferences
- Check `PreferenceMappingAgent` logs to see if item was matched to preference
- Verify mapping agent returned "high" or "medium" confidence
- Review mapping agent reasoning for why it chose (or didn't choose) a preference
- Validate YAML structure and syntax
- Check orchestrator passes matched preferences to prompt builder

## Future Enhancement Opportunities

Potential features not yet implemented:
- **Learning from behavior**: Track kept vs removed products, adjust preferences automatically
- **Preference profiles**: Multiple preference sets switchable by flag (e.g., "budget", "premium")
- **Store-specific preferences**: Different preferences per grocery store
- **Substitution chains**: Define acceptable alternatives when preferred unavailable
- **Price constraints**: Maximum acceptable price per item
- **Seasonal preferences**: Adapt preferences based on season/availability
