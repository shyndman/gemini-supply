# Home Assistant Shopping List Integration

## Overview

This document describes how to integrate the grocery agent with Home Assistant's shopping list functionality. The agent implements the abstract `ShoppingListProvider` interface to read items from and update state in Home Assistant.

## Prerequisites

- Home Assistant instance with API access
- Shopping list integration enabled in Home Assistant
- Long-lived access token for API authentication

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Home Assistant                            │
│                                                              │
│  Shopping List:                                              │
│    ☐ milk                                                    │
│    ☐ bread                                                   │
│    ☑ eggs (completed = in cart)                             │
│    ☐ butter #404 (not found)                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                   ▲
                   │ (queries list, updates immediately)
                   │
┌─────────────────────────────────────────────────────────────┐
│           HomeAssistantShoppingListProvider                  │
│                                                              │
│  Implements: ShoppingListProvider                           │
│                                                              │
│  Methods:                                                   │
│    - get_uncompleted_items() → list[ShoppingListItem]      │
│    - mark_completed(item_id)                                │
│    - mark_not_found(item_id, explanation)                   │
│    - mark_failed(item_id, error)                            │
│    - send_summary(summary)                                  │
│                                                              │
│  HA-Specific Features:                                      │
│    - Fire events for each state change                      │
│    - Create persistent notifications                        │
│    - Tag items with #404 or #failed                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### Configuration

**File Location:** `~/.config/gemini-supply/config.yaml`

```yaml
shopping_list:
  provider: "home_assistant"

home_assistant:
  url: "http://homeassistant.local:8123"
  token: "YOUR_LONG_LIVED_ACCESS_TOKEN"
  shopping_list_entity: "todo.shopping_list"
```

### HAShoppingListProvider Class

**Constructor:**
- `__init__(ha_url, token, entity_id="todo.shopping_list")`
- Store HA URL, auth token, entity ID
- Setup authorization headers

**Core Methods:**

**`get_uncompleted_items()`**
- GET `/api/todo/{entity_id}/items`
- Filter for `status == "needs_action"` and no error tags
- Return list of `ShoppingListItem` objects

**`mark_completed(item_id)`**
- POST `/api/services/todo/update_item` with `status: "completed"`
- Fire event: `grocery_agent.item_added`

**`mark_not_found(item_id, explanation)`**
- GET item, append " #404" to summary
- POST updated summary
- Fire event: `grocery_agent.item_not_found` with explanation

**`mark_failed(item_id, error)`**
- GET item, append " #failed" to summary
- POST updated summary
- Fire event: `grocery_agent.error` with error details

**`send_summary(summary)`**
- Format summary as markdown with sections: Added to Cart, Not Found, Failed
- POST `/api/services/persistent_notification/create`
- Title: "Grocery Shopping Complete"

**Helper Methods:**
- `_get_item(item_id)`: Fetch single item by UID
- `_fire_event(event_type, data)`: POST to `/api/events/{event_type}`
- `_has_error_tag(summary)`: Check for #404 or #failed in summary
- `_format_summary(summary)`: Convert ShoppingSummary to markdown

## State Tracking

### Shopping List Item States

| State | Meaning | How Represented |
|-------|---------|-----------------|
| Uncompleted | Not yet added to cart | `status: needs_action` |
| Completed | Successfully added to cart | `status: completed` |
| Not Found | Product not found on metro.ca | `needs_action` + `#404` tag in name |
| Failed | Error during processing | `needs_action` + `#failed` tag in name |

### Events Fired

| Event | When | Data |
|-------|------|------|
| `grocery_agent.item_added` | Item successfully added to cart | `{item_id, timestamp}` |
| `grocery_agent.item_not_found` | Product not found | `{item_id, explanation, timestamp}` |
| `grocery_agent.auth_expired` | Session expired | `{timestamp}` |
| `grocery_agent.error` | Unexpected error | `{item_id, error, timestamp}` |

### Notifications

Persistent notifications are created for:
- **Summary Report**: After all items processed (always)
- **Authentication Expired**: When session expires (actionable error)
- **Critical Failures**: Unexpected system errors (rare)

## Home Assistant Configuration

### Shell Command Setup

Add to `configuration.yaml`:

```yaml
shell_command:
  grocery_shop: "cd /path/to/gemini-supply && uv run grocery-agent shop"
```

### Script for UI Triggering

```yaml
script:
  do_grocery_shopping:
    alias: "Do Grocery Shopping"
    sequence:
      - service: shell_command.grocery_shop
```

### Automation Examples

**Option 1: Manual Button Trigger**

```yaml
automation:
  - alias: "Grocery Shopping Button"
    trigger:
      - platform: state
        entity_id: input_boolean.start_grocery_shopping
        to: "on"
    action:
      - service: script.do_grocery_shopping
      - service: input_boolean.turn_off
        target:
          entity_id: input_boolean.start_grocery_shopping
```

**Option 2: Voice Assistant Integration**

Set up Google Assistant or Alexa to trigger the `script.do_grocery_shopping` script.

### Event-Based Automations (Optional)

**Notification on Item Added:**

```yaml
automation:
  - alias: "Notify Item Added to Cart"
    trigger:
      - platform: event
        event_type: grocery_agent.item_added
    action:
      - service: notify.mobile_app
        data:
          message: "Added {{ trigger.event.data.item_id }} to cart"
```

**Alert on Auth Expired:**

```yaml
automation:
  - alias: "Alert Auth Expired"
    trigger:
      - platform: event
        event_type: grocery_agent.auth_expired
    action:
      - service: notify.mobile_app
        data:
          message: "Grocery agent authentication expired. Run: uv run grocery-agent authenticate"
          title: "Action Required"
```

## Setup Instructions

### 1. Create Long-Lived Access Token

1. Open Home Assistant
2. Click on your profile (bottom left)
3. Scroll to "Long-Lived Access Tokens"
4. Click "Create Token"
5. Name it "Grocery Agent"
6. Copy the token

### 2. Configure gemini-supply

Create `~/.config/gemini-supply/config.yaml`:

```yaml
shopping_list:
  provider: "home_assistant"

home_assistant:
  url: "http://homeassistant.local:8123"
  token: "YOUR_TOKEN_HERE"
  shopping_list_entity: "todo.shopping_list"
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
- Verify `shopping_list_entity` matches your entity ID
- Check agent logs for API errors

### Events Not Firing

**Problem**: Automations not triggering on events

**Solutions**:
- Verify events are enabled in HA
- Check Developer Tools → Events to see if events are firing
- Ensure event names match exactly

### Authentication Issues

**Problem**: Agent can't connect to HA

**Solutions**:
- Regenerate long-lived access token
- Verify HA URL is correct (include http:// or https://)
- Check firewall allows connection from agent machine
- Test token with curl:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" \
       http://homeassistant.local:8123/api/
  ```

## Advanced Configuration

### Custom Entity ID

If your shopping list entity has a different name:

```yaml
home_assistant:
  shopping_list_entity: "todo.my_custom_list"
```

### Multiple Shopping Lists

Run separate agent instances with different configs:

```bash
# Groceries
uv run grocery-agent shop --config ~/.config/gemini-supply/groceries.yaml

# Household items
uv run grocery-agent shop --config ~/.config/gemini-supply/household.yaml
```

### Telegram Notifications

To also send summary via Telegram, add to `config.yaml`:

```yaml
notifications:
  telegram:
    enabled: true
    bot_token: "YOUR_BOT_TOKEN"
    chat_id: "YOUR_CHAT_ID"
```

The provider will send to both HA and Telegram when configured.
