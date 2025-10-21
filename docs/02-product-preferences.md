# Product Preference Resolution

## Overview
Introduce a per-item preference system so ambiguous shopping-list entries resolve to the user’s preferred products without manual re-selection. The feature layers a normalization pass, persistent preference storage, and a human-in-the-loop chat flow on top of the existing metro.ca automation.

## Goals
- Convert free-form shopping-list text into canonical keys using a Pydantic AI normalization agent.
- Persist `{canonical_key → chosen product}` mappings in a dedicated YAML file referenced from the main config.
- Let the browser agent request human decisions when it cannot select a product confidently, then reuse those choices automatically.
- Keep the conversation experience single-threaded and patient (no timeouts) while multiple agents run in parallel.

## Non-Goals
- Handling multiple retailers or lists beyond metro.ca.
- Managing historical versions of preferences or enabling quick rollback.
- Providing automatic recovery if the orchestrator crashes mid-conversation.

## Normalization Agent
- **Invocation**: Run once per shopping-list item (YAML or Home Assistant) before any preference lookup. The orchestrator calls a Pydantic AI agent with the raw item text.
- **Outputs**:
  - `canonical_key`: Deterministic slug derived from the parsed category (e.g., `milk`).
  - `category_label`: Human-friendly category label to display in chat (e.g., `Milk`).
  - `original_text`: Exact user input for context.
  - `quantity`: Parsed item quantity (defaults to 1 when unspecified).
  - `brand`: Detected brand name or `null` if none supplied.
- **Usage**: The canonical key anchors preference lookups, while the category label and original text seed chat prompts. Quantity and brand are available for future enhancements (e.g., analytics or validation) but do not affect preference matching yet.

## Preference Storage
- **Config hook**: Add a `preferences` block to `config.yaml`.
  - `file`: Path (absolute or relative) to the YAML store for canonical mappings.
  - `normalizer_model`: OpenAI-compatible model to use for categorization (default `qwen3:1.7b`).
  - `normalizer_api_base_url`: Optional base URL for OpenAI-compatible providers (e.g., Ollama `http://ollama/v1`). If omitted, falls back to environment variables.
  - `normalizer_api_key`: Optional API key for the provider (or use `OPENAI_API_KEY`, `GEMINI_API_KEY`, or provider-specific env vars).
  - `telegram.bot_token`, `telegram.chat_id`: Enable human-in-the-loop prompting.
  - `telegram.nag_minutes` (optional): Reminder cadence, defaults to 30.
- **File**: YAML map keyed by `canonical_key`. Each value stores:
  - `product_name`: The metro.ca display name selected by the user.
  - `product_url`: The product page URL (for deterministic navigation).
  - `metadata`: Includes `category_label`, optional `brand`, and `updated_at_iso`.
- **Concurrency**: Preference writes are protected with an async mutex; updates load into memory, mutate, and atomically write back. No temp-file dance needed.

## Orchestrator Flow
1. Normalize shopping-list item.
2. Check preference store; if a match exists, hand the product descriptor to the browser agent and continue.
3. If no preference exists, let the browser agent attempt autonomous resolution.
4. If the agent cannot uniquely select a product, it compiles a shortlist (display name + URL + descriptors) and calls an orchestrator tool.
5. The orchestrator enqueues the request; only the head item is surfaced to the user chat.
6. While waiting, the requesting browser agent pauses. Other agents can continue until they require input.
7. Once a decision arrives:
   - `option N`: Persist mapping under the original canonical key and resume the paused agent with the product descriptor.
   - `skip`: Resume without changes, leaving the item unresolved this run.
   - Free text: Re-run normalization on the user’s message, treat it as the new target, and loop back to step 3 (still updating the original key if a product is chosen).

## Chat Resolution Subflow
- **Channel**: Single shared chat (e.g., Telegram group). The orchestrator ensures only one outstanding request at a time.
- **Prompt**: Include the normalized category label (e.g., “Milk”), the user’s original text, and numbered options. Offer “skip” explicitly and remind the user they can reply with an alternative product.
- **Queue discipline**: Replies always apply to the head of the queue. No parallel conversations or IDs required.
- **Timeouts**: None. The run remains pending until the user responds.
- **Nagging**: Every 30 minutes, send a reminder using a random string from a predefined constant list (to be populated later). Reminders restate the surface label and how to respond (“tap a button, reply with 1-10, send skip, or describe something else”).
- **State**: Keep transient queue state in memory; on orchestrator restart, unresolved items simply re-enqueue when their agents resurface the issue.

## Browser Agent Contract
- Provide a tool to emit an “unresolved choice” payload: normalized descriptors, shortlisted product options, and the requesting agent ID.
- Suspend its workflow until the orchestrator replies with the selected product or skip instruction.
- On selection, continue the checkout flow with the supplied product descriptor. On skip, mark the item as unresolved/not found as today.

## Skip Behavior
- “Skip” means do not add to cart this run and do not modify any existing preference. The preference map remains untouched.

## Reminder Strings
- Define `DEFAULT_NAG_STRINGS` in `src/gemini_supply/preferences/constants.py`. Each reminder picks randomly from this list to keep UX lighthearted.

## Telegram Bot Integration
- Use `python-telegram-bot` as the orchestration chat layer. Run the async `Application` with polling; we only keep one active prompt so handlers can stay sequential (`block=True`).
- Queue human decisions by sending up to 10 numbered buttons plus a single "Skip" button. Users can still type `1-10` manually or reply with alternative text; the handler interprets numbers as selections and pushes everything else back through normalization.
- Schedule the 30-minute reminder loop with PTB’s `JobQueue`, drawing a message from `PREFERENCE_NAG_STRINGS` and re-posting the unresolved item prompt.
- Keep orchestration state in memory only. If the process restarts, the next run reruns normalization and re-requests any outstanding choices.

## Future Considerations
- Optional preference-edit CLI for manual adjustments.
- Extending the schema with quantity/price ceilings.
- Persisting in-progress conversations for resilience if restarts become common.
