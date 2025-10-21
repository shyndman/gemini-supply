# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repo.

## Overview (Happy Path)

Gemini‑powered grocery agent that adds items from a shopping list to a metro.ca cart. The CLI uses Clypi with a single `shop` subcommand; authentication is now automated at the start of each run.

- Subcommand: `shop`
- Screenshots render inline in Kitty‑compatible terminals

## Setup

```bash
uv sync

# Configure APIs / credentials
export GEMINI_API_KEY="YOUR_KEY"
export GEMINI_SUPPLY_METRO_USERNAME="email@example.com"
export GEMINI_SUPPLY_METRO_PASSWORD="super-secret"
```

Note: No extra Playwright installs are required for the happy path. If your system is missing OS libs, you can run: `uv run playwright install-deps firefox && uv run playwright install firefox`.

## Run

1) Shop all uncompleted items (auto-login runs first):
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

- After completing a task or TODO list, always run `ruff format .`, `ruff check . --fix`, and `uv run pyright`, and resolve every reported issue before considering the work done.

### Coding Guidelines (Repo)

- Modern Python only (3.13+); use `A | B` and `A | None` instead of `Union`/`Optional`.
- Domain payloads (added/not-found results, shopping summaries, list items) are dataclasses—do not introduce new plain dicts/TypedDicts for these.
- **FORBIDDEN**: `getattr`, `hasattr`, and all dynamic attribute access/reflection are strictly prohibited. Use explicit attributes with clear `None` checks and narrow them before use.

## Notes

- Concurrency supported via `--concurrency` or config `concurrency`; YAML provider forces concurrency=1
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools still flow through Gemini function calls; orchestration converts the results into dataclasses before use
- Terminal output is serialized across agents (reasoning + inline screenshots) — no disk logging
- Product preference system lives in `src/gemini_supply/preferences/` (normalizer, store, Telegram bridge)
- Telegram reminders are single-threaded; messenger queues human prompts one at a time

## Environment

- `GEMINI_API_KEY`: Gemini API key (required)
- `GEMINI_SUPPLY_METRO_USERNAME` / `GEMINI_SUPPLY_METRO_PASSWORD`: metro.ca credentials for automated login (required)
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
