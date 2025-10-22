**Important!**

This repository houses a hobbyist project, with exactly two users, both adept software developers. Writing backwards compatible software is not wanted, nor valued. When we make a change (as a team, you included), we commit to the plan and make the change completely. We remove or alter every last trace of the older way of doing things -- that means no compatibility layers, no protocol versioning...no discussions even! Nothing.

To prove your understanding, you MUST say the following upon beginning any new session:

> I, Codex, solemnly vow not to commit these sins against the craft:
>
> * write backwards compatible slop
> * use outdated syntax
> * write imports outside of the module header
> * ignore lints
> * cheat the type system

## Project Structure & Module Organization
The CLI entry point lives in `src/gemini_supply/main.py`, with session orchestration in `src/gemini_supply/shopping/` (settings models live in `shopping/models.py`, orchestration loop in `shopping/orchestrator.py`). Browser automation helpers sit under `src/gemini_supply/computers/`. Grocery-specific flows (providers, types) are in `src/gemini_supply/grocery/`. Preference orchestration (normalization, storage, Telegram bridge) is under `src/gemini_supply/preferences/`. Tests mirror those modules inside `tests/`, while configuration examples and integration notes sit in `docs/` and `config.sample.yaml`. Use `examples/` for quick start snippets; artifacts produced by packaging land in `dist/`.

## Build, Test, and Development Commands
- `uv sync` installs all runtime and dev dependencies.
- `uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml --postal-code "M5V 1J1"` processes the default YAML shopping list. This command now runs the automated login flow up front; make sure `GEMINI_SUPPLY_METRO_USERNAME` / `GEMINI_SUPPLY_METRO_PASSWORD` are exported.
- `uv run pyright` runs static type checks; fix any warnings before submitting.
- `uv run pytest -n auto -q` executes the async-heavy test suite quickly in parallel.
- `ruff check . --fix` and `ruff format .` enforce linting and formatting.
- If you change dependencies, bump `pyproject.toml` (`uv version --bump major|minor|patch`) and regenerate `uv.lock` with `uv pip compile pyproject.toml --upgrade`.
- When you finish a task or cleanup pass, always run `ruff format .`, `ruff check . --fix`, and `uv run pyright`, and fix every reported issue before you hand the work off.
- Feature toggles: the product preference system lives under `src/gemini_supply/preferences/`. Normalizer settings (model, base URL, API key) are configurable via the `preferences` block in `config.yaml`.

## Coding Style & Naming Conventions
Target Python 3.13 features: prefer `TypeA | TypeB` over `Union`, and `Type | None` instead of `Optional`. The repo enforces 2-space indentation and a 100-character line limit via Ruff. Never use `Any`. **FORBIDDEN**: `getattr`, `hasattr`, `setattr`, and all dynamic attribute access are strictly prohibited—model structured data with explicit dataclasses or Pydantic models, and access fields directly. **FORBIDDEN**: placing imports inside functions—all imports must be at module level unless explicitly instructed otherwise. Domain payloads (added item results, shopping summary, etc.) are dataclasses now; do not add new `dict`/`TypedDict` facades. Match existing CLI flag spelling (`--shopping-list`, `--time-budget`) and keep module names snake_case. Prefer imports from `collections.abc` for abstract container types (e.g., `Sequence`).

## Testing Guidelines
Use pytest with `pytest-asyncio` fixtures; asynchronous behaviors should be isolated with `async def` tests named `test_*`. Keep new tests alongside their modules in `tests/`. When adding features that touch remote automation or preferences, add regression tests (see `tests/test_preferences_behavior.py`). Run `uv run pytest -n auto -q` plus `uv run pyright` before opening a PR and ensure coverage stays consistent with existing suites.

## Commit & Pull Request Guidelines
Follow the repository's present-tense, concise commit style (e.g., `Add concurrency model limiting tabs`). Squash noisy work-in-progress commits locally. Pull requests must include: a short summary, linked issues when applicable, before/after notes or screenshots for UI-facing changes, and the exact verification commands you ran (`ruff`, `pyright`, `pytest -n auto`, relevant `gemini-supply` commands). Highlight any risks to shopping flows or authentication so reviewers can focus testing.

## Security & Configuration Tips
Never commit `GEMINI_API_KEY`, Metro credentials, Telegram bot tokens, or home-assistant tokens. Use environment variables (`export GEMINI_API_KEY=...`, `export GEMINI_SUPPLY_METRO_USERNAME=...`, `export GEMINI_SUPPLY_METRO_PASSWORD=...`, `export GEMINI_SUPPLY_USER_DATA_DIR=...`) and keep personal configs in `~/.config/gemini-supply/`. The `preferences` section of `config.yaml` should point to a writable YAML file plus Telegram credentials; treat both values as secrets. When sharing repro steps, reference `config.sample.yaml` rather than real credentials. Persistent browser profiles are stored under the user data directory; rotate or isolate them if you suspect credential leakage.
