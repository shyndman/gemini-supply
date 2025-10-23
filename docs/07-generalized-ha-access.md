# Generalizing Home Assistant Access: Shopping Lists as To-Do Lists

## Overview

This document describes the refactoring of `HomeAssistantShoppingListProvider` to use Home Assistant's modern to-do list APIs instead of the legacy shopping list endpoints. This change was motivated by the discovery that shopping lists are fundamentally to-do lists under the covers, exposing more flexible and standardized APIs.

## Discovery: Shopping Lists Are To-Do Lists

While experimenting with Home Assistant's REST API, we discovered that:

1. **Shopping lists are just specialized to-do lists** - The built-in shopping list integration creates a `todo.shopping_list` entity
2. **Google Keep lists are also to-do lists** - The Google Keep integration exposes lists as `todo.google_keep_my_shopping_list` entities
3. **Both can be accessed via the same API** - The `todo.get_items` and `todo.update_item` services work uniformly across all to-do list providers

This revelation means we can:
- Use a single, well-documented API surface
- Support multiple list providers without code changes
- Leverage Home Assistant's standardized to-do list functionality
- Access any to-do list entity, not just shopping lists

## API Comparison

### Old Shopping List API

**Get Items:**
```bash
GET /api/shopping_list
```
Returns:
```json
[
  {
    "id": "123",
    "name": "Milk",
    "complete": false
  }
]
```

**Update Item:**
```bash
POST /api/shopping_list/item/{item_id}
```
Body:
```json
{
  "name": "Milk #not_found",
  "complete": false
}
```

### New To-Do List API

**Get Items:**
```bash
POST /api/services/todo/get_items?return_response
```
Body:
```json
{
  "entity_id": "todo.shopping_list"
}
```
Returns:
```json
{
  "service_response": {
    "todo.shopping_list": {
      "items": [
        {
          "uid": "cbx.abc123",
          "summary": "Milk",
          "status": "needs_action"
        }
      ]
    }
  }
}
```

**Update Item:**
```bash
POST /api/services/todo/update_item
```
Body:
```json
{
  "entity_id": "todo.shopping_list",
  "item": "cbx.abc123",
  "rename": "Milk #not_found",
  "status": "completed"
}
```

## Field Name Mapping

| Old API | New API | Notes |
|---------|---------|-------|
| `id` | `uid` | Item identifier |
| `name` | `summary` | Item text content |
| `complete` (bool) | `status` (string) | `false` → `"needs_action"`, `true` → `"completed"` |

## Implementation Changes

### 1. Data Model Updates

**Before:**
```python
class HomeAssistantItemModel(BaseModel):
  id: str = ""
  name: str = ""
  complete: bool = False
```

**After:**
```python
class HomeAssistantItemModel(BaseModel):
  uid: str = ""
  summary: str = ""
  status: Literal["needs_action", "completed"] = "needs_action"
```

### 2. Provider Configuration

**New parameter added:**
```python
@dataclass
class HomeAssistantShoppingListProvider:
  ha_url: str
  token: str
  no_retry: bool = False
  entity_id: str = "todo.shopping_list"  # NEW: configurable entity
```

This allows the provider to work with:
- `todo.shopping_list` (built-in Home Assistant shopping list)
- `todo.google_keep_my_shopping_list` (Google Keep integration)
- Any other to-do list entity

### 3. Get Items Implementation

**Before:**
```python
def _get_items(self) -> list[HomeAssistantItemModel]:
  url = f"{self.ha_url}/api/shopping_list"
  req = urllib.request.Request(url, headers=self._headers(), method="GET")
  with urllib.request.urlopen(req, timeout=5) as resp:
    raw_data = json.loads(resp.read().decode("utf-8"))
    # raw_data is a flat list
    return [HomeAssistantItemModel.model_validate(entry) for entry in raw_data]
```

**After:**
```python
def _get_items(self) -> list[HomeAssistantItemModel]:
  url = f"{self.ha_url}/api/services/todo/get_items?return_response"
  payload = {"entity_id": self.entity_id}
  req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers=self._headers(),
    method="POST"
  )
  with urllib.request.urlopen(req, timeout=5) as resp:
    raw_data = json.loads(resp.read().decode("utf-8"))
    # raw_data is nested: service_response.{entity_id}.items
    items_data = raw_data.get("service_response", {}).get(self.entity_id, {}).get("items", [])
    return [HomeAssistantItemModel.model_validate(entry) for entry in items_data]
```

**Key changes:**
- Endpoint changes from GET to POST with `?return_response` query param
- Must provide `entity_id` in request body
- Response is nested under `service_response.{entity_id}.items`

### 4. Update Item Implementation

**Before:**
```python
def _update_item(self, item_id: str, fields: dict[str, object]) -> None:
  url = f"{self.ha_url}/api/shopping_list/item/{item_id}"
  data = json.dumps(fields).encode("utf-8")
  req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
  # fields: {"name": "...", "complete": bool}
```

**After:**
```python
def _update_item(self, item_uid: str, fields: dict[str, object]) -> None:
  url = f"{self.ha_url}/api/services/todo/update_item"

  # Map old fields to new service parameters
  payload: dict[str, object] = {"entity_id": self.entity_id, "item": item_uid}

  if "name" in fields:
    payload["rename"] = fields["name"]
  if "complete" in fields:
    payload["status"] = "completed" if fields["complete"] else "needs_action"

  data = json.dumps(payload).encode("utf-8")
  req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
```

**Key changes:**
- Endpoint is now a service call, not a REST resource
- Item ID moves from URL path to request body as `item` parameter
- `name` field becomes `rename` parameter
- `complete` bool becomes `status` string enum
- Must always include `entity_id` in payload

### 5. Internal Field Access Updates

Throughout the provider, all references need updating:

**Field Access:**
```python
# Before
item.id
item.name
item.complete

# After
item.uid
item.summary
item.status == "needs_action"  # was: not item.complete
item.status == "completed"     # was: item.complete
```

**Common patterns:**
```python
# Filtering incomplete items
# Before: if not it.complete
# After:  if it.status == "needs_action"

# Getting item identifier
# Before: if not it.id
# After:  if not it.uid

# Getting item text
# Before: raw_name = it.name.strip()
# After:  raw_name = it.summary.strip()
```

## What Stays the Same

Crucially, the **entire business logic layer** remains unchanged:

- ✅ Tag management (`#not_found`, `#out_of_stock`, `#failed`, `#dupe`)
- ✅ Duplicate detection (case-insensitive normalization)
- ✅ Quantity parsing (`x3`, `3x`, `(3)`, etc.)
- ✅ Summary formatting and markdown generation
- ✅ Public API methods (`get_uncompleted_items`, `mark_completed`, etc.)
- ✅ Persistent notification creation
- ✅ All filtering and transformation logic

The refactor is purely at the **data access layer** - we're just swapping out how we fetch and update items, not what we do with them.

## Testing Strategy

### Pre-Refactor: Test Suite Creation

Before making any changes, we created a comprehensive test suite (`tests/test_home_assistant_shopping_list.py`) with **40 tests** covering:

1. **Item retrieval and filtering** - ensures `get_uncompleted_items()` handles all edge cases
2. **State mutations** - verifies `mark_completed`, `mark_not_found`, etc. work correctly
3. **Tag management** - validates tag stripping, detection, and application
4. **Quantity parsing** - confirms all quantity formats are handled
5. **Summary formatting** - checks markdown generation and output
6. **Initialization** - verifies provider setup

**Why test first?**
- Locks in current behavior before refactoring
- Provides confidence that the refactor preserves functionality
- Acts as regression detector if something breaks
- Documents expected behavior

### Test Approach

All tests use **mocking** to isolate the provider from actual Home Assistant:

```python
def test_returns_only_incomplete_items(provider):
  with patch.object(provider, "_get_items") as mock_get:
    mock_get.return_value = [
      HomeAssistantItemModel(id="1", name="Milk", complete=False),
      HomeAssistantItemModel(id="2", name="Eggs", complete=True),
    ]

    items = provider.get_uncompleted_items()

    assert len(items) == 1
    assert items[0].name == "Milk"
```

After refactoring, we'll update the mock data to use new field names, but the assertions stay the same.

### Refactor Verification

1. Run tests before refactoring → **40 passing**
2. Update `HomeAssistantItemModel` fields
3. Update mock data in tests to use new field names
4. Run tests → **should still be 40 passing**
5. Update `_get_items()` implementation
6. Run tests → **should still be 40 passing**
7. Update `_update_item()` implementation
8. Run tests → **should still be 40 passing**

If tests fail at any point, we know exactly what broke.

## Configuration Changes

### Home Assistant Config

Update `~/.config/gemini-supply/config.yaml`:

```yaml
shopping_list:
  provider: home_assistant

home_assistant:
  url: http://your-ha-instance:8123
  token: your-long-lived-access-token
  entity_id: todo.shopping_list  # NEW: optional, defaults to "todo.shopping_list"
```

**For Google Keep:**
```yaml
home_assistant:
  url: http://your-ha-instance:8123
  token: your-long-lived-access-token
  entity_id: todo.google_keep_my_shopping_list  # Use Google Keep list
```

### Config Loading Updates

```python
@dataclass
class HomeAssistantShoppingListConfig:
  url: str
  token: str
  entity_id: str = "todo.shopping_list"  # NEW: with default
```

## Benefits of This Change

### 1. **Standardization**
- Uses official Home Assistant to-do list APIs
- Follows documented, supported patterns
- Less likely to break with HA updates

### 2. **Flexibility**
- Works with built-in shopping lists
- Works with Google Keep lists
- Works with any future to-do list integration
- Could support multiple lists simultaneously

### 3. **Feature Parity**
- Access to richer to-do item metadata (if needed in future)
- Better error handling from service calls
- Consistent with Home Assistant's architectural direction

### 4. **Simplified Testing**
- Scripts like `home_assistant_call.py` now work with both modes
- Can test against different list providers easily
- Easier to debug issues with standardized API

## Migration Path

### Phase 1: Test Suite (✅ Complete)
- [x] Create comprehensive test suite
- [x] Verify all 40 tests pass
- [x] Document expected behavior

### Phase 2: Data Model
- [ ] Update `HomeAssistantItemModel` fields
- [ ] Update field validators for new types
- [ ] Update test mocks to use new field names
- [ ] Verify tests still pass (40/40)

### Phase 3: Configuration
- [ ] Add `entity_id` parameter to provider
- [ ] Add `entity_id` field to config dataclass
- [ ] Update config loading logic
- [ ] Verify tests still pass (40/40)

### Phase 4: Get Items
- [ ] Rewrite `_get_items()` to use `todo.get_items` service
- [ ] Handle nested response structure
- [ ] Update error handling
- [ ] Verify tests still pass (40/40)

### Phase 5: Update Items
- [ ] Rewrite `_update_item()` to use `todo.update_item` service
- [ ] Map old parameters to new service format
- [ ] Handle status enum conversion
- [ ] Verify tests still pass (40/40)

### Phase 6: Field References
- [ ] Update all `item.id` → `item.uid`
- [ ] Update all `item.name` → `item.summary`
- [ ] Update all `item.complete` → `item.status` comparisons
- [ ] Verify tests still pass (40/40)

### Phase 7: Integration Testing
- [ ] Test against real Home Assistant instance
- [ ] Verify shopping list operations work end-to-end
- [ ] Test with Google Keep list (if available)
- [ ] Document any edge cases discovered

### Phase 8: Cleanup
- [ ] Remove any compatibility shims
- [ ] Update documentation
- [ ] Update CLAUDE.md if needed

## Edge Cases and Considerations

### 1. Empty/Missing Fields
- Old API: `id`, `name` could be empty strings
- New API: `uid`, `summary` could be empty strings
- **Action:** Same validation logic applies

### 2. Status Enum Handling
```python
# Robust status checking
def is_incomplete(item: HomeAssistantItemModel) -> bool:
  return item.status != "completed"  # catches "needs_action" and future values

# Explicit mapping when needed
STATUS_MAP = {
  "needs_action": False,  # not complete
  "completed": True,      # complete
}
```

### 3. Error Handling
```python
# Service calls may return different error structures
try:
  response = self._get_items()
except HTTPError as e:
  if e.code in (401, 403):
    raise RuntimeError(f"Home Assistant auth failed: HTTP {e.code}") from e
  # Handle service-specific errors
  error_body = json.loads(e.read().decode("utf-8"))
  if "error" in error_body:
    # Log service error details
    pass
```

### 4. Response Structure Changes
```python
# Old: direct list access
items = response_data  # List[dict]

# New: nested access with error handling
service_response = response_data.get("service_response", {})
entity_data = service_response.get(self.entity_id, {})
items = entity_data.get("items", [])

if not isinstance(items, list):
  # Handle malformed response
  return []
```

### 5. Backwards Compatibility
**Per CLAUDE.md:** We do NOT write backwards-compatible software. When we migrate, we migrate completely:
- Remove old API code entirely
- No compatibility layers
- No protocol versioning
- Clean, modern implementation only

## Future Opportunities

### 1. Multiple List Support
With `entity_id` as a parameter, we could support shopping from multiple lists:
```python
primary_list = HomeAssistantShoppingListProvider(
  ha_url=url,
  token=token,
  entity_id="todo.shopping_list"
)

google_keep = HomeAssistantShoppingListProvider(
  ha_url=url,
  token=token,
  entity_id="todo.google_keep_my_shopping_list"
)

# Shop from both
items = primary_list.get_uncompleted_items() + google_keep.get_uncompleted_items()
```

### 2. Rich To-Do Item Support
The to-do API supports additional fields we could leverage:
- `description`: Longer item descriptions
- `due_date` / `due_datetime`: When items need to be purchased
- Custom attributes specific to list provider

### 3. Provider Abstraction
We could introduce a generic `ToDoListProvider` protocol:
```python
class ToDoListProvider(Protocol):
  def get_uncompleted_items(self) -> list[ShoppingListItem]: ...
  def mark_completed(self, item_id: str, result: ItemAddedResult) -> None: ...
  # ...
```

Then implement:
- `HomeAssistantToDoProvider` (what we're building)
- `GoogleTasksProvider` (direct Google Tasks API)
- `TodoistProvider` (Todoist API)
- `LocalFileProvider` (YAML/JSON file)

### 4. Real-time Updates
Home Assistant's WebSocket API could notify us of list changes:
```python
# Future: subscribe to todo.shopping_list state changes
async def watch_list_updates():
  async with ha_websocket(url, token) as ws:
    await ws.subscribe_events("todo_list_updated", entity_id="todo.shopping_list")
    async for event in ws:
      # Refresh our view of the list
      items = provider.get_uncompleted_items()
```

## Testing the New Implementation

### Manual Testing Script

```bash
# Get all items from shopping list
./scripts/home_assistant_call.py service "todo.get_items?return_response" \
  --entity-id "todo.shopping_list" | jq '.service_response'

# Add an item
./scripts/home_assistant_call.py service "todo.add_item" \
  --entity-id "todo.shopping_list" \
  --data '{"item": "Test Item"}'

# Update an item
./scripts/home_assistant_call.py service "todo.update_item" \
  --entity-id "todo.shopping_list" \
  --data '{"item": "cbx.abc123", "status": "completed"}'

# Remove an item
./scripts/home_assistant_call.py service "todo.remove_item" \
  --entity-id "todo.shopping_list" \
  --data '{"item": "cbx.abc123"}'
```

### Integration Test Checklist

- [ ] Can retrieve all items from list
- [ ] Can filter incomplete items correctly
- [ ] Can mark items as completed
- [ ] Can mark items as not found (with tag)
- [ ] Can mark items as out of stock (with tag)
- [ ] Can mark items as failed (with tag)
- [ ] Tags persist across get/update cycles
- [ ] Duplicate detection works
- [ ] Quantity parsing works
- [ ] Summary formatting works
- [ ] Google Keep list works (if available)

## Conclusion

This refactoring moves `HomeAssistantShoppingListProvider` from a legacy, shopping-list-specific API to modern, standardized to-do list services. The change:

1. **Preserves all business logic** - only the data access layer changes
2. **Increases flexibility** - works with any to-do list provider
3. **Improves maintainability** - uses documented, supported APIs
4. **Enables future features** - multiple lists, richer metadata, real-time updates

The comprehensive test suite ensures we can refactor confidently, and the phased approach allows us to verify correctness at each step.

## References

- [Home Assistant REST API Documentation](https://developers.home-assistant.io/docs/api/rest)
- [To-Do List Integration Documentation](https://www.home-assistant.io/integrations/todo)
- [Home Assistant Services](https://www.home-assistant.io/docs/scripts/service-calls/)
- Test suite: `tests/test_home_assistant_shopping_list.py`
- Implementation: `src/gemini_supply/grocery/home_assistant_shopping_list.py`
- Helper script: `scripts/home_assistant_call.py`