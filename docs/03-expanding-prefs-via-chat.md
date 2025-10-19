# Expanding Preferences Via Chat

## Overview

When the shopping agent encounters ambiguous choice scenarios—whether from vague list items, insufficient preferences, or out-of-stock conditions—it needs user guidance. This document describes the interactive Telegram-based resolution system that enables real-time decision-making during shopping sessions.

**Design Principle**: When automated preference matching leaves too many viable options or no viable options, pause the agent and obtain explicit user guidance through Telegram chat, then resume shopping with the user's choice.

## Problem Statement

The agent faces choice ambiguity in several scenarios:

1. **Generic list items without preferences**: User adds "milk" with no preference defined → search returns dozens of products
2. **Preferences still too broad**: Preference filters to "organic milk" but 20+ variants match on metro.ca
3. **Out of stock**: Preferred product unavailable → agent needs approval for substitute or skip
4. **No matches**: Search yields zero results → agent needs clarification or alternate term

Without intervention, the agent must either:
- Guess (wrong product, user removes from cart)
- Give up (mark `#404`, user manually adds later)

Both outcomes waste time and degrade automation value.

## Solution: Interactive Choice Resolution

When the agent encounters ambiguity, it:
1. Collects available product options from search results
2. Calls custom tool function `present_options()`
3. System formats options as numbered list and sends via Telegram
4. User selects from list, chooses "Nothing", or writes custom text
5. User's choice returns to agent
6. Agent resumes search/add with user guidance

### Timeout Handling

- **Standard agent timeout**: Does not apply while awaiting user response
- **Timeout reset**: After user replies, reset timeout to full duration for remaining agent operations
- **User response timeout**: Configurable maximum wait for user reply (default: 10 minutes)
  - If exceeded: mark item as failed, notify user, move to next item
  - User can configure longer timeout in preferences

## Architecture

```
Shopping Agent (BrowserAgent)
    │
    ├─> Encounters ambiguous choice
    │     - Too many matching products (>5)
    │     - Out of stock scenario
    │     - Zero matches but close variants available
    │
    └─> Calls custom tool: present_options()
          │
          └─> ChoiceResolver (new component)
                ├─> Formats numbered option list
                ├─> Sends to TelegramNotifier
                │
                └─> TelegramNotifier
                      ├─> Sends message via python-telegram-bot
                      ├─> Starts polling for user response
                      │
                      └─> User receives Telegram message:
                            🛒 Shopping for: milk

                            I found multiple options:

                            1. President's Choice 2L 1% Milk ($4.99)
                            2. Natrel 2L 1% Milk ($5.49)
                            3. Lactantia 2L 1% Milk ($5.29)
                            4. Organic Meadow 2L 1% Milk ($6.99)
                            5. Nothing (skip this item)
                            6. Something else (reply with text)

                            Reply with a number or describe what you want.
                      │
                      ├─> User replies: "2"
                      │
                      └─> TelegramNotifier returns choice to ChoiceResolver
                            │
                            └─> ChoiceResolver maps "2" → "Natrel 2L 1% Milk"
                                  │
                                  └─> Returns OptionsResult to agent
                                        │
                                        └─> Agent continues with user's choice
```

## Implementation Components

### ChoiceResolver

**Location:** `src/gemini_supply/grocery/choice_resolver.py`

**Responsibilities:**
- Receive product options from agent via tool function
- Format options as structured numbered list
- Delegate message sending to `TelegramNotifier`
- Block until user response received
- Map user response back to product choice
- Return result to agent

**Key Methods:**
- `present_options(item_name: str, options: list[ProductOption], context: str) -> UserChoice`
  - `item_name`: Shopping list item being resolved
  - `options`: List of available product choices (name, price, URL)
  - `context`: Agent's explanation of the situation
  - Returns `UserChoice` with selected product or instructions

**Type Definitions:**
- `ProductOption`: TypedDict with `name: str`, `price: str`, `url: str`, `product_id: str`
- `UserChoice`: TypedDict with `choice_type: Literal["product", "nothing", "custom"]`, `value: str`, `product_option: Optional[ProductOption]`

**Behavior:**
- Always includes "Nothing" as last numbered option (skip item)
- Always includes "Something else" as final option (custom text)
- Blocks execution until user responds or timeout occurs
- On timeout: returns `UserChoice(choice_type="nothing", value="timeout", product_option=None)`

### TelegramNotifier

**Location:** `src/gemini_supply/grocery/telegram_notifier.py`

**Responsibilities:**
- Initialize `python-telegram-bot` client
- Send formatted messages to user via Telegram bot
- Poll for and receive user responses
- Handle message threading (match responses to questions)
- Manage conversation state during user interaction

**Configuration Requirements:**
- Bot token (from BotFather)
- User phone number or chat ID for direct messaging
- Stored in `~/.config/gemini-supply/config.yaml`:

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"
  user_chat_id: "YOUR_CHAT_ID"
  response_timeout: 600  # seconds (default: 10 minutes)
```

**Key Methods:**
- `send_choice_request(item_name: str, options: list[str], context: str) -> str`
  - Formats and sends numbered options to user
  - Returns message ID for response correlation
- `wait_for_response(message_id: str, timeout: int) -> str`
  - Blocks until user replies or timeout expires
  - Returns user's text response
- `send_notification(message: str) -> None`
  - Sends informational message (shopping started, completed, etc.)

**Library:** `python-telegram-bot`
- Install: `uv add python-telegram-bot`
- Documentation: https://python-telegram-bot.org/
- Supports both polling and webhook modes (use polling for simplicity)

### Agent Tool Function

**Custom Tool Function:** `present_options(item_name, options, context)`

**Registration:**
- Define `present_options` function with TypedDict return type in `agent.py`
- Return type: `OptionsResult` (TypedDict)
- Add `OptionsResult` to `FunctionResponseT` union type
- Register with `FunctionDeclaration.from_callable()` in `BrowserAgent.__init__()`
- Add handler case in `BrowserAgent.handle_action()`

**Function Signature:**
```python
def present_options(
    item_name: str,
    options: list[ProductOption],
    context: str
) -> OptionsResult:
    """
    Present product options to user and wait for selection.

    Args:
        item_name: Shopping list item being resolved
        options: List of product choices (name, price, url, product_id)
        context: Agent's explanation of why choice is needed

    Returns:
        OptionsResult with user's selection
    """
```

**Type Definition:**
```python
class OptionsResult(TypedDict):
    item_name: str
    choice_type: Literal["product", "nothing", "custom"]
    selected_product: str  # Product name, "nothing", or custom text
    product_url: str | None  # URL if choice_type == "product"
    product_id: str | None  # metro.ca product ID if available
```

**Agent Behavior After Tool Call:**
- If `choice_type == "product"`: Navigate to `product_url` and add to cart
- If `choice_type == "nothing"`: Call `report_item_not_found()` with explanation
- If `choice_type == "custom"`: Resume search with `selected_product` as new query

### Integration with Shopping Orchestrator

**Orchestrator Modifications:**

1. **Initialization:**
   - Create `TelegramNotifier` instance at start of shopping session
   - Pass notifier to `ChoiceResolver` during instantiation
   - Pass `ChoiceResolver` to each `BrowserAgent` instance

2. **Timeout Management:**
   - Detect when agent calls `present_options()` tool
   - Pause standard agent timeout
   - Wait for `OptionsResult` return
   - Reset timeout to full duration before resuming agent operations

3. **Error Handling:**
   - If user response timeout occurs: treat as `choice_type="nothing"`
   - If Telegram API fails: fall back to `report_item_not_found()` behavior
   - Log all user interactions for debugging

4. **Session Notifications:**
   - Send "Shopping session started" notification at beginning
   - Send "Shopping session completed" with summary at end
   - Send "Waiting for your input" when `present_options()` called

## User Experience Flow

### Scenario 1: Generic Item, No Preference

**Shopping list item:** "milk"

1. Agent searches metro.ca for "milk"
2. Finds 40+ products
3. Calls `present_options()` with top 5 matches:
   ```
   🛒 Shopping for: milk

   I found many milk options. Which would you like?

   1. President's Choice 2L 1% Milk ($4.99)
   2. Natrel 2L 1% Milk ($5.49)
   3. Lactantia 2L 1% Milk ($5.29)
   4. Organic Meadow 2L 1% Milk ($6.99)
   5. Sealtest 2L 2% Milk ($4.79)
   6. Nothing
   7. Something else
   ```
4. User replies: **1**
5. Agent adds President's Choice 2L 1% Milk to cart
6. Calls `report_item_added()`

### Scenario 2: Out of Stock

**Shopping list item:** "milk" (with preference for PC 2L 1%)

1. Agent searches for preferred product
2. Finds product page but "Out of Stock" indicator present
3. Performs fallback search for similar products
4. Calls `present_options()` with alternatives:
   ```
   🛒 Shopping for: milk

   Your preferred PC 2L 1% Milk is out of stock.
   Would you like a substitute?

   1. Natrel 2L 1% Milk ($5.49)
   2. Lactantia 2L 1% Milk ($5.29)
   3. Nothing (skip this item)
   4. Something else
   ```
5. User replies: **3** (Nothing)
6. Agent calls `report_item_not_found()` with explanation: "Preferred product out of stock, user declined substitutes"

### Scenario 3: Custom Text Response

**Shopping list item:** "yogurt"

1. Agent searches for "yogurt"
2. Finds 30+ products
3. Calls `present_options()` with top 5
4. User replies: **Something else** → then types: "Greek yogurt 0% plain large tub"
5. Agent receives `choice_type="custom"`, `selected_product="Greek yogurt 0% plain large tub"`
6. Agent performs new search with refined query
7. Either finds product and adds to cart, or presents options again if still ambiguous

## Configuration

### Setup Requirements

1. **Create Telegram Bot:**
   - Message @BotFather on Telegram
   - Command: `/newbot`
   - Follow prompts to name bot
   - Receive bot token

2. **Get Chat ID:**
   - Start conversation with your new bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your `chat_id` in response JSON

3. **Configure gemini-supply:**
   ```yaml
   # ~/.config/gemini-supply/config.yaml
   telegram:
     bot_token: "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
     user_chat_id: "987654321"
     response_timeout: 600  # 10 minutes
   ```

4. **Test Connection:**
   ```bash
   uv run grocery-agent test-telegram
   ```
   - Sends test message via bot
   - Confirms configuration is correct

### Environment Variables (Alternative)

```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_USER_CHAT_ID="your_chat_id"
```

Configuration file takes precedence over environment variables.

## Design Decisions

### Why Telegram?

- **Ubiquitous**: Most users already have Telegram installed
- **Simple API**: `python-telegram-bot` provides clean, well-documented interface
- **Reliable**: Battle-tested for bot interactions
- **Push notifications**: User gets notified immediately when choice needed
- **Persistent history**: User can review past choices

### Why Numbered Options?

- **Low friction**: Single digit response, no typing required
- **Mobile-friendly**: Easy to tap on phone
- **Unambiguous**: No parsing errors, direct index mapping
- **Accessible**: Works on any device, any Telegram client

### Why "Nothing" and "Something Else"?

- **Nothing**: Gives user explicit skip option instead of ignoring notification
- **Something Else**: Allows flexible text input without breaking numbered option model
- **User control**: Prevents agent from making unwanted substitutions

### Timeout Strategy

- **No timeout during user wait**: Agent doesn't consume resources or fail while waiting
- **Reset after response**: User gets full agent timeout for post-response operations
- **Configurable user timeout**: Different users have different availability/preferences
- **Graceful degradation**: Timeout treated as "skip item", not fatal error

## Error Handling

### Telegram API Failures

| Error | Detection | Action |
|-------|-----------|--------|
| Invalid bot token | Exception during client initialization | Log error, disable Telegram integration, fall back to `report_item_not_found()` |
| Network timeout | Exception during message send | Retry once, then fall back to `report_item_not_found()` |
| User blocked bot | Error response from Telegram API | Log warning, disable Telegram for session, fall back to `report_item_not_found()` |
| Chat ID invalid | Error response from send_message | Log error, disable Telegram integration, fall back to `report_item_not_found()` |

### User Response Issues

| Issue | Detection | Action |
|-------|-----------|--------|
| User doesn't respond | Timeout expires | Treat as `choice_type="nothing"`, mark item as failed with note |
| Invalid number response | Parse error (not 1-N) | Reply "Invalid choice, please select 1-N", wait again |
| Ambiguous text | N/A | Pass directly to agent as custom query |

### Agent Integration Failures

| Failure | Detection | Action |
|---------|-----------|--------|
| `present_options()` tool not registered | Exception during agent initialization | Fail fast with clear error message |
| ChoiceResolver unavailable | Exception during tool call | Fall back to `report_item_not_found()` |
| Agent doesn't call any completion tool | Agent timeout after choice provided | Mark as failed, log warning about incomplete agent behavior |

## Security Considerations

### Bot Token Storage

- **Never commit to git**: Add `config.yaml` to `.gitignore`
- **File permissions**: `chmod 600 ~/.config/gemini-supply/config.yaml`
- **Rotation**: If token exposed, revoke via @BotFather and update config

### User Authentication

- **Chat ID filtering**: Bot only responds to configured `user_chat_id`
- **Reject unknown users**: Ignore messages from other chat IDs
- **No public bot**: This is single-user automation, not multi-user service

### Data Privacy

- **No storage of messages**: Don't persist user responses beyond session
- **No sharing**: Product choices remain local to user's system
- **Minimal logging**: Log user choice events, not message contents

## Testing Strategy

### Manual Testing

1. **Happy path**: Generic item → options presented → user selects → item added
2. **Out of stock**: Preferred item unavailable → alternatives → user picks substitute
3. **Custom text**: User writes description → agent searches → finds product
4. **Timeout**: Don't respond → verify timeout handling → item marked failed
5. **Invalid input**: Send "99" when only 5 options → verify error handling

### Integration Testing

- Mock `TelegramNotifier` to simulate user responses
- Test `ChoiceResolver` logic without actual Telegram API calls
- Verify agent continues correctly after receiving `OptionsResult`
- Test timeout reset behavior

### Configuration Validation

- Missing bot token → clear error message
- Invalid chat ID → graceful fallback
- Telegram disabled → shopping works without interruption

## Future Enhancements

Potential features not yet implemented:

- **Image attachments**: Send product images with options for visual confirmation
- **Quick reply buttons**: Use Telegram inline keyboards instead of numbered text
- **Multi-user support**: Different users, different shopping lists, single bot
- **Preference learning**: "Always pick option 1 for milk" → auto-apply pattern
- **Voice input**: Accept voice messages, transcribe to text query
- **Receipt photos**: After checkout, send photo of receipt via Telegram
- **Price alerts**: Notify when preferred items go on sale
- **Conversation history**: View past choices and refine preferences based on patterns
