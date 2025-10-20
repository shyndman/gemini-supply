# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repo.

## Overview (Happy Path)

Gemini‑powered grocery agent that adds items from a shopping list to a metro.ca cart. The CLI uses Clypi subcommands.

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

## Dev

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
uv run pytest -q
# If deps change, regenerate uv.lock
uv pip compile pyproject.toml --upgrade
```

### Coding Guidelines (Repo)

- Modern Python only (3.13+); use `A | B` and `A | None` instead of `Union`/`Optional`.
- If you create a mapping, it must be a `TypedDict`. Never use `Any`.
- **FORBIDDEN**: `getattr`, `hasattr`, and all dynamic attribute access/reflection are strictly prohibited. Use explicit attributes with clear `None` checks and narrow them before use.

## Notes

- Concurrency supported via `--concurrency` or config `concurrency`; YAML provider forces concurrency=1
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools return TypedDicts, registered via `FunctionDeclaration.from_callable()`
- Terminal output is serialized across agents (reasoning + inline screenshots) — no disk logging
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools return TypedDicts, registered via `FunctionDeclaration.from_callable()`
- Product preference system lives in `src/gemini_supply/preferences/` (normalizer, store, Telegram bridge)
- Telegram reminders are single-threaded; messenger queues human prompts one at a time

## Environment

- `GEMINI_API_KEY`: Gemini API key (required)
- `GEMINI_SUPPLY_USER_DATA_DIR`: Override profile directory
- Config file (optional): `~/.config/gemini-supply/config.yaml` supports:
  - `shopping_list.provider: home_assistant`
  - `home_assistant.url`, `home_assistant.token`
  - `postal_code`
  - `concurrency`
  - `preferences.file`: path to preference YAML store
  - `preferences.normalizer_model`, `preferences.normalizer_api_base_url`, `preferences.normalizer_api_key`
  - `preferences.telegram.bot_token`, `preferences.telegram.chat_id`, `preferences.telegram.nag_minutes`
- Telegram bot token and chat ID are secrets; never commit them
