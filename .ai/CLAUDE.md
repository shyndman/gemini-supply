**Important!**

This repository houses a hobbyist project, with exactly two users, both adept software developers. Writing backwards compatible software is not wanted, nor valued. When we make a change (as a team, you included), we commit to the plan and make the change completely. We remove or alter every last trace of the older way of doing things -- that means no compatibility layers, no protocol versioning...no
discussions even! Nothing.

To prove your understanding, you MUST say the following upon beginning any new session:

> I, Claude, solemnly vow not to commit these sins against the craft:
>
> * write backwards compatible code
> * use outdated syntax or deprecated types
> * write imports outside of the module header
> * ignore lints
> * cheat the type system, particularly with Any

## Overview (Happy Path)

Gemini‑powered grocery agent that adds items from a shopping list to a metro.ca cart. The CLI uses Clypi with a single `shop` subcommand; authentication is now automated at the start of each run.

- Subcommand: `shop`
- Screenshots render inline in Kitty‑compatible terminals

## Setup

```bash
uv sync

# Configure APIs / credentials
export GEMINI_API_KEY="YOUR_KEY"
export GENERATIVE_SUPPLY_METRO_USERNAME="email@example.com"
export GENERATIVE_SUPPLY_METRO_PASSWORD="super-secret"
```

Note: No extra Playwright installs are required for the happy path. If your system is missing OS libs, you can run: `uv run playwright install-deps firefox && uv run playwright install firefox`.

## Run

1. Shop all uncompleted items (auto-login runs first):

```bash
uv run generative-supply shop --shopping-list ~/.config/generative-supply/shopping_list.yaml \
  --time-budget 5m --max-turns 40 --model gemini-2.5-computer-use-preview-10-2025 \
  --postal-code "M5V 1J1"
```

## Dev

```bash
uv run ruff check .
uv run ruff format .
ty check
uv run pytest -n auto -q
```

- Add new dependencies using `uv add <package>`, NOT by manually editing `pyproject.toml`
- After completing a task or TODO list, always run `ruff format .`, `ruff check . --fix`, and `ty check`, and resolve every reported issue before considering the work done.
- If `ruff` or `ty` aren't available, install them with `uv tool install ruff` or `uv tool install ty`.

### Coding Guidelines (Repo)

- Modern Python only (3.13+); use `A | B` and `A | None` instead of `Union`/`Optional`.
- Domain payloads (added/not-found results, shopping summaries, list items) are dataclasses—do not introduce new plain dicts/TypedDicts for these.
- **FORBIDDEN**: `getattr`, `hasattr`, and all dynamic attribute access/reflection are strictly prohibited. Use explicit attributes with clear `None` checks and narrow them before use.
- **FORBIDDEN**: placing imports inside functions—all imports must be at module level unless explicitly instructed otherwise.

## Notes

- Concurrency supported via `--concurrency` or config `concurrency`; YAML provider forces concurrency=1
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools still flow through Gemini function calls; orchestration converts the results into dataclasses before use
- Terminal output is serialized across agents (reasoning + inline screenshots) — no disk logging
- Product preference system lives in `src/gemini_supply/preferences/` (normalizer, store, Telegram bridge)
- Telegram reminders are single-threaded; messenger queues human prompts one at a time

## Environment

- `GEMINI_API_KEY`: Gemini API key (required)
- `GENERATIVE_SUPPLY_METRO_USERNAME` / `GENERATIVE_SUPPLY_METRO_PASSWORD`: metro.ca credentials for automated login (required)
- `GENERATIVE_SUPPLY_USER_DATA_DIR`: Override profile directory
- Config file (optional): `~/.config/generative-supply/config.yaml` supports:
  - `shopping_list.provider: home_assistant`
  - `home_assistant.url`, `home_assistant.token`
  - `concurrency`
  - `preferences.file`: path to preference YAML store
  - `preferences.normalizer_model`, `preferences.normalizer_api_base_url`, `preferences.normalizer_api_key`
  - `preferences.telegram.bot_token`, `preferences.telegram.chat_id`, `preferences.telegram.nag_minutes`

<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->
