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

# Choose one API path
export GEMINI_API_KEY="YOUR_KEY"               # Gemini Developer API
# or Vertex AI
export USE_VERTEXAI=true
export VERTEXAI_PROJECT="your-project-id"
export VERTEXAI_LOCATION="your-location"
```

Note: No extra Playwright installs are required for the happy path. If your system is missing OS libs, you can run: `uv run playwright install-deps firefox && uv run playwright install firefox`.

## Run

1) Authenticate (headful, relaxed):
```bash
uv run gemini-supply auth-setup --user-data-dir ~/.config/gemini-supply/camoufox-profile
# Optional: --camoufox-exec /path/to/camoufox (auto‑detected if omitted)
```

2) Shop all uncompleted items:
```bash
uv run gemini-supply shop --list ~/.config/gemini-supply/shopping_list.yaml \
  --user-data-dir ~/.config/gemini-supply/camoufox-profile \
  --time-budget 5m --max-turns 40 --model gemini-2.5-computer-use-preview-10-2025
```

Headless shopping (auth should remain headful):
```bash
export PLAYWRIGHT_HEADLESS=1
uv run gemini-supply shop --list ~/.config/gemini-supply/shopping_list.yaml --user-data-dir ~/.config/gemini-supply/camoufox-profile
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
- Safety decisions: prompts the user if the model requests confirmation (piping `yes` will auto‑confirm)

## Environment

- `GEMINI_API_KEY`: Gemini API key (required unless using Vertex)
- `USE_VERTEXAI`, `VERTEXAI_PROJECT`, `VERTEXAI_LOCATION`: Vertex settings (optional)
- `PLAYWRIGHT_HEADLESS`: Run headless (optional)
