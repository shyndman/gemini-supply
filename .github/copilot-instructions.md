# Copilot Instructions for generative-supply

## Project Overview

This is a Gemini-powered browser agent that adds items from your shopping list to your metro.ca cart. It's a hobbyist project with exactly two users, both adept software developers. **Backwards compatibility is not valued** - when making changes, commit fully and remove all traces of older approaches (no compatibility layers, no protocol versioning).

## Project Structure

- **CLI entry point**: `src/generative_supply/__main__.py`
- **Shopping orchestration**: `src/generative_supply/orchestrator.py`
- **Browser automation**: `src/generative_supply/computers/`
- **Preference system**: `src/generative_supply/preferences/` (normalization, storage, Telegram bridge)
- **Tests**: `tests/` (mirrors module structure)
- **Configuration**: `config.sample.yaml` (examples), `docs/` (integration notes)
- **Examples**: `examples/` (quick start snippets)

## Development Setup

```bash
# Install dependencies
uv sync

# Set required environment variables
export GEMINI_API_KEY="YOUR_KEY"
export GENERATIVE_SUPPLY_METRO_USERNAME="email@example.com"
export GENERATIVE_SUPPLY_METRO_PASSWORD="super-secret"

# Optional: override profile directory
export GENERATIVE_SUPPLY_USER_DATA_DIR="..."
```

## Build, Test, and Lint Commands

```bash
# Run tests (parallel, quiet)
uv run pytest -n auto -q

# Type checking (install with: uv tool install ty)
ty check

# Linting and formatting (install with: uv tool install ruff)
ruff check . --fix
ruff format .

# Run the application
uv run generative-supply shop --shopping-list ~/.config/generative-supply/shopping_list.yaml --postal-code "M5V 1J1"
```

**Before completing any task**: Always run `ruff format .`, `ruff check . --fix`, and `ty check`, and fix every reported issue.

## Coding Standards

### Python Version and Type Hints
- Target Python 3.13+
- Use modern type syntax: `TypeA | TypeB` instead of `Union`
- Use `Type | None` instead of `Optional`
- **FORBIDDEN**: Never use `Any` type

### Style Guidelines
- 2-space indentation (enforced by Ruff)
- 100-character line limit
- Module names: snake_case
- CLI flags: kebab-case (e.g., `--shopping-list`, `--time-budget`)

### Absolute Prohibitions
- **FORBIDDEN**: `getattr`, `hasattr`, `setattr`, and all dynamic attribute access - use explicit dataclasses or Pydantic models with direct field access
- **FORBIDDEN**: Imports inside functions - all imports must be at module level
- **FORBIDDEN**: Using `dict`/`TypedDict` for domain payloads - use dataclasses instead
- **FORBIDDEN**: Backwards compatibility layers

### Imports
- Prefer `collections.abc` for abstract container types (e.g., `Sequence`)
- All imports must be at module level unless explicitly instructed otherwise

## Testing Guidelines

- Use pytest with `pytest-asyncio` fixtures
- Test files: `test_*.py` in `tests/` directory
- Async behaviors: `async def test_*` functions
- Add regression tests for features touching remote automation or preferences
- Run `uv run pytest -n auto -q` and `ty check` before opening PRs
- Maintain coverage consistent with existing test suites

## Dependencies Management

- Add dependencies: `uv add <package>` (NOT by manually editing `pyproject.toml`)
- Update dependencies: `uv lock --upgrade`
- Version bumping: `uv version --bump major|minor|patch`

## Security and Configuration

**Never commit secrets**:
- `GEMINI_API_KEY`
- Metro credentials (`GENERATIVE_SUPPLY_METRO_USERNAME`, `GENERATIVE_SUPPLY_METRO_PASSWORD`)
- Telegram bot tokens
- Home Assistant tokens

Store personal configs in `~/.config/generative-supply/` and reference `config.sample.yaml` for examples.

## Commit Guidelines

- Present-tense, concise messages (e.g., "Add concurrency model limiting tabs")
- Squash work-in-progress commits locally
- Include in PRs:
  - Short summary
  - Linked issues when applicable
  - Before/after notes or screenshots for UI changes
  - Exact verification commands run
  - Risks to shopping flows or authentication

## Common Patterns

### Dataclasses for Domain Models
Use dataclasses for all domain payloads (shopping results, list items, summaries).

### Concurrency
- Supported via `--concurrency` flag or `concurrency` in config
- YAML provider forces `concurrency=1`
- Multiple items processed in parallel tabs

### Browser Automation
- Normalized coordinates (1000×1000) denormalized per viewport
- Custom tools flow through Gemini function calls
- Results converted to dataclasses

### Output
- Terminal output serialized across agents (reasoning + inline screenshots)
- No disk logging
- Screenshots render inline in Kitty-compatible terminals

## Key Features

### Authentication
Automated login at start of each run using `GENERATIVE_SUPPLY_METRO_USERNAME` and `GENERATIVE_SUPPLY_METRO_PASSWORD`. Credentials stored in persistent profile directory.

### Product Preferences
- System lives in `src/generative_supply/preferences/`
- Records user choices per canonical category
- Telegram integration for disambiguation prompts
- Normalizer runs on Gemini flash-lite model (no external config needed)

### Shopping List Providers
- YAML provider: `--shopping-list path/to/file.yaml`
- Home Assistant provider: configured via `config.yaml`

## CLI Flags Reference

- `--model`: Choose Gemini model (default: `gemini-2.5-computer-use-preview-10-2025`)
- `--highlight-mouse`: Show cursor feedback
- `--time-budget`: Per-item time limit (e.g., `5m`, `300s`, `1h`)
- `--max-turns`: Cap agent iterations per item
- `--concurrency`: Process multiple items in parallel (default: 1)
- `--shopping-list`: Path to YAML shopping list
- `--postal-code`: Postal code for delivery

## Troubleshooting

- Automated login failures: Verify environment variables and rerun
- Fresh start: Delete profile directory or set different `GENERATIVE_SUPPLY_USER_DATA_DIR`
- Missing OS libs: Run `uv run playwright install-deps firefox && uv run playwright install firefox`
