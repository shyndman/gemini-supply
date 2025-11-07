# Home Assistant Shopping List Integration

## Overview

This document describes how to integrate the grocery agent with Home Assistant's Shopping list functionality. The agent implements the abstract `ShoppingListProvider` interface to read items from and update state in Home Assistant over HA's REST API.

## Prerequisites

- Home Assistant instance with API access
- Shopping list integration enabled in Home Assistant
- Long‑lived access token for API authentication

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Home Assistant                         │
│                                                              │
│  Shopping List (global):                                     │
│    ☐ milk                                                    │
│    ☐ bread                                                   │
│    ☑ eggs (completed = in cart)                              │
│    ☐ butter #not_found                                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                   ▲
                   │ (REST: read + mutate items)
                   │           and create summary notification
┌─────────────────────────────────────────────────────────────┐
│           HomeAssistantShoppingListProvider                  │
│                                                              │
│  Implements: ShoppingListProvider                            │
│                                                              │
│  Methods:                                                    │
│    - get_uncompleted_items() → list[ShoppingListItem]        │
│    - mark_completed(id)                                      │
│    - mark_not_found(id)                                      │
│    - mark_failed(id)                                         │
│    - send_summary(summary)                                   │
│                                                              │
│  Behavior:                                                   │
│    - Serial processing, minimal logging                      │
│    - Tag items (#not_found, #out_of_stock, #failed, #dupe)   │
│    - Create persistent notification per run                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### Configuration

File: `~/.config/generative-supply/config.yaml`

```yaml
shopping_list:
  provider: "home_assistant"

home_assistant:
  url: "http://home.don"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"
```

Security: Keep this file private (e.g., user‑only permissions) and out of version control.

### HomeAssistantShoppingListProvider Class

**Constructor:**
- `__init__(ha_url, token)`
- Store HA URL and auth token
- Setup authorization headers

**Core Methods:**

**`get_uncompleted_items()`**
- GET `/api/shopping_list`
- Filter for `complete == false`
- By default, include items even if tagged; with `--no-retry`, exclude any item containing `#not_found`, `#out_of_stock`, `#failed`, or `#dupe`
- Return list of `ShoppingListItem` objects (id, name, complete)

**`mark_completed(id)`**
- POST `/api/shopping_list/item/{id}` with `{ complete: true, name: "<base name>" }`
- Remove any error tags from the name when marking complete

**`mark_not_found(id)`**
- Append `#not_found` to the item name (only if absent), ensure `complete` stays `false`
- POST `/api/shopping_list/item/{id}` with `{ name: "<base name> #not_found", complete: false }`

**`mark_failed(id)`**
- Append `#failed` to the item name (only if absent and without other error tags), ensure `complete` stays `false`
- POST `/api/shopping_list/item/{id}` with `{ name: "<base name> #failed", complete: false }`

**`mark_out_of_stock(id)`**
- Append `#out_of_stock` to the item name (only if absent), ensure `complete` stays `false`
- POST `/api/shopping_list/item/{id}` with `{ name: "<base name> #out_of_stock", complete: false }`

**`send_summary(summary)`**
- Format summary as Markdown with sections: Added to Cart, Out of Stock, Not Found, Duplicates, Failed (omit empty sections)
- First line includes run time, for example: `Run: Oct 19, 2025 2:32pm`
- POST `/api/services/persistent_notification/create` with `{ title: "Grocery Shopping Complete", message: "<markdown>" }`
- Also print the same summary to stdout if any processing occurred

**Helper Methods:**
- `_update_item(id, fields)`: POST `/api/shopping_list/item/{id}` with partial `{ name?, complete? }`
- `_strip_tags(name)`: Remove any of `#not_found #out_of_stock #failed #dupe` from the end
- `_apply_tags(name, tags)`: Append canonical ordered tags without duplicates
- `_parse_quantity(name)`: Detect quantity from patterns `xN`, `Nx`, `(N)`, leading/trailing number; first match wins
- `_format_summary(summary)`: Convert ShoppingSummary to Markdown (tags stripped, quantities rendered as ×N)
- `_notify_persistent(markdown)`: POST to `/api/services/persistent_notification/create`

## State Tracking

### Shopping List Item States

| State | Meaning | How Represented |
|-------|---------|-----------------|
| Uncompleted | Not yet added to cart | `complete: false` |
| Completed | Successfully added to cart | `complete: true` (tags removed) |
| Not Found | No retailer match | `complete: false` + `#not_found` tag in name |
| Out of Stock | Match found but unavailable | `complete: false` + `#out_of_stock` tag in name |
| Failed | Network/parsing/5xx/unexpected | `complete: false` + `#failed` (exclusive) |
| Duplicate | Additional item with same normalized name | `complete: false` + `#dupe` (no retailer processing) |

### Notifications

Persistent notifications are created for:
- **Summary Report**: After all items processed (always)
- **Retailer Authentication/Session Failures**
- **Critical Failures**: Unexpected system errors (non‑401/403)

401/403 from Home Assistant are treated as fatal (no notification possible).
## Home Assistant Configuration

No HA automations are required. The provider reads and updates the Shopping list via REST and creates a persistent notification for the run summary.

## Setup Instructions

### 1. Create Long-Lived Access Token

1. Open Home Assistant
2. Click on your profile (bottom left)
3. Scroll to "Long-Lived Access Tokens"
4. Click "Create Token"
5. Name it "Grocery Agent"
6. Copy the token

### 2. Configure generative-supply

Create `~/.config/generative-supply/config.yaml`:

```yaml
shopping_list:
  provider: "home_assistant"

home_assistant:
  url: "http://home.don"
  token: "YOUR_TOKEN_HERE"
```

### 3. Add Items to Shopping List

In Home Assistant:
1. Open Shopping List integration
2. Add items: "milk", "bread", "eggs", etc.

### 4. Run Agent

```bash
uv run grocery-agent shop
```

### 5. Review Results

- Check Shopping List for completed items
- Review persistent notification for summary
- Check cart at metro.ca

## Troubleshooting

### Items Not Updating

**Problem**: Items remain uncompleted after agent runs

**Solutions**:
- Verify HA token is valid
- Check HA API is accessible from agent machine
- Check agent logs for API errors

### Authentication Issues

**Problem**: Agent can't connect to HA

**Solutions**:
- Regenerate long-lived access token
- Verify HA URL is correct (include http:// or https://)
- Check firewall allows connection from agent machine
- Test token with curl:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" \
       http://home.don/api/
  ```

## Behavior Details

### API Endpoints
- Read items: `GET /api/shopping_list` → `[ { id, name, complete } ]`
- Update item: `POST /api/shopping_list/item/{id}` with JSON body `{ name?: string, complete?: bool }`
- Create summary notification: `POST /api/services/persistent_notification/create` with `{ title, message }`

Timeout is 5 seconds for all HA requests. No automatic retries.

### Tagging Rules
- Tags are appended at the end of the name in this canonical order: `#not_found #out_of_stock #failed #dupe` (subset as needed)
- Exclusivity: `#failed` is exclusive; `#not_found` and `#out_of_stock` are mutually exclusive
- `#dupe` stands alone (no retailer processing)
- Tags are added only if missing; duplicates are not added

### Duplicates
- The first occurrence of a name is processed; subsequent exact‑name matches are tagged `#dupe` and skipped
- Completed items are ignored entirely

### Retry Semantics
- Default: reprocess items even if tagged
- `--no-retry`: skip any item that contains any of the tags (`#not_found`, `#out_of_stock`, `#failed`, `#dupe`)

### Quantities and Names
- Quantities are parsed from one of: trailing/leading unitless number, `xN`, `Nx`, `(N)`; the first match wins
- Summary displays base names without tags; quantities are rendered as `×N`

### Summary Format
- Title: `Grocery Shopping Complete`
- First line: `Run: <pretty local time>`, e.g., `Run: Oct 19, 2025 2:32pm`
- Sections (omit if empty): Added to Cart, Out of Stock, Not Found, Duplicates, Failed
- Items: `- <name>[ ×<qty>]`, original HA order within each section
- The same summary is always printed to the terminal if any processing occurred; a short message is printed if nothing to do

### Error Handling and Logging
- 401/403 from HA: fatal error (no HA notification)
- Other HA errors (>=400): logged minimally; reflected in summary or a separate persistent notification when appropriate
- Minimal logs overall; reasons (e.g., timeout 5s, parsing error) appear in logs, not in the summary
