from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType
from urllib.parse import urlparse
from typing import Literal

import playwright.async_api
import termcolor
from playwright.async_api import async_playwright

from .computer import Computer, EnvState, ScreenSize
from .errors import AuthExpiredError
from .keys import PLAYWRIGHT_KEY_MAP


class CamoufoxHost:
  """Single persistent Camoufox/Firefox context that can spawn per-tab Computers.

  - Uses a hardened Firefox (Camoufox) binary
  - Persistent profile via `user_data_dir`
  - Enforces allowlist/blocklist when `enforce_restrictions=True`
  - Injects status banner via init script
  - Provides `new_tab()` to create an isolated TabComputer per agent
  """

  def __init__(
    self,
    *,
    screen_size: ScreenSize | tuple[int, int],
    user_data_dir: Path,
    initial_url: str = "https://www.metro.ca",
    search_engine_url: str = "https://www.metro.ca/en/online-grocery/search",
    highlight_mouse: bool = False,
    enforce_restrictions: bool = True,
    executable_path: Path | None = None,
    headless: bool | None = None,
  ) -> None:
    self._initial_url = initial_url
    self._search_engine_url = search_engine_url
    self._highlight_mouse = highlight_mouse
    self._enforce_restrictions = enforce_restrictions
    self._executable_path = executable_path
    self._user_data_dir = user_data_dir
    self._headless = headless
    if isinstance(screen_size, ScreenSize):
      self._screen_size = screen_size
    else:
      self._screen_size = ScreenSize(*screen_size)

    # Runtime-managed Playwright objects
    self._playwright: playwright.async_api.Playwright | None = None
    self._context: playwright.async_api.BrowserContext | None = None
    self._browser: playwright.async_api.Browser | None = None
    self._initial_page_claimed = False

    # Shared restrictions
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

  @property
  def screen_size(self) -> ScreenSize:
    return self._screen_size

  @property
  def search_engine_url(self) -> str:
    return self._search_engine_url

  @property
  def highlight_mouse(self) -> bool:
    return self._highlight_mouse

  async def __aenter__(self) -> "CamoufoxHost":
    termcolor.cprint("Creating Camoufox host (persistent context)...", color="cyan")
    self._playwright = await async_playwright().start()
    assert self._playwright is not None
    p = self._playwright

    try:
      # Headless: prefer explicit flag, else env var PLAYWRIGHT_HEADLESS
      env_val = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()
      if self._headless is None:
        headless = env_val not in ("0", "false", "no") and bool(env_val or True)
      else:
        headless = self._headless

      self._context = await p.firefox.launch_persistent_context(
        user_data_dir=str(self._user_data_dir),
        executable_path=str(self._executable_path) if self._executable_path else None,
        headless=headless,
        viewport={"width": self._screen_size.width, "height": self._screen_size.height},
      )
      self._browser = self._context.browser
    except Exception as e:  # noqa: BLE001
      raise RuntimeError(
        f"Failed to launch Camoufox persistent context with profile '{self._user_data_dir}': {e}"
      ) from e

    assert self._context is not None
    c = self._context
    await c.add_init_script(self._banner_script())
    if self._enforce_restrictions:
      await c.route("**/*", self._route_interceptor)

    termcolor.cprint("Camoufox host ready.", color="green")
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    # Close context then Playwright
    if self._context is not None:
      try:
        await self._context.close()
      except Exception:
        pass
      finally:
        self._context = None
        self._browser = None
    if self._playwright is not None:
      try:
        await self._playwright.stop()
      except Exception:
        pass
      finally:
        self._playwright = None

  async def new_tab(self) -> "CamoufoxTab":
    c = self._context
    assert c is not None
    page: playwright.async_api.Page
    # Reuse the first existing page created by the persistent context to avoid
    # spawning an extra blank window, which Firefox may do on startup.
    if not self._initial_page_claimed and c.pages:
      page = c.pages[0]
      self._initial_page_claimed = True
      # Always navigate to the initial URL to normalize state.
      await page.goto(self._initial_url)
    else:
      page = await c.new_page()
      await page.goto(self._initial_url)
    return CamoufoxTab(
      page=page,
      screen_size=self._screen_size,
      search_engine_url=self._search_engine_url,
      host=self,
      highlight_mouse=self._highlight_mouse,
    )

  async def is_authenticated(self, page: playwright.async_api.Page) -> bool:
    try:
      el = await page.query_selector("#authenticatedButton")
      return el is not None
    except Exception:  # noqa: BLE001
      return False

  async def _route_interceptor(self, route: playwright.async_api.Route) -> None:
    url = route.request.url
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path

    if any(path.startswith(p) for p in self._blocked_paths):
      await route.abort()
      return

    if host not in self._allow_domains:
      await route.abort()
      return

    await route.continue_()

  def _banner_script(self) -> str:
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
      "})();"
    )


class CamoufoxTab(Computer):
  """A tab-scoped Computer implementation backed by a single Page."""

  def __init__(
    self,
    *,
    page: playwright.async_api.Page,
    screen_size: ScreenSize,
    search_engine_url: str,
    host: CamoufoxHost,
    highlight_mouse: bool = False,
  ) -> None:
    self._page = page
    self._screen_size = screen_size
    self._search_engine_url = search_engine_url
    self._host = host
    self._highlight_mouse = highlight_mouse

  async def __aenter__(self) -> "CamoufoxTab":
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    await self.close()

  async def close(self) -> None:
    try:
      await self._page.close()
    except Exception:
      pass

  # Computer methods
  def screen_size(self) -> ScreenSize:
    viewport = self._page.viewport_size
    if viewport:
      return ScreenSize(viewport["width"], viewport["height"])
    return self._screen_size

  async def open_web_browser(self) -> EnvState:
    return await self.current_state()

  async def click_at(self, x: int, y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.click(x, y)
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def hover_at(self, x: int, y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.move(x, y)
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def type_text_at(
    self,
    x: int,
    y: int,
    text: str,
    press_enter: bool,
    clear_before_typing: bool,
  ) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.click(x, y)
    await self._page.wait_for_load_state()
    if clear_before_typing:
      # Cmd/Ctrl+A then Delete
      import sys

      if os.name == "posix" and sys.platform == "darwin":
        await self.key_combination(["Command", "A"])
      else:
        await self.key_combination(["Control", "A"])
      await self.key_combination(["Delete"])
    await self._page.keyboard.type(text)
    await self._page.wait_for_load_state()
    if press_enter:
      await self.key_combination(["Enter"])
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def scroll_document(self, direction: Literal["up", "down", "left", "right"]) -> EnvState:
    if direction == "down":
      return await self.key_combination(["PageDown"])
    elif direction == "up":
      return await self.key_combination(["PageUp"])
    elif direction in ("left", "right"):
      # Horizontal scroll by 50% of viewport
      horizontal_scroll_amount = self.screen_size().width // 2
      sign = "-" if direction == "left" else ""
      await self._page.evaluate(f"window.scrollBy({sign}{horizontal_scroll_amount}, 0);")
      await self._page.wait_for_load_state()
      return await self.current_state()
    else:
      raise ValueError("Unsupported direction: ", direction)

  async def scroll_at(
    self,
    x: int,
    y: int,
    direction: Literal["up", "down", "left", "right"],
    magnitude: int,
  ) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.move(x, y)
    await self._page.wait_for_load_state()
    dx = 0
    dy = 0
    if direction == "up":
      dy = -magnitude
    elif direction == "down":
      dy = magnitude
    elif direction == "left":
      dx = -magnitude
    elif direction == "right":
      dx = magnitude
    else:
      raise ValueError("Unsupported direction: ", direction)
    await self._page.mouse.wheel(dx, dy)
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def wait_5_seconds(self) -> EnvState:
    import asyncio

    await asyncio.sleep(5)
    return await self.current_state()

  async def go_back(self) -> EnvState:
    await self._page.go_back()
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def go_forward(self) -> EnvState:
    await self._page.go_forward()
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def search(self) -> EnvState:
    return await self.navigate(self._host.search_engine_url)

  async def navigate(self, url: str) -> EnvState:
    normalized_url = url
    if not normalized_url.startswith(("http://", "https://")):
      normalized_url = "https://" + normalized_url
    await self._page.goto(normalized_url)
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def key_combination(self, keys: list[str]) -> EnvState:
    # Normalize keys to Playwright map
    keys = [PLAYWRIGHT_KEY_MAP.get(k.lower(), k) for k in keys]
    for key in keys[:-1]:
      await self._page.keyboard.down(key)
    await self._page.keyboard.press(keys[-1])
    for key in reversed(keys[:-1]):
      await self._page.keyboard.up(key)
    return await self.current_state()

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.move(x, y)
    await self._page.wait_for_load_state()
    await self._page.mouse.down()
    await self._page.wait_for_load_state()
    await self.highlight_mouse(destination_x, destination_y)
    await self._page.mouse.move(destination_x, destination_y)
    await self._page.wait_for_load_state()
    await self._page.mouse.up()
    return await self.current_state()

  async def current_state(self) -> EnvState:
    import asyncio

    await self._page.wait_for_load_state()
    await asyncio.sleep(0.5)
    # Auth check at current page
    if not await self._host.is_authenticated(self._page):
      raise AuthExpiredError("Authentication expired or missing — login required")
    screenshot_bytes = await self._page.screenshot(type="png", full_page=False)
    return EnvState(screenshot=screenshot_bytes, url=self._page.url)

  async def highlight_mouse(self, x: int, y: int) -> None:
    if not self._highlight_mouse:
      return
    await self._page.evaluate(
      f"""
        () => {{
            const element_id = "playwright-feedback-circle";
            let div = document.getElementById(element_id);
            if (!div) {{
              div = document.createElement('div');
              div.id = element_id;
              div.style.pointerEvents = 'none';
              div.style.border = '4px solid red';
              div.style.borderRadius = '50%';
              div.style.width = '20px';
              div.style.height = '20px';
              div.style.position = 'fixed';
              div.style.zIndex = '9999';
              document.body.appendChild(div);
            }}

            div.hidden = false;
            div.style.left = {x} - 10 + 'px';
            div.style.top = {y} - 10 + 'px';

            setTimeout(() => {{
                div.hidden = true;
            }}, 2000);
        }}
    """
    )
    import asyncio

    await asyncio.sleep(1)
