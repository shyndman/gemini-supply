# Multi-Tab Browser Host: One Browser, Many Agents

## Goals

- Run multiple agents in parallel in a single persistent Camoufox/Firefox browser session.
- Give each agent its own tab (Playwright Page) and a tab-scoped Computer interface.
- Remove single-tab interception; metro.ca does not open new tabs in practice.
- Keep auth, allow/block, and banner injection at the context level.

Non-goals
- Do not implement per-turn parallelism within a single agent.
- Do not change tool schemas or domain logic beyond what’s required to support multi-tab.

## High-Level Design

- BrowserHost (new): owns Playwright startup, persistent profile, single BrowserContext, and shared policies (allowlist, blocklist, banners, auth checks). Provides `new_tab()` that returns a TabComputer bound to a unique Page.
- TabComputer (new): implements the `Computer` protocol for one Page. No shared `self._page` across agents. All actions target this page only.
- Orchestrator: launches one BrowserHost and spawns N TabComputers (bounded by `--concurrency`). Each item runs in its own tab + agent.
- Gemini: keep one process-wide `genai.Client` (injected into BrowserAgent) and call `generate_content` via `asyncio.to_thread(...)`. Optionally gate with a semaphore for QPS control.

## API and Class Changes

Files and changes (paths are workspace-relative):

- src/gemini_supply/computers/computer.py
  - No interface changes required; TabComputer implements the same methods against its Page.

- src/gemini_supply/computers/playwright_computer.py
  - Remove single-tab interception logic:
    - Delete `_handle_new_page` and the `context.on("page", self._handle_new_page)` hook.
  - This class will remain as the basis for shared helpers (e.g., key mapping, highlight_mouse), but not used directly by the orchestrator once BrowserHost/TabComputer exist.

- src/gemini_supply/computers/camoufox_browser.py
  - Split responsibilities:
    - New `BrowserHost` (CamoufoxHost) class that launches a persistent context, injects banner and request interception (allowlist/blocklist), and exposes `new_tab()`.
    - New `TabComputer` class that receives a Page from the host and implements Computer over that Page.
  - Auth check remains context/page-based (`is_authenticated()`), callable from TabComputer’s `current_state()`.

- src/gemini_supply/agent.py (BrowserAgent)
  - Add optional `client: genai.Client | None` injection; if absent, create lazily.
  - Make `get_model_response()` non-blocking: wrap sync SDK call using `await asyncio.to_thread(self._client.models.generate_content, ...)`.
  - Optional: accept `img_enabled` flag to suppress inline screenshots when concurrency > 1.

- src/gemini_supply/grocery_main.py
  - Add `--concurrency N` (default 1).
  - Create one BrowserHost per run; inside an `asyncio.TaskGroup`, acquire up to N tabs (`host.new_tab()`), and run `_shop_single_item(...)` per tab.
  - Ensure cleanup: close each TabComputer after its item; close the Host at run end.
  - YAML provider: either force `--concurrency 1` or add a file lock around writes.

## Detailed Steps

1) Introduce BrowserHost and TabComputer
   - File: `src/gemini_supply/computers/browser_host.py`
   - BrowserHost.__aenter__:
     - Start Playwright, `firefox.launch_persistent_context` using Camoufox binary and profile.
     - Add init scripts (banner); install request routing if `enforce_restrictions`.
   - BrowserHost.new_tab():
     - `page = context.new_page()`; navigate to `initial_url`.
     - Return a `TabComputer(page, screen_size, highlight_mouse, host_ref)`.
   - BrowserHost.__aexit__: close context, browser, playwright.
   - TabComputer: copy the action methods from PlaywrightComputer, but operate on `self._page` provided by host. Keep screenshot logic and `highlight_mouse` per-tab.
   - TabComputer.current_state(): call host’s `is_authenticated(page)`; raise `AuthExpiredError` on failure.

2) Remove single-tab interception
   - Delete `_handle_new_page` and associated hooks in `playwright_computer.py` and `camoufox_browser.py`.
   - metro.ca does not open new tabs; we rely on per-tab isolation instead.

3) Orchestrator concurrency
   - Add CLI flag: `--concurrency N` in `src/gemini_supply/main.py`; plumb to `run_shopping`.
   - In `run_shopping`:
     - `async with BrowserHost(...) as host:`
     - Use `asyncio.Semaphore(N)` and `asyncio.TaskGroup()` to fan out items.
     - Each task:
       - `tab = await host.new_tab()`
       - `agent = BrowserAgent(browser_computer=tab, ...)`
       - Run the loop; ensure `tab.close()` in finally.
   - Disable inline screenshots by default when `N>1` via env or a flag (or render to per-item logs).

4) Gemini integration
   - Update `BrowserAgent.get_model_response` to use `asyncio.to_thread` for the sync SDK.
   - Add optional shared `genai.Client` injection so all agents reuse one client.
   - Optional: a process-wide `asyncio.Semaphore` to cap concurrent `generate_content` calls.

5) Provider safety
   - HomeAssistant provider: no special handling; safe to run in parallel.
   - YAML provider: if parallel, add a file lock around `_write`; otherwise force `--concurrency 1` when YAML provider is active.

6) Cleanup and lifecycle
   - Ensure `TabComputer.__aexit__/close` closes its Page only.
   - Ensure Host waits for child tabs to close and then shuts down.

## Testing Plan

- Unit-style:
  - TabComputer actions operate only on its Page (mock Page to assert calls).
  - Host `new_tab()` returns distinct pages; closing a tab doesn’t affect others.
  - Remove-interception change: verify no auto-close of pages on `context.on("page")`.

- Integration:
  - Launch Host; create 2–3 tabs; navigate each to different SRPs; run a minimal agent step; ensure URLs/screenshots don’t cross.
  - Parallel run with `--concurrency 3` against a small list; verify throughput and independent success/failure accounting.
  - HA provider: summary notification created once; YAML provider: locking works or concurrency forced to 1.

## Risks and Mitigations

- Memory/CPU: multiple FF tabs raise resource usage. Mitigate with `--concurrency` default 2–3 and headless option.
- Auth DOM hook drift: if `#authenticatedButton` changes, update selector. Keep failure explicit.
- Gemini QPS/latency: gate parallel `generate_content` calls with a semaphore; keep backoff.
- YAML write races: add file lock or restrict concurrency.

## Rollout Steps

1. Land BrowserHost/TabComputer and refactor orchestrator to single-host/one-tab per item (keep `--concurrency 1` default).
2. Remove interception hooks from PlaywrightComputer/Camoufox code.
3. Make BrowserAgent model calls non-blocking (`to_thread`); optionally inject shared client.
4. Add CLI `--concurrency` and disable inline screenshots by default when N>1.
5. Add YAML locking or enforce `--concurrency 1` with YAML.
6. Test small parallel runs; then increase default concurrency if stable.

## Follow-ups (Optional)

- Tab recycling/pooling to reduce create/destroy overhead.
- Per-item log capture for screenshots when parallel.
- Configurable rate limits for Gemini calls.

