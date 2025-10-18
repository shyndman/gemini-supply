Gemini Supply — Grocery Shopping Agent
======================================

Gemini‑powered browser agent that adds items from your shopping list to your metro.ca cart. The project now runs exclusively with Camoufox (a hardened Firefox build) to reduce automation detection.

Quick Start
-----------

- Install deps with uv:
  - `uv sync`

- Set environment (one of):
  - `export GEMINI_API_KEY="..."`
  - or Vertex AI: `export USE_VERTEXAI=true && export VERTEXAI_PROJECT=... && export VERTEXAI_LOCATION=...`

Authenticate (Camoufox)
-----------------------

Run a relaxed, headful auth session (Turnstile/SSO compatible). The Camoufox executable is auto‑detected via `python -m camoufox path`, but you can pass one explicitly.

- Persistent profile (recommended):
  - `uv run gemini-supply auth-setup --user-data-dir ~/.config/gemini-supply/camoufox-profile`
  - Optional explicit binary: `--camoufox-exec /home/you/.cache/camoufox/camoufox`

Shop
----

Process all uncompleted items from a YAML shopping list with the authenticated session.

- `uv run gemini-supply shop --list ~/.config/gemini-supply/shopping_list.yaml --user-data-dir ~/.config/gemini-supply/camoufox-profile`

Flags you may find useful:
- `--model` to choose a Gemini model (default `gemini-2.5-computer-use-preview-10-2025`)
- `--highlight-mouse` to show cursor feedback
- `--time-budget` with timedelta parsing (e.g., `5m`, `300s`, `1h`) per item
- `--max-turns` to cap agent iterations per item

Notes
-----

- Camoufox is the single browser path end‑to‑end; Chromium/Chrome is not used.
- Auth runs in relaxed mode (no network blocks) to allow captcha/SSO resources; shopping sessions enforce an allowlist/blocklist for safety.
- Use email/password on metro.ca where possible. Third‑party SSO (e.g., Google) may refuse automated contexts.
- Ctrl+C exits cleanly.

Troubleshooting
---------------

- If Turnstile appears during auth, just solve it; the session is persisted.
- If you need to relocate your Camoufox binary, pass `--camoufox-exec` or rely on auto‑detection.
- For issues with saved sessions, try a fresh user data dir (new folder) and re‑authenticate.
