Gemini Supply — Grocery Shopping Agent
======================================

Gemini‑powered browser agent that adds items from your shopping list to your metro.ca cart.

Quick Start
-----------

- Install deps with uv:
  - `uv sync`

- Set environment:
  - `export GEMINI_API_KEY="..."`
  - `export GENERATIVE_SUPPLY_METRO_USERNAME="email@example.com"`
  - `export GENERATIVE_SUPPLY_METRO_PASSWORD="super-secret"`
  - Optional profile override: `export GENERATIVE_SUPPLY_USER_DATA_DIR=...`

Authentication
--------------

The `shop` command now authenticates automatically before starting and whenever the session expires.
Make sure the Metro username/password environment variables above are set. Credentials are stored in
the persistent profile directory for subsequent runs.

Shop
----

Process all uncompleted items from a YAML shopping list with the authenticated session.

- YAML provider:
  - `uv run generative-supply shop --shopping-list ~/.config/generative-supply/shopping_list.yaml --postal-code "M5V 1J1"`

- Home Assistant provider (via config):
  - Create `~/.config/generative-supply/config.yaml` (see `config.sample.yaml`)
  - Minimal config:
    ```yaml
    shopping_list:
      provider: home_assistant
      url: http://home.don
      token: YOUR_LONG_LIVED_ACCESS_TOKEN

    preferences:
      normalizer_model: "qwen3:1.7b"
      normalizer_api_base_url: "http://ollama/v1"
      telegram:
        bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
        chat_id: -123456789

    # optional
    concurrency: 3
    ```
  - Run: `uv run generative-supply shop`
  - Details: see `docs/01-home-assistant-shopping-lists.md`

Product preferences & Telegram prompts
--------------------------------------

- Add a `preferences` block to `config.yaml` (see `config.sample.yaml`).
  - `file`: where canonical item → product mappings are stored.
  - `normalizer_model`: OpenAI-compatible model name used for categorizing items (defaults to `qwen3:1.7b`).
  - `normalizer_api_base_url`: Optional OpenAI-compatible endpoint (e.g., Ollama `http://ollama-nvidia.don/v1`).
  - `normalizer_api_key`: Optional key for remote providers; leave blank for local Ollama.
  - `telegram.bot_token` and `telegram.chat_id`: credentials for the chat the bot should post in.
  - Optional `telegram.nag_minutes` adjusts reminder cadence (default 30).
- Normalization uses OpenAI-compatible APIs. Provide credentials via `normalizer_api_key`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`. For Ollama, set `normalizer_api_base_url` (or `OLLAMA_BASE_URL`) and optionally `OLLAMA_API_KEY`.
- When configured, the agent records your choices per canonical category (e.g., “Milk”) and reuses them automatically.
- If the browser agent cannot disambiguate a product, it will queue a prompt in the configured Telegram chat so you can choose or type an alternative.

Flags you may find useful:
- `--model` to choose a Gemini model (default `gemini-2.5-computer-use-preview-10-2025`)
- `--highlight-mouse` to show cursor feedback
- `--time-budget` with timedelta parsing (e.g., `5m`, `300s`, `1h`) per item
- `--max-turns` to cap agent iterations per item
 - `--concurrency` to process multiple items in parallel (tabs). Set `0` to use config or default `1`.

Behavior & Notes
----------------

- Parallelism: processes multiple items in parallel (tabs). Output (reasoning + screenshots) is serialized to the terminal per turn so logs don’t interleave.
- Use email/password on metro.ca where possible. Third‑party SSO (e.g., Google) may refuse automated contexts.
- Ctrl+C exits cleanly.

Troubleshooting
---------------

- If the automated login reports a failure, verify `GENERATIVE_SUPPLY_METRO_USERNAME` / `GENERATIVE_SUPPLY_METRO_PASSWORD`
  and rerun the command. The workflow will refresh credentials for you when the session expires.
- The profile directory persists cookies/tokens automatically. To start fresh, delete the folder or set a different `GENERATIVE_SUPPLY_USER_DATA_DIR`.
