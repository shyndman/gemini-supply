from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Sequence, TypeAlias

import termcolor
from playwright.async_api import ElementHandle, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType

from gemini_supply.computers import CamoufoxHost

SHORT_FENCE_WAIT_MS = 1000

AuthFlow: TypeAlias = Callable[[CamoufoxHost], Awaitable[None]]
SHORT_FENCE_TYPE = CaptchaType.CLOUDFLARE_TURNSTILE


@dataclass(slots=True)
class AuthCredentials:
  username: str
  password: str


class AuthenticationError(RuntimeError):
  """Raised when automated authentication fails."""


class AuthManager:
  """Coordinates automated authentication with single-flight semantics."""

  def __init__(self, host: CamoufoxHost, auth_flow: AuthFlow | None = None) -> None:
    self._host = host
    self._auth_flow: AuthFlow = auth_flow or _run_default_auth_flow
    # Keep single-flight semantics even when the orchestrator gates pre-shop auth; future
    # reauthentication passes will rely on this to avoid duplicate login attempts.
    self._lock = asyncio.Lock()
    self._last_success: float | None = None

  async def ensure_authenticated(self, *, force: bool = False) -> None:
    if not force and await self._session_is_valid():
      return
    async with self._lock:
      if not force and await self._session_is_valid():
        return
      await self._auth_flow(self._host)
      if not await self._session_is_valid():
        raise AuthenticationError("Authentication flow completed without a valid session.")
      self._last_success = time.monotonic()

  async def _session_is_valid(self) -> bool:
    context_pages = list(self._host.context.pages)
    pages = [page for page in context_pages if not _is_keepalive_page(page)]
    if not pages:
      page = await self._host.new_page()
      try:
        return await _check_session_via_promotions(self._host, page)
      finally:
        await _ensure_keepalive_tab(self._host, preserve=page)

    for page in pages:
      try:
        if await self._host.is_authenticated(page):
          return True
      except Exception:
        continue
    return False


async def _run_default_auth_flow(host: CamoufoxHost) -> None:
  async with _unrestricted_context(host):
    await _perform_login(host)


@asynccontextmanager
async def _unrestricted_context(host: CamoufoxHost) -> AsyncIterator[None]:
  async with host.unrestricted():
    yield


async def _perform_login(host: CamoufoxHost) -> None:
  credentials = _resolve_credentials()
  page = await host.new_page()
  try:
    await page.wait_for_load_state("domcontentloaded")
    await _accept_cookies(page)
    await _open_promotions(page)
    await page.wait_for_load_state()

    if await host.is_authenticated(page):
      termcolor.cprint("[auth] Existing authenticated session detected; skipping login.", "yellow")
      return

    async with ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver:
      await _launch_login_drawer(page)
      await _solve_short_fence(page, solver)
    await _submit_credentials(page, credentials)
    termcolor.cprint("[auth] Submitted credentials; waiting for redirect.", "cyan")
    await page.wait_for_load_state("networkidle")
    final_page = await _wait_for_authenticated_page(host, host.context.pages)
    termcolor.cprint(f"[auth] Authenticated via {final_page.url}", "green")
  finally:
    try:
      await _ensure_keepalive_tab(host, preserve=page)
    except Exception:
      pass


def _resolve_credentials() -> AuthCredentials:
  username = os.environ.get("GEMINI_SUPPLY_METRO_USERNAME", "").strip()
  password = os.environ.get("GEMINI_SUPPLY_METRO_PASSWORD", "").strip()
  if not username or not password:
    raise AuthenticationError(
      "Set GEMINI_SUPPLY_METRO_USERNAME and GEMINI_SUPPLY_METRO_PASSWORD for automated auth."
    )
  return AuthCredentials(username=username, password=password)


async def _check_session_via_promotions(host: CamoufoxHost, page: Page) -> bool:
  try:
    await page.wait_for_load_state("domcontentloaded")
  except AttributeError:
    return await host.is_authenticated(page)

  try:
    await _accept_cookies(page)
    try:
      await _open_promotions(page)
    except PlaywrightTimeout:
      termcolor.cprint("[auth] Promotions link unavailable during session check.", "yellow")
    else:
      await page.wait_for_load_state()
  except AttributeError:
    return await host.is_authenticated(page)
  return await host.is_authenticated(page)


async def _ensure_keepalive_tab(host: CamoufoxHost, *, preserve: Page) -> None:
  context = host.context
  if _page_is_closed(preserve):
    return

  real_pages = [p for p in context.pages if p is not preserve and not _is_keepalive_page(p)]

  if real_pages:
    try:
      await preserve.close()
    except Exception:
      pass
    return

  # Reuse the preserve page as keepalive when it would otherwise be the last tab.
  try:
    await preserve.goto("about:blank#keepalive", wait_until="domcontentloaded")
  except Exception:
    pass


def _is_keepalive_page(page: Page) -> bool:
  try:
    return page.url.startswith("about:blank#keepalive")
  except Exception:
    return False


def _page_is_closed(page: Page) -> bool:
  try:
    return bool(page.is_closed())
  except Exception:
    return False


async def _accept_cookies(page: Page) -> None:
  try:
    await _hover_and_click(page, "#onetrust-accept-btn-handler", timeout=4000)
    termcolor.cprint("[auth] Accepted cookies.", "magenta")
  except PlaywrightTimeout:
    termcolor.cprint("[auth] Cookie banner not present.", "yellow")


async def _open_promotions(page: Page) -> None:
  await _hover_and_click(page, 'a[href="/en/flyer"]')
  await page.wait_for_load_state()


async def _launch_login_drawer(page: Page) -> None:
  termcolor.cprint("[auth] Opening login drawer.", "cyan")
  await _hover_and_click(page, ".login--btn")
  await page.wait_for_selector("#loginSidePanelForm", state="visible", timeout=5000)
  termcolor.cprint("[auth] Triggering login action.", "cyan")
  cta = await page.wait_for_selector(
    "#loginSidePanelForm .cta-basic-primary", state="visible", timeout=5000
  )
  if cta is None:
    raise AuthenticationError("Login button in side panel not found.")
  await _click_center(page, cta)
  await page.wait_for_timeout(300)
  termcolor.cprint("[auth] Waiting for identity redirect.", "cyan")
  try:
    await page.wait_for_function("() => location.href.includes('auth.')", timeout=30000)
  except PlaywrightTimeout:
    termcolor.cprint("[auth] Redirect took longer than expected; waiting for load state.", "yellow")
    await page.wait_for_load_state()


async def _solve_short_fence(page: Page, solver: ClickSolver) -> None:
  termcolor.cprint("[auth] Preparing short fence solver.", "cyan")
  await page.wait_for_timeout(SHORT_FENCE_WAIT_MS)
  await solver.solve_captcha(
    captcha_container=page,
    captcha_type=SHORT_FENCE_TYPE,
  )
  termcolor.cprint("[auth] Short fence cleared.", "green")


async def _submit_credentials(page: Page, credentials: AuthCredentials) -> None:
  user_input = await page.wait_for_selector("#signInName", timeout=15000)
  if user_input is None:
    raise AuthenticationError("Username field not present.")
  await _click_center(page, user_input)
  await page.keyboard.type(credentials.username, delay=80)
  await page.keyboard.press("Tab")

  password_input = await page.wait_for_selector("#password", timeout=5000)
  if password_input is None:
    raise AuthenticationError("Password field not present.")
  await _click_center(page, password_input)
  await page.keyboard.type(credentials.password, delay=90)
  await page.keyboard.press("Enter")


async def _wait_for_authenticated_page(host: CamoufoxHost, pages: Sequence[Page]) -> Page:
  for _ in range(40):
    for candidate in list(pages):
      try:
        if "metro.ca" in candidate.url and await host.is_authenticated(candidate):
          return candidate
      except Exception:
        continue
    await asyncio.sleep(0.5)
  raise AuthenticationError("Authentication did not complete within the expected window.")


async def _hover_and_click(page: Page, selector: str, *, timeout: float = 10000) -> None:
  termcolor.cprint(f"[auth] Waiting for selector: {selector}", "cyan")
  element = await page.wait_for_selector(selector, state="visible", timeout=timeout)
  if element is None:
    raise AuthenticationError(f"Element '{selector}' not found.")
  try:
    await element.wait_for_element_state("stable", timeout=timeout)
  except Exception:
    termcolor.cprint(f"[auth] Element not stable; continuing: {selector}", "yellow")
  try:
    await element.scroll_into_view_if_needed()
  except Exception:
    termcolor.cprint(f"[auth] scroll_into_view_if_needed failed; continuing: {selector}", "yellow")
  await _click_center(page, element)


async def _click_center(page: Page, element: ElementHandle) -> None:
  box = await element.bounding_box()
  if box is None:
    raise AuthenticationError("Element missing bounding box.")
  target_x = box["x"] + box["width"] / 2
  target_y = box["y"] + box["height"] / 2
  termcolor.cprint(
    f"[auth] Clicking target at x={target_x:.1f}, y={target_y:.1f}",
    "magenta",
  )
  await page.mouse.move(target_x, target_y)
  await page.mouse.click(target_x, target_y)


__all__ = [
  "AuthCredentials",
  "AuthManager",
  "AuthenticationError",
  "SHORT_FENCE_WAIT_MS",
]
