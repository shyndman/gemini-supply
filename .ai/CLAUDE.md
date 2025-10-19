# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repo.

## Overview (Happy Path)

Gemini‑powered grocery agent that adds items from a YAML shopping list to a metro.ca cart. Runtime is Camoufox (hardened Firefox via Playwright). The CLI uses Clypi subcommands.

- Browser: Camoufox only (auto‑detected via `python -m camoufox path`)
- Subcommands: `auth-setup`, `shop`
- Screenshots render inline in Kitty‑compatible terminals

## Setup

```bash
uv sync

# Configure API (Gemini Developer API)
export GEMINI_API_KEY="YOUR_KEY"
```

Note: No extra Playwright installs are required for the happy path. If your system is missing OS libs, you can run: `uv run playwright install-deps firefox && uv run playwright install firefox`.

## Run

1) Authenticate (headful, relaxed):
```bash
# Optional override (Linux default is ~/.config/gemini-supply/camoufox-profile)
# export GEMINI_SUPPLY_USER_DATA_DIR=~/.config/gemini-supply/camoufox-profile

uv run gemini-supply auth-setup
```

2) Shop all uncompleted items:
```bash
uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml \
  --time-budget 5m --max-turns 40 --model gemini-2.5-computer-use-preview-10-2025 \
  --postal-code "M5V 1J1"
```

Headless shopping (auth should remain headful):
```bash
export PLAYWRIGHT_HEADLESS=1
uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml --postal-code "M5V 1J1"
```

## Dev

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
uv run pytest -q
```

### Coding Guidelines (Repo)

- Modern Python only (3.13+); use `A | B` and `A | None` instead of `Union`/`Optional`.
- If you create a mapping, it must be a `TypedDict`. Never use `Any`.
- Do not use dynamic attribute access like `getattr`, `hasattr`, or similar reflection. Prefer explicit attributes with clear `None` checks and narrow them before use.

## Architecture

- `main.py`: Clypi CLI (`auth-setup`, `shop`)
- `grocery_main.py`: Orchestrator (per‑item loop, time/turn caps, terminal tool handling)
- `agent.py`: Gemini loop (function calls → computer actions, keeps last 3 screenshot turns)
- `computers/camoufox_browser.py`: Camoufox via Playwright Firefox (allowlist/blocklist, banner, DOM auth check)
- `computers/playwright_computer.py`: Common actions (click, type, scroll, key combos, screenshots)
- `display.py`: Kitty graphics screenshot rendering
- `grocery/types.py`: TypedDict + Pydantic models for tool I/O and domain types
- `grocery/shopping_list.py`: `ShoppingListProvider` + YAML implementation

Key details:
- Single‑tab only; new tabs are redirected into the current page
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools return TypedDicts, registered via `FunctionDeclaration.from_callable()`
  

## Environment

- `GEMINI_API_KEY`: Gemini API key (required)
- `GEMINI_SUPPLY_USER_DATA_DIR`: Override profile directory (Linux default: `~/.config/gemini-supply/camoufox-profile`)
- `PLAYWRIGHT_HEADLESS`: Run headless (optional)
