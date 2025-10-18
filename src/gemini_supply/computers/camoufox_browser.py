from __future__ import annotations

import os
from types import TracebackType
from typing import TypedDict
from urllib.parse import urlparse

import playwright.async_api
import termcolor
from playwright.async_api import async_playwright

from .computer import EnvState
from .playwright_computer import PlaywrightComputer


class AuthExpiredError(Exception):
  pass


class CamoufoxMetroBrowser(PlaywrightComputer):
  """Playwright Firefox browser tailored for metro.ca with auth and restrictions.

  Uses a Camoufox executable (a hardened Firefox build) to reduce automation detection.
  - Loads/saves storage state for persistent authentication when not launching persistent
  - Optionally launches a persistent context bound to a user data dir
  - Enforces domain allowlist and URL blocklist during shopping sessions
  - Injects a status banner and hooks SPA route changes
  - Performs DOM-based authentication checks
  """

  def __init__(
    self,
    *,
    screen_size: tuple[int, int],
    storage_state_path: str,
    initial_url: str = "https://www.metro.ca",
    highlight_mouse: bool = False,
    enforce_restrictions: bool = True,
    executable_path: str | None = None,
    user_data_dir: str | None = None,
  ) -> None:
    super().__init__(
      screen_size=screen_size,
      initial_url=initial_url,
      search_engine_url="https://www.metro.ca/en/online-grocery/search",
      highlight_mouse=highlight_mouse,
    )
    self._storage_state_path = storage_state_path
    self._enforce_restrictions = enforce_restrictions
    self._executable_path = executable_path
    self._user_data_dir = user_data_dir
    self._allow_domains: set[str] = {
      "www.metro.ca",
      "product-images.metro.ca",
      "d94qwxh6czci4.cloudfront.net",
      "static.cloud.coveo.com",
      "use.typekit.net",
      "p.typekit.net",
      "cdn.cookielaw.org",
      "cdn.dialoginsight.com",
    }
    self._blocked_paths: tuple[str, ...] = (
      "/checkout",
      "/payment",
      "/billing",
      "/login",
      "/logout",
      "/signup",
      "/register",
      "/account/settings",
      "/account/edit",
      "/password",
      "/password-reset",
    )

  async def __aenter__(self) -> "CamoufoxMetroBrowser":
    termcolor.cprint("Creating Camoufox metro browser session...", color="cyan")
    self._playwright = await async_playwright().start()
    assert self._playwright is not None
    p = self._playwright

    if self._user_data_dir is not None:
      # Launch a persistent Firefox context using Camoufox binary
      self._context = await p.firefox.launch_persistent_context(
        user_data_dir=self._user_data_dir,
        executable_path=self._executable_path,
        headless=bool(os.environ.get("PLAYWRIGHT_HEADLESS", False)),
        viewport={"width": self._screen_size[0], "height": self._screen_size[1]},
      )
      self._browser = self._context.browser
    else:
      # Standard ephemeral context; we will load/save storage state
      self._browser = await p.firefox.launch(
        executable_path=self._executable_path,
        headless=bool(os.environ.get("PLAYWRIGHT_HEADLESS", False)),
      )
      storage_state = self._storage_state_path if os.path.exists(self._storage_state_path) else None

      class _ViewportKw(TypedDict):
        width: int
        height: int

      class _ContextKwargs(TypedDict, total=False):
        viewport: _ViewportKw
        storage_state: str

      context_kwargs: _ContextKwargs = _ContextKwargs(
        viewport=_ViewportKw(width=self._screen_size[0], height=self._screen_size[1])
      )
      if storage_state is not None:
        context_kwargs["storage_state"] = storage_state
      assert self._browser is not None
      self._context = await self._browser.new_context(**context_kwargs)  # type: ignore[arg-type]

    # Inject status banner and history hooks on every document load.
    assert self._context is not None
    c = self._context
    assert c is not None
    await c.add_init_script(self._banner_script())

    # Intercept requests for allow/block enforcement (disabled in relaxed mode, e.g., auth setup).
    if self._enforce_restrictions:
      await c.route("**/*", self._route_interceptor)

    self._page = await c.new_page()
    await self._page.goto(self._initial_url)
    c.on("page", self._handle_new_page)

    termcolor.cprint("Camoufox metro browser ready.", color="green")
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    # Persist updated storage state if possible (both ephemeral and persistent contexts).
    try:
      c = self._context
      assert c is not None
      await c.storage_state(path=self._storage_state_path)
    except Exception:  # noqa: BLE001 - best effort
      pass
    await super().__aexit__(exc_type, exc_val, exc_tb)

  async def current_state(self) -> EnvState:
    state = await super().current_state()
    if not await self.is_authenticated():
      raise AuthExpiredError("Authentication expired or missing — login required")
    return state

  async def is_authenticated(self) -> bool:
    try:
      # Presence of #authenticatedButton implies a valid logged-in session
      page = self._page
      assert page is not None
      el = await page.query_selector("#authenticatedButton")
      return el is not None
    except Exception:  # noqa: BLE001
      return False

  async def _route_interceptor(self, route: playwright.async_api.Route) -> None:
    url = route.request.url
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path

    # Block known sensitive paths
    if any(path.startswith(p) for p in self._blocked_paths):
      termcolor.cprint(f"Blocked sensitive path: {url}", color="yellow")
      await route.abort()
      return

    # Enforce allowlist
    if host not in self._allow_domains:
      termcolor.cprint(f"Blocked non-allowed host: {host}", color="yellow")
      await route.abort()
      return

    await route.continue_()

  def _banner_script(self) -> str:
    # No confirmation dialogs; simple status banner and SPA route hooks
    return (
      "(() => {\n"
      "  if (window.__groceryAgentInjected) return;\n"
      "  window.__groceryAgentInjected = true;\n"
      "  const id = 'grocery-agent-status-banner';\n"
      "  const update = (text) => {\n"
      "    let el = document.getElementById(id);\n"
      "    if (!el) {\n"
      "      el = document.createElement('div');\n"
      "      el.id = id;\n"
      "      el.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;padding:6px 10px;background:linear-gradient(90deg,#3b82f6,#06b6d4);color:white;font:600 12px system-ui;letter-spacing:.3px;';\n"
      "      document.body.prepend(el);\n"
      "      document.body.style.paddingTop = '28px';\n"
      "    }\n"
      "    el.textContent = text;\n"
      "  };\n"
      "  window.setCurrentShoppingItem = (name) => { update(`🤖 Grocery Agent Active — ${name}`); };\n"
      "  const _push = history.pushState;\n"
      "  const _replace = history.replaceState;\n"
      "  history.pushState = function(...args) { const r = _push.apply(this,args); window.dispatchEvent(new Event('grocery:spa')); return r; }\n"
      "  history.replaceState = function(...args) { const r = _replace.apply(this,args); window.dispatchEvent(new Event('grocery:spa')); return r; }\n"
      "  window.addEventListener('popstate', () => window.dispatchEvent(new Event('grocery:spa')));\n"
      "  window.addEventListener('grocery:spa', () => { /* could re-run checks if needed */ });\n"
      "})();"
    )
