# Grocery Agent Design Document

## Overview

This document describes the design and implementation plan for enhancing gemini-supply to automatically add items from a shopping list to a metro.ca shopping cart using the Gemini Computer Use API.

**Scope**: Single-user personal automation for grocery shopping
**Target Site**: metro.ca (Canadian grocery delivery)
**Data Source**: Shopping list (YAML file or external provider integration)

## Use Case

1. User adds items to shopping list over time
2. User runs the agent with a shopping list path: `uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml`
3. Agent processes ALL uncompleted items sequentially (one agent instance per item)
4. For each item:
   - Agent adds item to cart
   - Agent calls custom tool function to report success/failure with details
   - System updates shopping list immediately
5. After all items processed, system generates summary report
6. User receives notification with results (items added, prices, failures)
7. User manually reviews cart and completes checkout when ready

## Core Requirements

### Functional Requirements

1. **Batch Processing**: Process all uncompleted items in single invocation, one agent per item
2. **Custom Tool Functions**: Provide agent with `report_item_added()` and `report_item_not_found()` tools
3. **Cart Management**: Add items to metro.ca cart sequentially during single shopping session
4. **State Tracking**: Track which items have been added, failed, or not found (update list immediately)
5. **Authentication**: Reuse saved authentication without exposing credentials to LLM
6. **Safety Constraints**: Prevent agent from leaving metro.ca domain or accessing sensitive pages
7. **Summary Reporting**: Generate comprehensive report after all items processed
8. **Result Details**: Capture item name, price, URL, quantity for successful additions
9. **Failure Explanations**: Capture agent's explanation when items cannot be found

### Non-Functional Requirements

1. **Security**: No credentials shared with LLM; authentication via saved browser state
2. **Reliability**: Graceful handling of session expiry, product not found, cart limits
3. **Observability**: Clear logging and status reporting
4. **Speed**: Fast enough for incremental addition (one item at a time)
5. **Maintainability**: Resilient to minor metro.ca UI changes (no brittle selectors)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 Shopping List Provider                       │
│                 (Interface: ShoppingListProvider)            │
│                                                              │
│  Shopping List Data:                                        │
│    ☐ milk                                                    │
│    ☐ bread                                                   │
│    ☑ eggs (completed = in cart)                             │
│    ☐ butter #404 (not found)                                │
│                                                              │
│  Implementations:                                           │
│    - YAMLShoppingListProvider (local file)                  │
│    - HomeAssistantProvider (see 01-home-assistant-*.md)     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                   ▲
                   │ (queries list, updates immediately)
                   │
┌─────────────────────────────────────────────────────────────┐
│              Grocery Shop Orchestrator                       │
│              (grocery_main.py: shop command)                 │
│                                                              │
│  While uncompleted items exist:                             │
│    1. Get next uncompleted item from provider               │
│    2. Initialize protected browser with saved auth          │
│    3. Create task prompt with custom tool functions         │
│    4. Run BrowserAgent (single item)                        │
│    5. Agent calls report_item_added() or                    │
│       report_item_not_found()                               │
│    6. Update shopping list via provider immediately         │
│    7. Collect results for summary                           │
│    8. Close browser, spin up new agent for next item        │
│                                                              │
│  After all items:                                           │
│    - Save refreshed auth state                              │
│    - Generate summary report                                │
│    - Send summary via provider                              │
│                                                              │
└──────────────────┬──────────────────────────────────────────┘
                   │ (creates for each item)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Enhanced Browser Agent                      │
│                  (agent.py - with custom functions)          │
│                                                              │
│  Custom Tool Functions:                                     │
│    - report_item_added(item_name, price, url, quantity)    │
│    - report_item_not_found(item_name, explanation)         │
│                                                              │
│  Task Prompt:                                               │
│    "Add {item} to metro.ca cart.                            │
│     When done, call report_item_added() with details        │
│     If not found, call report_item_not_found()"            │
│                                                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│            Protected Playwright Computer                     │
│            (computers/protected_computer.py)                 │
│                                                              │
│  Security Features:                                         │
│    ✓ Load saved authentication context                      │
│    ✓ Block checkout/payment/login pages                     │
│    ✓ Domain restriction (metro.ca only)                     │
│    ✓ Inject UI banner showing current item                  │
│                                                              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  State Management                            │
│                                                              │
│  Shopping List Provider Interface:                          │
│    - mark_completed(item_id): Mark item as added to cart   │
│    - mark_not_found(item_id, explanation): Tag as #404     │
│    - mark_failed(item_id, error): Tag as #failed           │
│    - send_summary(summary): Deliver final report            │
│                                                              │
│  Results Collection:                                        │
│    - List of successfully added items (with prices/URLs)    │
│    - List of not found items (with explanations)           │
│    - Total estimated cost                                   │
│                                                              │
│  Profile (Persistent):                                      │
│    ~/.config/gemini-supply/camoufox-profile                 │
│    (cookies/tokens persist as you browse)                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Design

### 1. Shopping List Provider Interface

**Abstract Interface:**

Define a `ShoppingListProvider` Protocol with the following methods:
- `get_uncompleted_items()` → Returns list of `ShoppingListItem` objects (name, id, status)
- `mark_completed(item_id)` → Mark item as successfully added to cart
- `mark_not_found(item_id, explanation)` → Mark item as not found with explanation
- `mark_failed(item_id, error)` → Mark item as failed with error message
- `send_summary(summary)` → Deliver final `ShoppingSummary` after all items processed

Types needed:
- `ShoppingListItem`: name (str), id (str), status (Literal["needs_action", "completed"])
- `ShoppingSummary`: added_items, not_found_items, failed_items, total_cost

**Built-in Implementation: YAMLShoppingListProvider**

Reads/writes to `~/.config/gemini-supply/shopping_list.yaml` with items array containing:
- Basic fields: id, name, status
- Optional fields: tags (array), explanation (string for failures)

Behavior:
- `mark_completed()`: Updates status to "completed"
- `mark_not_found()`: Adds "#404" tag and stores explanation
- `mark_failed()`: Adds "#failed" tag and stores error
- `send_summary()`: Writes formatted summary to `~/.config/gemini-supply/last_shopping_summary.txt`

**Alternative Implementations:**

See separate documentation for integrations:
- `01-home-assistant-shopping-lists.md`: Integration with Home Assistant

### 2. Trigger Mechanism

**Manual Invocation (Subcommand):**
```bash
uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml
```

Where `--shopping-list` points to a YAML shopping list file. This subcommand:
- Queries shopping list provider for ALL uncompleted items
- Processes each item sequentially (one agent instance per item)
- Generates summary report after all items processed
- Sends summary via provider

### 3. Authentication Management

**Automated Setup:**
- Provide metro.ca credentials via environment variables:
  - `GEMINI_SUPPLY_METRO_USERNAME`
  - `GEMINI_SUPPLY_METRO_PASSWORD`
- The shopping orchestrator runs the automated login routine before any agents start.
- Default profile (Linux): `~/.config/gemini-supply/camoufox-profile`

**Automated Usage:**
- Browser always launches a persistent context bound to the profile directory
- Cookies/local storage/session storage persist on disk and are reused automatically

**Session Refresh:**
- Session refresh is automatic: the persistent profile is updated continuously as the browser runs

**Expiry Handling:**
- DOM-based authentication check (see below) determines if session is valid
- On expiry, the orchestrator gates a single automated re-login and retries the in-flight item once
- If re-authentication fails, mark the item as `auth_recovery_failed` and continue

**Session Lifetime:** ~1 week (to be validated in practice)

**DOM Authentication Check:**
- Implement `is_authenticated()` in the Metro browser class
- Heuristic: presence of `#authenticatedButton` indicates authenticated; absence indicates unauthenticated
- Called from `current_state()` and after first navigation to metro.ca
- On unauthenticated: raise `AuthExpiredError` for the orchestrator to handle

### 4. Domain Restrictions & Safety

**Blocked URL Patterns:**
- Checkout/payment pages: `/checkout`, `/payment`, `/billing`
- Authentication pages: `/login`, `/logout`, `/signup`, `/register`
- Account management: `/account/settings`, `/account/edit`, `/password`, `/password-reset`

**Domain Restrictions:**
- Allow only: `https://www.metro.ca` and essential hosts (see allowlist below)
- Block all other external domains by default

**Implementation:**
- Playwright route handler intercepts all requests
- Check URL against blocked patterns and domain whitelist
- Abort blocked requests, continue allowed ones
- Log blocked hosts to help tune the allowlist over time

**Metro Browser Class:**
- A specialized Playwright subclass, `CamoufoxMetroBrowser`, will:
  - Launch Firefox via Camoufox with a persistent user data dir (authentication persistence)
  - Enforce domain allowlist and URL blocklist
  - Inject a status banner on every document load and keep it updated across SPA route changes
  - Log blocked hosts for developer visibility

**Recommended Domain Allowlist (Observed):**
- Required for core shopping:
  - `www.metro.ca` — main app, styles, JS, icons
  - `product-images.metro.ca` — product images
  - `d94qwxh6czci4.cloudfront.net` — main app bundle for search/results
  - `static.cloud.coveo.com` — Coveo analytics library used by search
- Nice-to-have/benign assets:
  - `use.typekit.net`, `p.typekit.net` — web fonts
  - `cdn.cookielaw.org` — cookie consent banner
  - `cdn.dialoginsight.com` — newsletter/opt‑in form scripts
- Optional analytics/tracking (block by default unless needed):
  - Google: `www.googletagmanager.com`, `analytics.google.com`, `www.google.com/gmp`, `www.google.com/recaptcha`, `www.gstatic.com`
  - Ads: `ad.doubleclick.net`, `googleads.g.doubleclick.net`, `securepubads.g.doubleclick.net`, `*.fls.doubleclick.net`, `dynamic.criteo.com`
  - Social: `connect.facebook.net`, `www.facebook.com`
  - Microsoft: `bat.bing.com`, `www.clarity.ms`
  - Fraud/anti‑abuse (mostly relevant near checkout): `cdn0.forter.com`, `cdn4.forter.com`
- Metro telemetry endpoints (permit if harmless; review responses):
  - `*.a.run.app` (e.g., `mpc2-prod-1-is5qnl632q-uc.a.run.app`)
  - `db7q4jg5rkhk8.cloudfront.net`, `d2o5idwacg3gyw.cloudfront.net`

Notes:
- Limiting to only `www.metro.ca` can break search/results because core JS is served from CloudFront; include the observed CloudFront host(s).
- These hosts can rotate. Log blocked hosts at runtime and surface a developer hint to promote necessary domains to the allowlist.
- Many analytics/ads calls are not required for browsing or add‑to‑cart; prefer blocking them to reduce noise and risk.

### 5. JavaScript Injection

**Status Banner:**
- Fixed position at top of page
- Shows: "🤖 Grocery Agent Active - Currently shopping for: {item}"
- Styled with gradient background, high z-index
- Injected on page load and after navigation
- Provides `window.setCurrentShoppingItem(itemName)` function for orchestrator

**Implementation Notes:**
- Use `context.add_init_script` to inject on every full document load (prevents flicker)
- Hook SPA navigation by wrapping `history.pushState/replaceState` and listening to `popstate`
- IIFE wrapper to prevent duplicate injection
- Check for `window.__groceryAgentInjected` flag
- Prepend banner to `document.body`

**What counts as navigation (Playwright):**
- A navigation is a top-level document change (e.g., `page.goto`, link causing a full load)
- SPA route changes via history API are not navigations; the init script + hooks keep the banner in sync

**Design Decision: Trust the Agent**
- No automatic cart change detection
- No confirmation dialogs
- Agent uses custom tool functions to report results directly

### 7. Custom Tool Functions & Task Framing

**Custom Tool Functions:**

Two functions registered with Gemini API using `FunctionDeclaration.from_callable()`:

1. **report_item_added(item_name, price_text, price_cents, url, quantity)**
   - Called when item successfully added to cart
   - Returns `ItemAddedResult` (TypedDict) with fields:
     - `item_name: str`
     - `price_text: str` (e.g., "$12.34")
     - `price_cents: int` (e.g., 1234)
     - `url: str`
     - `quantity: int` (default 1 if omitted)

2. **report_item_not_found(item_name, explanation)**
   - Called when item cannot be found after reasonable attempts
   - Returns `ItemNotFoundResult` (TypedDict) with: `item_name: str`, `explanation: str`

**Type Requirements:**
- Internals use Pydantic models for validation and math (e.g., Decimal for totals)
- Tool I/O uses TypedDicts only (never `dict[str, object]` or `Any`)
- Add these TypedDicts to the `FunctionResponseT` union type
- Add handler cases in `BrowserAgent.handle_action()` that return the TypedDict payloads

**Terminal Behavior (Implementation Detail):**
- The orchestrator treats the first call to `report_item_added(...)` or `report_item_not_found(...)` as terminal for that item
- Do not communicate this termination behavior in tool docstrings or prompts

**Task Prompt Template:**

Template structure:
- **Goal**: Add ONE specific item to metro.ca cart
- **Item**: `{item_name}`
- **Instructions**:
  1. Search metro.ca for the item
  2. Add item to cart
  3. Call `report_item_added()` with details (name, price, url, quantity)
  4. OR call `report_item_not_found()` with explanation if not found
- **Constraints**:
  - Stay on metro.ca domain only
  - No payment info, account settings, or checkout
  - Focus only on finding and adding the requested item

**Navigation and Search Guidance:**
- Prefer using `navigate` to directly open the search results page (SRP):
  - `https://www.metro.ca/en/online-grocery/search?filter={ENCODED_QUERY}`
- Alternatively, use the header search input present on all pages
- The built-in `search()` tool is no-arg; in grocery mode it may land on the Metro search area without a filter, but `navigate` to SRP is more reliable

### 8. State Tracking via Provider

**Shopping List Item States:**

| State | Meaning | Provider Method |
|-------|---------|-----------------|
| Uncompleted | Not yet added to cart | `status: needs_action` |
| Completed | Successfully added to cart | `mark_completed(item_id)` |
| Not Found | Product not found on metro.ca | `mark_not_found(item_id, explanation)` |
| Failed | Error during processing | `mark_failed(item_id, error)` |

**Provider Interactions:**

The orchestrator calls provider methods based on agent results:

- **Success**: `provider.mark_completed(item_id)` when agent returns `ItemAddedResult`
- **Not found**: `provider.mark_not_found(item_id, explanation)` when agent returns `ItemNotFoundResult`
- **Error**: `provider.mark_failed(item_id, error)` when exception occurs
- **Summary**: `provider.send_summary(results)` after all items processed

**Provider Responsibilities:**

Each provider implementation decides how to:
- Store item state updates
- Tag items with error markers (#404, #failed)
- Deliver summary notifications
- Fire events or trigger automations (provider-specific)

### 9. Success/Error Handling

**Success Flow:**
1. Agent searches metro.ca for item
2. Agent adds item to cart
3. Agent calls `report_item_added(item_name, price, url, quantity)`
4. Orchestrator: calls `provider.mark_completed(item_id)`, collects result, closes browser
5. Process next item or finish

**Not Found Flow:**
1. Agent searches metro.ca for item
2. Agent tries multiple search terms/variations
3. Agent cannot find suitable product
4. Agent calls `report_item_not_found(item_name, explanation)`
5. Orchestrator: calls `provider.mark_not_found(item_id, explanation)`, collects result, closes browser
6. Process next item or finish

**Error Scenarios:**

| Error | Detection | Action |
|-------|-----------|--------|
| Product not found | Agent calls `report_item_not_found()` | Call `mark_not_found()`, collect for report |
| Auth expired | Redirect to login detected | Log error, stop shopping, notify via provider |
| Agent timeout | Internal time budget exceeded (default 5 min) or max turns reached | Call `mark_failed()`, add to report, continue to next |
| Network error | Exception during browser operations | Call `mark_failed()`, retry once, then move to next item |
| Agent error | Exception in agent loop | Call `mark_failed()`, log error, continue to next item |

**Summary Report (After All Items):**
Generated after processing all items, includes:
- Successfully added items with prices and URLs
- Not found items with explanations
- Failed items with error messages
- Total estimated cost
- Link to metro.ca cart

Delivered via `provider.send_summary()`.

**Timeouts:**
- Internal time budget per item: default 5 minutes
- Max turns per item: default 40
- If either is exceeded, mark as failed and move to next item
- CLI uses a timedelta for time budget (e.g., `--time-budget 5m`, `--time-budget 300s`, `--time-budget 1h`)

### 10. Configuration Locations

**Directory Structure:**
```
~/.config/gemini-supply/
├── camoufox-profile/            # Persistent browser profile (cookies/tokens)
└── config.yaml                  # Optional: future configuration
```

**First Run Setup:**
- Create config directory: `mkdir -p ~/.config/gemini-supply`
- Export `GEMINI_SUPPLY_METRO_USERNAME` / `GEMINI_SUPPLY_METRO_PASSWORD`
- Run `uv run gemini-supply shop ...` to trigger automated login

**Gitignore:**
```
# Sensitive/local files
camoufox-profile/
config.yaml
```

## Implementation Plan

### Phase 1: Core Infrastructure

**1.1 Project Structure**
```
src/gemini_supply/
├── grocery/
│   ├── __init__.py
│   ├── shopping_list.py     # ShoppingListProvider interface + YAML implementation
│   └── config.py           # Configuration management
├── computers/
│   └── camoufox_browser.py  # CamoufoxMetroBrowser: Playwright subclass with auth + restrictions
├── grocery_main.py          # Orchestrator for grocery agent
├── main.py                  # Clypi-based CLI (subcommands: shop)
└── agent.py                 # (modifications to existing)
```

**1.2 Shopping List Provider**
- Define `ShoppingListProvider` protocol in `shopping_list.py`
- Implement `YAMLShoppingListProvider` as default
- Support YAML file read/write for items and state

**1.3 Configuration Management**
- Create `config.py` to handle loading from `~/.config/gemini-supply/`
- Validate configuration on startup

### Phase 2: Authenticated Metro Browser

**2.1 CamoufoxMetroBrowser Class**
- Extend `PlaywrightComputer`
- Launch Firefox via Camoufox with persistent profile directory
- Implement route blocking (allowlist + blocklist)
- Inject status banner on document load; keep in sync on SPA route changes
- Log blocked hosts for allowlist tuning

**2.2 JavaScript Injection**
- Status banner
- Helper functions for agent interaction
- Use `context.add_init_script`; hook history API to catch SPA route changes

**2.3 Domain Restrictions**
- URL pattern blocking
- Domain whitelist enforcement
- Checkout interception

### Phase 3: Orchestrator & Agent Integration

**3.1 Grocery Orchestrator (`grocery_main.py`)**
- CLI argument parsing (`shop`, `authenticate`)
- Shopping loop: process all uncompleted items
- Per-item agent instantiation
- Custom tool function registration
- Task prompt construction with tool instructions
- Result collection and aggregation
- Summary report generation
 - Treat first `report_item_added()` or `report_item_not_found()` call as terminal for the item

**3.2 Agent Modifications**
- Add custom tool functions: `report_item_added()` and `report_item_not_found()`
- Register tools using `FunctionDeclaration.from_callable()`
- Handle tool function results in agent loop
- Signal completion when tool functions are called

**3.3 Authentication Flow**
- Separate utility opens headful browser for manual login
- Uses a persistent profile directory; no JSON storage state is saved/loaded
- Validation of successful auth

**3.4 Summary Generation**
- Format results as markdown
- Calculate total estimated cost (use Decimal internally; present `$`-formatted values)
- Pass summary to provider via `send_summary()`

### Phase 4: Testing & Refinement

**4.1 Manual Testing**
- Test full flow end-to-end with YAML provider
- Validate cart persistence
- Test error scenarios

**4.2 Refinements**
- Adjust task prompts based on agent behavior
- Handle edge cases discovered during testing

**4.3 Documentation**
- User setup guide
- Provider integration guide
- Troubleshooting guide
