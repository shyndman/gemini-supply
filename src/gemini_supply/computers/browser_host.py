from __future__ import annotations

import asyncio
import os
from pathlib import Path
from types import TracebackType
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Any, Awaitable, Literal, Protocol, TypedDict, Unpack, cast

import playwright.async_api
import termcolor
from camoufox.utils import launch_options as camoufox_launch_options
from playwright.async_api import async_playwright

if TYPE_CHECKING:
  from playwright.async_api import BrowserContext, Playwright

  class _CamoufoxLaunchKwargs(TypedDict, total=False):
    debug: bool | None

  class _AsyncCamoufoxNewBrowserFn(Protocol):
    def __call__(
      self,
      playwright: Playwright,
      *,
      from_options: dict[str, Any] | None = None,
      persistent_context: Literal[True],
      headless: bool | None = None,
      **kwargs: Unpack[_CamoufoxLaunchKwargs],
    ) -> Awaitable[BrowserContext]: ...

  _async_camoufox_new_browser: _AsyncCamoufoxNewBrowserFn
else:
  from camoufox.async_api import AsyncNewBrowser as _async_camoufox_new_browser

from .computer import Computer, EnvState, ScreenSize
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
    disable_sandbox: bool | None = None,
    browser: Literal["firefox", "chromium"] | None = None,
    camoufox_options: dict[str, Any] | None = None,
  ) -> None:
    self._initial_url = initial_url
    self._search_engine_url = search_engine_url
    self._highlight_mouse = highlight_mouse
    self._enforce_restrictions = enforce_restrictions
    self._executable_path = executable_path
    self._user_data_dir = user_data_dir
    self._headless = headless

    env_disable = os.environ.get("CAMOUFOX_DISABLE_SANDBOX", "").strip().lower()
    self._disable_sandbox = (
      disable_sandbox if disable_sandbox is not None else env_disable in ("1", "true", "yes", "on")
    )

    if isinstance(screen_size, ScreenSize):
      self._screen_size = screen_size
    else:
      self._screen_size = ScreenSize(*screen_size)

    env_browser = os.environ.get("CAMOUFOX_BROWSER", "").strip().lower()
    resolved_browser = browser or (
      env_browser if env_browser in {"firefox", "chromium"} else "firefox"
    )
    self._browser_type: Literal["firefox", "chromium"] = (
      "chromium" if resolved_browser == "chromium" else "firefox"
    )

    # Runtime-managed Playwright objects
    self._playwright: playwright.async_api.Playwright | None = None
    self._context: playwright.async_api.BrowserContext | None = None
    self._browser: playwright.async_api.Browser | None = None
    self._initial_page_claimed = False

    # Optional Camoufox launch overrides
    self._camoufox_options = camoufox_options.copy() if camoufox_options else None

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

  @property
  def context(self) -> playwright.async_api.BrowserContext:
    ctx = self._context
    if ctx is None:
      raise RuntimeError("Camoufox host is not running.")
    return ctx

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

      if self._camoufox_options is not None:
        termcolor.cprint("Launching with Camoufox options (persistent context)...", color="cyan")
        context = await self._launch_with_camoufox_options(headless=headless)
        self._context = context
        # Browser may be None for persistent contexts; rely on context.
        self._browser = context.browser
      else:
        launch_args: list[str] = []
        launch_env: dict[str, str] | None = None
        if self._disable_sandbox:
          runtime_dir = self._user_data_dir / ".runtime"
          runtime_dir.mkdir(parents=True, exist_ok=True)
          launch_args.extend(
            ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
          )
          launch_env = {
            "MOZ_DISABLE_CONTENT_SANDBOX": "1",
            "MOZ_DISABLE_GMP_SANDBOX": "1",
            "MOZ_DISABLE_RDD_SANDBOX": "1",
            "XDG_RUNTIME_DIR": str(runtime_dir),
          }

        browser_launcher = getattr(p, self._browser_type)
        context = await browser_launcher.launch_persistent_context(
          user_data_dir=str(self._user_data_dir),
          executable_path=str(self._executable_path) if self._executable_path else None,
          headless=headless,
          viewport={"width": self._screen_size.width, "height": self._screen_size.height},
          args=launch_args or None,
          env=launch_env,
        )
        self._context = context
        # Browser may be None for persistent contexts; rely on context.
        self._browser = context.browser
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

  async def _launch_with_camoufox_options(
    self, *, headless: bool
  ) -> playwright.async_api.BrowserContext:
    if self._browser_type != "firefox":
      raise RuntimeError("Camoufox launch options require the Firefox browser type.")
    assert self._playwright is not None
    loop = asyncio.get_running_loop()
    launch_kwargs = self._camoufox_options.copy() if self._camoufox_options else {}
    if "config" in launch_kwargs and isinstance(launch_kwargs["config"], dict):
      launch_kwargs["config"] = launch_kwargs["config"].copy()
    exe_path = str(self._executable_path) if self._executable_path else None
    options = await loop.run_in_executor(
      None,
      lambda: camoufox_launch_options(
        headless=headless,
        executable_path=exe_path,
        **launch_kwargs,
      ),
    )
    termcolor.cprint(f"Camoufox executable: {exe_path or '<default>'}", color="yellow")
    options["user_data_dir"] = str(self._user_data_dir)
    options.setdefault(
      "viewport",
      {"width": self._screen_size.width, "height": self._screen_size.height},
    )
    if self._disable_sandbox:
      runtime_dir = self._user_data_dir / ".runtime"
      runtime_dir.mkdir(parents=True, exist_ok=True)
      args = list(options.get("args") or [])
      args.extend(["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"])
      options["args"] = args
      env = dict(options.get("env") or {})
      env.update(
        {
          "MOZ_DISABLE_CONTENT_SANDBOX": "1",
          "MOZ_DISABLE_GMP_SANDBOX": "1",
          "MOZ_DISABLE_RDD_SANDBOX": "1",
          "XDG_RUNTIME_DIR": str(runtime_dir),
        }
      )
      options["env"] = env
    context = await _async_camoufox_new_browser(
      self._playwright,
      from_options=options,
      persistent_context=True,
      headless=headless,
    )
    return cast(playwright.async_api.BrowserContext, context)

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

  async def _acquire_page(self) -> playwright.async_api.Page:
    c = self.context
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
    return page

  async def new_page(self) -> playwright.async_api.Page:
    return await self._acquire_page()

  async def new_tab(self) -> "CamoufoxTab":
    page = await self._acquire_page()
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
    for key in keys:
      mapping = PLAYWRIGHT_KEY_MAP.get(key, key)
      await self._page.keyboard.down(mapping)
    for key in reversed(keys):
      mapping = PLAYWRIGHT_KEY_MAP.get(key, key)
      await self._page.keyboard.up(mapping)
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    await self._page.mouse.move(x, y)
    await self._page.mouse.down()
    await self.highlight_mouse(destination_x, destination_y)
    await self._page.mouse.move(destination_x, destination_y)
    await self._page.mouse.up()
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def current_state(self) -> EnvState:
    url = self._page.url
    screenshot = await self._page.screenshot(full_page=True)
    return EnvState(url=url, screenshot=screenshot)

  async def highlight_mouse(self, x: int, y: int) -> None:
    if not self._highlight_mouse:
      return
    await self._page.evaluate(
      """([mouseX, mouseY]) => {
        let el = document.getElementById('__mouse-highlight');
        if (!el) {
          el = document.createElement('div');
          el.id = '__mouse-highlight';
          el.style.cssText = 'position:fixed;width:18px;height:18px;border-radius:9px;background:#f97316;opacity:0.9;pointer-events:none;z-index:2147483647;transform:translate(-9px,-9px);transition:transform 80ms ease-out;';
          document.body.append(el);
        }
        el.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-9px, -9px)`;
      }""",
      [x, y],
    )


__all__ = ["CamoufoxHost", "CamoufoxTab"]
