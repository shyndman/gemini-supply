# Activity Logging System - Design & Migration Plan

## Overview

Centralize all operational/activity logging into `ActivityLog` with semantic method names, replacing scattered `termcolor.cprint()` calls. Move fully to Rich for all terminal output.

## Current State

- **ActivityLog** (`src/gemini_supply/term.py`): Currently handles only structured output
  - `print_reasoning()` - Rich tables with agent reasoning
  - `show_screenshot()` - Terminal image display
  - Uses Rich Console for output

- **termcolor.cprint()**: 62 scattered calls across 5 files
  - Direct colored terminal output
  - Inconsistent with Rich-based ActivityLog

### Usage Breakdown by Category

| Prefix | Occurrences | Files | Purpose |
|--------|-------------|-------|---------|
| `[auth]` | 17 | auth/flow.py | Authentication flow |
| `[stage]` | 4 | orchestrator.py | Orchestration stages |
| `[denature]` | 5 | orchestrator.py | Page modification |
| `[agent-X]` | 11 | orchestrator.py, agent.py | Per-agent operations (dynamic) |
| `[normalizer]` | 2 | preferences/normalizer.py | Item normalization |
| `[unrestricted]` | 6 | computers/browser_host.py | Restriction management |
| *(none)* | ~17 | various | General orchestrator messages |

### Color Semantics

| Color | Current Meaning | Usage Count |
|-------|-----------------|-------------|
| cyan | Operations in progress | ~20 |
| green | Success, completion | ~15 |
| yellow | Warnings, skips, unusual states | ~12 |
| magenta | Important data/info display | ~5 |
| red | Errors, failures | ~3 |
| blue | Starting processes/agents | ~2 |
| white | Debug/trace level | ~4 |
| dark_grey | Model thinking output | ~1 |
| light_grey | Low-level debug | ~1 |

## Proposed Design

### Context-Based Access

Use Python's `contextvars` to provide global access to `ActivityLog` without parameter passing noise:

```python
from gemini_supply.term import activity_log, set_activity_log

# Setup once at orchestrator level
logger = ActivityLog()
set_activity_log(logger)

# Use anywhere in the call tree
activity_log().auth.operation("Opening login drawer")
activity_log().agent("agent-1").success("Item added")
```

**Benefits:**
- No parameter passing through every function
- Properly scoped to async context (works with concurrent agents)
- Easy to test (can override in test contexts)
- Explicit initialization at orchestrator level

### Hierarchical API

```python
# Static categories (properties)
activity_log().auth.operation("Opening login drawer")          # [auth] ...
activity_log().stage.success("Promoted stage to shopping")     # [stage] ...
activity_log().normalizer.thinking("Model processing...")       # [normalizer] ...
activity_log().denature.trace("On search results page")        # [denature] ...
activity_log().unrestricted.warning("Already inactive")        # [unrestricted] ...

# Dynamic categories (method)
activity_log().agent("agent-1").operation("Shopping for 'Milk'")  # [agent-1] ...
activity_log().prefix("custom").failure("Something broke")        # [custom] ...

# No prefix (root methods)
activity_log().operation("General message")                     # No prefix
activity_log().success("Done")
```

### Semantic Methods

Map color semantics to intent-based method names:

```python
def operation(self, message: str) -> None:     # cyan - operations in progress
def success(self, message: str) -> None:       # green - completions, success states
def warning(self, message: str) -> None:       # yellow - warnings, skips, unusual states
def important(self, message: str) -> None:     # magenta - important data/info display
def failure(self, message: str) -> None:       # red - errors, failures
def starting(self, message: str) -> None:      # blue - launching processes/agents
def debug(self, message: str) -> None:         # white - debug/trace level
def thinking(self, message: str) -> None:      # dim - model thinking output
def trace(self, message: str) -> None:         # grey70 - low-level debug
```

## Implementation Strategy

### Phase 1: Extend ActivityLog

1. **Add contextvars setup** for global access:
   ```python
   from contextvars import ContextVar

   _activity_log: ContextVar[ActivityLog | None] = ContextVar('activity_log', default=None)

   def activity_log() -> ActivityLog:
       """Get the current ActivityLog instance from context."""
       log = _activity_log.get()
       if log is None:
           raise RuntimeError("ActivityLog not initialized. Call set_activity_log() first.")
       return log

   def set_activity_log(log: ActivityLog) -> None:
       """Set the ActivityLog instance for the current context."""
       _activity_log.set(log)
   ```

2. **Add CategoryLogger helper class**:
   ```python
   class CategoryLogger:
       """Prefixed logger delegate for a specific category."""

       def __init__(self, console: Console, prefix: str) -> None:
           self._console = console
           self._prefix = prefix

       def operation(self, message: str) -> None:
           self._console.print(f"[cyan]\\[{self._prefix}] {message}[/cyan]")

       def success(self, message: str) -> None:
           self._console.print(f"[green]\\[{self._prefix}] {message}[/green]")

       def warning(self, message: str) -> None:
           self._console.print(f"[yellow]\\[{self._prefix}] {message}[/yellow]")

       def important(self, message: str) -> None:
           self._console.print(f"[magenta]\\[{self._prefix}] {message}[/magenta]")

       def failure(self, message: str) -> None:
           self._console.print(f"[red]\\[{self._prefix}] {message}[/red]")

       def starting(self, message: str) -> None:
           self._console.print(f"[blue]\\[{self._prefix}] {message}[/blue]")

       def debug(self, message: str) -> None:
           self._console.print(f"[white]\\[{self._prefix}] {message}[/white]")

       def thinking(self, message: str) -> None:
           self._console.print(f"[dim]\\[{self._prefix}] {message}[/dim]")

       def trace(self, message: str) -> None:
           self._console.print(f"[grey70]\\[{self._prefix}] {message}[/grey70]")
   ```

3. **Extend ActivityLog with new infrastructure**:
   ```python
   class ActivityLog:
       def __init__(self) -> None:
           self._console = Console()

           # Static category loggers
           self.auth = CategoryLogger(self._console, "auth")
           self.stage = CategoryLogger(self._console, "stage")
           self.normalizer = CategoryLogger(self._console, "normalizer")
           self.denature = CategoryLogger(self._console, "denature")
           self.unrestricted = CategoryLogger(self._console, "unrestricted")

       def agent(self, label: str) -> CategoryLogger:
           """Create a logger for a specific agent."""
           return CategoryLogger(self._console, label)

       def prefix(self, name: str) -> CategoryLogger:
           """Create a logger with a custom prefix."""
           return CategoryLogger(self._console, name)

       # Root-level semantic methods (no prefix)
       def operation(self, message: str) -> None:
           self._console.print(f"[cyan]{message}[/cyan]")

       def success(self, message: str) -> None:
           self._console.print(f"[green]{message}[/green]")

       def warning(self, message: str) -> None:
           self._console.print(f"[yellow]{message}[/yellow]")

       def important(self, message: str) -> None:
           self._console.print(f"[magenta]{message}[/magenta]")

       def failure(self, message: str) -> None:
           self._console.print(f"[red]{message}[/red]")

       def starting(self, message: str) -> None:
           self._console.print(f"[blue]{message}[/blue]")

       def debug(self, message: str) -> None:
           self._console.print(f"[white]{message}[/white]")

       def thinking(self, message: str) -> None:
           self._console.print(f"[dim]{message}[/dim]")

       def trace(self, message: str) -> None:
           self._console.print(f"[grey70]{message}[/grey70]")
   ```

4. **Rich color mapping** (termcolor → Rich):
   - `color="cyan"` → `[cyan]...[/cyan]`
   - `color="green"` → `[green]...[/green]`
   - `color="yellow"` → `[yellow]...[/yellow]`
   - `color="magenta"` → `[magenta]...[/magenta]`
   - `color="red"` → `[red]...[/red]`
   - `color="blue"` → `[blue]...[/blue]`
   - `color="white"` → `[white]...[/white]`
   - `color="dark_grey"` → `[dim]...[/dim]`
   - `color="light_grey"` → `[grey70]...[/grey70]`

### Phase 2: Migration (File by File)

#### Order of Migration:
1. `src/gemini_supply/computers/browser_host.py` (10 occurrences, mostly `unrestricted`)
2. `src/gemini_supply/auth/flow.py` (17 occurrences, all `auth`)
3. `src/gemini_supply/preferences/normalizer.py` (2 occurrences, `normalizer`)
4. `src/gemini_supply/agent.py` (3 occurrences, agent-prefixed + unprefixed)
5. `src/gemini_supply/orchestrator.py` (30 occurrences, mixed categories)

#### For Each File:
1. Add `from gemini_supply.term import activity_log` import
2. Replace each `termcolor.cprint(...)` with appropriate `activity_log().category.method(...)` call
3. Remove `termcolor` import
4. Run linters and tests

#### Example Transformations:

**Before:**
```python
termcolor.cprint("[auth] Opening login drawer.", "cyan")
```

**After:**
```python
activity_log().auth.operation("Opening login drawer.")
```

**Before:**
```python
termcolor.cprint(f"[{agent_label}] Shopping for '{display_label}'.", color="cyan")
```

**After:**
```python
activity_log().agent(agent_label).operation(f"Shopping for '{display_label}'.")
```

**Before:**
```python
termcolor.cprint("Camoufox host ready.", color="green")
```

**After:**
```python
activity_log().success("Camoufox host ready.")
```

**Before:**
```python
termcolor.cprint(
    f"[{agent_label}] User override received. Using new text '{active_override.override_text}'.",
    color="cyan",
)
```

**After:**
```python
activity_log().agent(agent_label).operation(
    f"User override received. Using new text '{active_override.override_text}'."
)
```

### Phase 3: Cleanup

1. Remove `termcolor` dependency from `pyproject.toml`
2. Run `uv sync` to clean up
3. Verify no remaining `termcolor` imports:
   ```bash
   rg "termcolor" --type py
   ```
4. Run `ruff format .`, `ruff check . --fix`, and `ty check`

## Benefits

1. **No Parameter Passing**: Context-based access eliminates passing `log` through every function signature
2. **Type Safety**: IDE autocomplete for `activity_log().auth.operation()` vs raw strings
3. **Consistency**: All logging through one interface (Rich)
4. **Maintainability**: Change color scheme in one place
5. **Readability**: Intent-based names (`success()`) vs low-level (`cprint(..., "green")`)
6. **Rich Features**: Access to Rich's advanced formatting (progress bars, panels, markup) now and in future
7. **DRY**: Prefix formatting centralized in one place
8. **Async-Safe**: `contextvars` properly scopes to async context, works with concurrent agents

## Open Questions

1. Should we add convenience methods for common patterns?
   - e.g., `activity_log().auth.credential_step(field: str)` → "Waiting for {field} field."

2. Should we allow Rich markup in messages?
   - Rich supports `[bold]text[/bold]`, etc.
   - Allow users to include Rich markup in messages?
   - Or escape all user content to prevent accidental markup?
   - **Recommendation**: Allow it - gives us flexibility for emphasis

## Migration Checklist

- [ ] Add contextvars setup (`activity_log()`, `set_activity_log()`) to `term.py`
- [ ] Implement `CategoryLogger` class in `term.py`
- [ ] Extend `ActivityLog` with semantic methods and category properties
- [ ] Remove `lock` parameter from `ActivityLog.__init__`
- [ ] Update `print_reasoning()` and `show_screenshot()` to remove lock usage
- [ ] Add `set_activity_log(logger)` call in orchestrator's `run_shopping()`
- [ ] Migrate `browser_host.py`
- [ ] Migrate `auth/flow.py`
- [ ] Migrate `preferences/normalizer.py`
- [ ] Migrate `agent.py`
- [ ] Migrate `orchestrator.py`
- [ ] Remove `termcolor` dependency from `pyproject.toml`
- [ ] Run `uv sync`
- [ ] Run `ruff format .`, `ruff check . --fix`, and `ty check`
- [ ] Run full test suite
- [ ] Manual smoke test with `--concurrency 2`
