from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from pprint import pformat
from types import TracebackType
from typing import (
  Any,
  AsyncIterator,
  Awaitable,
  Literal,
  NotRequired,
  TypedDict,
  cast,
)
from urllib.parse import urlparse

import playwright.async_api
from camoufox.async_api import AsyncNewBrowser  # type: ignore
from camoufox.utils import launch_options as camoufox_launch_options
from playwright.async_api import async_playwright

from generative_supply.term import activity_log

from .agent_managed_page import AgentManagedPage
from .computer import ScreenSize


class CamoufoxLaunchOptions(TypedDict):
  """Typed options for Camoufox browser launch configuration.

  Based on camoufox.launch_options() signature. All fields are optional.
  See: https://github.com/daijro/camoufox
  """

  # Humanization settings
  humanize: NotRequired[bool | float]  # Humanize cursor movement (True or max duration in seconds)
  config: NotRequired[
    dict[str, Any]
  ]  # Camoufox-specific properties (e.g., humanize:maxTime, showcursor)

  # Addons and extensions
  addons: NotRequired[list[str]]  # Firefox addon paths (e.g., CAPTCHA solver for authentication)

  # Evaluation and security
  main_world_eval: NotRequired[
    bool
  ]  # Enable scripts in main world (prepend "mw:" to evaluate calls)
  i_know_what_im_doing: NotRequired[bool]  # Bypass safety warnings
  disable_coop: NotRequired[
    bool
  ]  # Disable Cross-Origin-Opener-Policy for cross-origin iframe interaction


def build_camoufox_options() -> CamoufoxLaunchOptions:
  """Build default Camoufox launch options for metro.ca automation.

  Returns:
    Configured options including:
    - Humanized cursor movement (for appearing more natural)
    - CAPTCHA solver addon (required for metro.ca authentication)
    - Main world evaluation (for advanced script injection)
    - COOP disabled (for cross-origin iframe interaction)
  """

  return {
    "humanize": True,
    "config": {
      "humanize:maxTime": 0.9,
      "humanize:minTime": 0.6,
      "showcursor": True,
      "forceScopeAccess": True,
    },
    "main_world_eval": True,
    "i_know_what_im_doing": True,
    "disable_coop": True,  # Required for cross-origin iframe elements (necessary)
  }


class CamoufoxHost:
  """Single persistent Camoufox/Firefox context that can spawn pages.

  - Uses a hardened Firefox (Camoufox) binary
  - Persistent profile via `user_data_dir`
  - Enforces allowlist/blocklist when `enforce_restrictions=True`
  - Injects status banner via init script
  - Provides `new_agent_managed_page()` to create Computer-wrapped pages for agents
  - Provides `new_page()` to create raw Playwright pages for utilities (e.g., auth)
  """

  def __init__(
    self,
    *,
    screen_size: ScreenSize,
    user_data_dir: Path,
    initial_url: str = "https://www.metro.ca",
    init_scripts: list[str] = [],
    pre_iteration_delegate: Callable[[playwright.async_api.Page], Awaitable[None]] | None = None,
    highlight_mouse: bool = False,
    enforce_restrictions: bool = True,
    executable_path: Path | None = None,
    camoufox_options: CamoufoxLaunchOptions | None = None,
    window_position: tuple[int, int] | None = None,
  ) -> None:
    self._initial_url = initial_url
    self._init_scripts = init_scripts
    self._pre_iteration_delegate = pre_iteration_delegate
    self._highlight_mouse = highlight_mouse
    self._enforce_restrictions = enforce_restrictions
    self._executable_path = executable_path
    self._user_data_dir = user_data_dir

    self._screen_size = screen_size
    self._window_position = window_position

    # Runtime-managed Playwright objects
    self._playwright: playwright.async_api.Playwright | None = None
    self._context: playwright.async_api.BrowserContext | None = None
    self._restrictions_active = False

    # Camoufox launch options (use default if not provided)
    self._camoufox_options = (
      camoufox_options.copy() if camoufox_options else build_camoufox_options()
    )

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
    raise NotImplementedError("CamoufoxHost does not implement search_engine_url property.")

  @property
  def highlight_mouse(self) -> bool:
    return self._highlight_mouse

  @property
  def context(self) -> playwright.async_api.BrowserContext:
    ctx = self._context
    if ctx is None:
      raise RuntimeError("Camoufox host is not running.")
    return ctx

  def _resolve_headless_mode(self) -> bool | Literal["virtual"]:
    """Resolve headless mode from PLAYWRIGHT_HEADLESS env var."""
    env_val = os.environ.get("PLAYWRIGHT_HEADLESS", "").strip().lower()
    if env_val in ("virtual", "v"):
      return "virtual"
    elif env_val in ("0", "false", "no"):
      return False
    else:
      return True

  async def _prepare_launch_options(self, *, headless: bool | Literal["virtual"]) -> dict[str, Any]:
    """Build Camoufox launch options dict before browser launch."""
    loop = asyncio.get_running_loop()
    launch_kwargs = cast(dict[str, Any], self._camoufox_options.copy())
    if "config" in launch_kwargs and isinstance(launch_kwargs["config"], dict):
      launch_kwargs["config"] = launch_kwargs["config"].copy()
    launch_kwargs.pop("headless", None)
    if self._window_position is not None:
      config = cast(dict[str, Any], launch_kwargs.setdefault("config", {}))
      window_x, window_y = self._window_position
      config["window.screenX"] = window_x
      config["window.screenY"] = window_y
      config["screen.availLeft"] = window_x
      config["screen.availTop"] = window_y

    exe_path = str(self._executable_path) if self._executable_path else None
    camoufox_headless = headless if isinstance(headless, bool) else False
    options = await loop.run_in_executor(
      None,
      lambda: camoufox_launch_options(
        executable_path=exe_path,
        headless=camoufox_headless,
        window=(self._screen_size.width, self._screen_size.height),
        **launch_kwargs,
      ),
    )
    options["user_data_dir"] = str(self._user_data_dir)

    return options

  async def _initialize_context(self, context: playwright.async_api.BrowserContext) -> None:
    """Set up banner script and route restrictions on the browser context."""
    for script in self._init_scripts:
      await context.add_init_script(script)

    if self._enforce_restrictions:
      await context.route("**/*", self._route_interceptor)
      self._restrictions_active = True
    else:
      self._restrictions_active = False

  async def __aenter__(self) -> "CamoufoxHost":
    activity_log().operation("Creating Camoufox host (persistent context)...")
    self._playwright = await async_playwright().start()
    assert self._playwright is not None

    try:
      headless = self._resolve_headless_mode()
      activity_log().operation("Launching with Camoufox options (persistent context)...")
      context = await self._launch_with_camoufox_options(headless=headless)
      self._context = context
    except Exception as e:  # noqa: BLE001
      raise RuntimeError(
        f"Failed to launch Camoufox persistent context with profile '{self._user_data_dir}': {e}"
      ) from e

    assert self._context is not None
    await self._initialize_context(self._context)
    activity_log().success("Camoufox host ready.")
    return self

  async def _launch_with_camoufox_options(
    self, *, headless: bool | Literal["virtual"]
  ) -> playwright.async_api.BrowserContext:
    """Launch Camoufox browser with configured options."""
    assert self._playwright is not None
    options = await self._prepare_launch_options(headless=headless)
    activity_log().warning("Camoufox launch configuration:")
    activity_log().warning(pformat(options, sort_dicts=False))

    context = await AsyncNewBrowser(
      self._playwright,
      from_options=options,
      persistent_context=True,
      headless=headless,
    )
    return context

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
    if self._playwright is not None:
      try:
        await self._playwright.stop()
      except Exception:
        pass
      finally:
        self._playwright = None

  async def _acquire_page(self) -> playwright.async_api.Page:
    c = self.context
    page = await c.new_page()
    await page.goto(self._initial_url)
    return page

  async def new_page(self) -> playwright.async_api.Page:
    return await self._acquire_page()

  async def new_agent_managed_page(self) -> AgentManagedPage:
    page = await self._acquire_page()
    return AgentManagedPage(
      page=page,
      screen_size=self._screen_size,
      is_authenticated_delegate=self.is_authenticated,
      pre_iteration_delegate=self._pre_iteration_delegate,
      highlight_mouse=self._highlight_mouse,
    )

  async def is_authenticated(self, page: playwright.async_api.Page, timeout: int = 3000) -> bool:
    return (await page.wait_for_selector(".authenticatedButton", timeout=timeout)) is not None

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

  @asynccontextmanager
  async def unrestricted(self) -> AsyncIterator[None]:
    if not self._enforce_restrictions or not self._restrictions_active:
      activity_log().unrestricted.warning(
        "Restrictions not enforced or already inactive; skipping unroute."
      )
      yield
      return
    context = self.context
    activity_log().unrestricted.operation("Removing route restrictions.")
    await context.unroute("**/*", self._route_interceptor)
    self._restrictions_active = False
    activity_log().unrestricted.success("Restrictions removed; proceeding unrestricted.")
    try:
      yield
    finally:
      try:
        activity_log().unrestricted.operation("Re-enabling route restrictions.")
        await context.route("**/*", self._route_interceptor)
        activity_log().unrestricted.success("Restrictions re-enabled.")
      finally:
        self._restrictions_active = True
