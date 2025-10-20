# Repository Guidelines

## Project Structure & Module Organization
The CLI entry point lives in `src/gemini_supply/main.py`, with session orchestration in `src/gemini_supply/agent.py`, browser automation helpers under `src/gemini_supply/computers/`, and grocery-specific flows in `src/gemini_supply/grocery/`. Preference orchestration (normalization, storage, Telegram bridge) is under `src/gemini_supply/preferences/`. Tests mirror those modules inside `tests/`, while configuration examples and integration notes sit in `docs/` and `config.sample.yaml`. Use `examples/` for quick start snippets; artifacts produced by packaging land in `dist/`.

## Build, Test, and Development Commands
- `uv sync` installs all runtime and dev dependencies.
- `uv run gemini-supply auth-setup` opens an authenticated metro.ca session using the configured profile.
- `uv run gemini-supply shop --shopping-list ~/.config/gemini-supply/shopping_list.yaml --postal-code "M5V 1J1"` processes the default YAML shopping list.
- `uv run ruff check .` and `uv run ruff format .` enforce linting and formatting.
- `uv run pyright` runs static type checks; fix any warnings before submitting.
- `uv run pytest -q` executes the async-heavy test suite quickly.
- If you change dependencies, bump `pyproject.toml` and regenerate `uv.lock` with `uv pip compile pyproject.toml --upgrade`.
- Feature toggles: the product preference system lives under `src/gemini_supply/preferences/`. Normalizer settings (model, base URL, API key) are configurable via the `preferences` block in `config.yaml`.

## Coding Style & Naming Conventions
Target Python 3.13 features: prefer `TypeA | TypeB` over `Union`, and `Type | None` instead of `Optional`. The repo enforces 2-space indentation and a 100-character line limit via Ruff. Avoid `Any`, dynamic attribute access, and unchecked `getattr`; model structured data with `TypedDict` or Pydantic models. Match existing CLI flag spelling (`--shopping-list`, `--time-budget`) and keep module names snake_case. Prefer imports from `collections.abc` for abstract container types (e.g., `Sequence`).

## Testing Guidelines
Use pytest with `pytest-asyncio` fixtures; asynchronous behaviors should be isolated with `async def` tests named `test_*`. Keep new tests alongside their modules in `tests/`. When adding features that touch remote automation, add regression tests that stub browser interactions or config objects. Run `uv run pytest -q` plus `uv run pyright` before opening a PR and ensure coverage stays consistent with existing suites.

## Commit & Pull Request Guidelines
Follow the repository’s present-tense, concise commit style (e.g., `Add concurrency model limiting tabs`). Squash noisy work-in-progress commits locally. Pull requests must include: a short summary, linked issues when applicable, before/after notes or screenshots for UI-facing changes, and the exact verification commands you ran (`ruff`, `pyright`, `pytest`, relevant `gemini-supply` commands). Highlight any risks to shopping flows or authentication so reviewers can focus testing.

## Security & Configuration Tips
Never commit `GEMINI_API_KEY`, Telegram bot tokens, or home-assistant tokens. Use environment variables (`export GEMINI_API_KEY=...`, `export GEMINI_SUPPLY_USER_DATA_DIR=...`) and keep personal configs in `~/.config/gemini-supply/`. The `preferences` section of `config.yaml` should point to a writable YAML file plus Telegram credentials; treat both values as secrets. When sharing repro steps, reference `config.sample.yaml` rather than real credentials. Persistent browser profiles are stored under the user data directory; rotate or isolate them if you suspect credential leakage.
