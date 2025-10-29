from __future__ import annotations

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, TypeAlias

import termcolor
from playwright.async_api import Page, Position
from playwright.async_api import TimeoutError as PlaywrightTimeout

from gemini_supply.auth.short_fence import find_interactive_element_click_location
from gemini_supply.computers import CamoufoxHost
from gemini_supply.term import display_image_bytes_in_terminal

SHORT_FENCE_ATTEMPTS = 4
SHORT_FENCE_WAIT_MS = 2000

AuthFlow: TypeAlias = Callable[[CamoufoxHost], Awaitable[None]]


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

  async def ensure_authenticated(self) -> None:
    async with self._lock:
      await self._auth_flow(self._host)
      self._last_success = time.monotonic()


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
    await _accept_cookies(page)
    await _open_promotions(page)
    await page.wait_for_load_state()

    if await host.is_authenticated(page):
      termcolor.cprint("[auth] Existing authenticated session detected; skipping login.", "yellow")
      return

    await _launch_login_drawer(page)
    await _solve_short_fence(page)
    await _submit_credentials(page, credentials)

    termcolor.cprint("[auth] Submitted credentials; waiting for redirect.", "cyan")
    await page.wait_for_load_state("networkidle")
  finally:
    await _ensure_keepalive_tab(host, preserve=page)


def _resolve_credentials() -> AuthCredentials:
  username = os.environ.get("GEMINI_SUPPLY_METRO_USERNAME", "").strip()
  password = os.environ.get("GEMINI_SUPPLY_METRO_PASSWORD", "").strip()
  if not username or not password:
    raise AuthenticationError(
      "Set GEMINI_SUPPLY_METRO_USERNAME and GEMINI_SUPPLY_METRO_PASSWORD for automated auth."
    )
  return AuthCredentials(username=username, password=password)


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
    await page.locator("#onetrust-accept-btn-handler").click()
    termcolor.cprint("[auth] Accepted cookies.", "magenta")
  except PlaywrightTimeout:
    termcolor.cprint("[auth] Cookie banner not present.", "yellow")


async def _open_promotions(page: Page) -> None:
  await page.locator('.header-navs a[href="/en/flyer"]').click()
  await page.wait_for_load_state()


AUTH_URL_PATTERN = re.compile("^https://auth.moiid.ca/")


async def _launch_login_drawer(page: Page) -> None:
  termcolor.cprint("[auth] Opening login drawer.", "cyan")
  await page.locator(".login--btn").click()
  await page.wait_for_timeout(1000)

  termcolor.cprint("[auth] Triggering login action.", "cyan")
  login_btn = page.locator("#loginSidePanelForm .cta-basic-primary")
  await login_btn.is_visible()
  await login_btn.click()

  await page.wait_for_url(AUTH_URL_PATTERN)


async def _solve_short_fence(page: Page) -> None:
  termcolor.cprint("[auth] Preparing short fence solver.", "cyan")
  click_position: Position | None = None
  for attempt in range(SHORT_FENCE_ATTEMPTS):
    await page.wait_for_timeout(SHORT_FENCE_WAIT_MS)
    png_bytes = await page.locator(".main-content").screenshot(timeout=2000)
    display_image_bytes_in_terminal(png_bytes)
    click_position = find_interactive_element_click_location(png_bytes)
    if click_position is not None:
      termcolor.cprint(f"[auth] Click location determined, {click_position}.", "cyan")
      break

  if click_position is None:  # type: ignore
    raise AuthenticationError("Short fence challenge not detected.")

  await page.click(".main-content", position=click_position)
  termcolor.cprint("[auth] Short fence cleared.", "green")


async def _submit_credentials(page: Page, credentials: AuthCredentials) -> None:
  termcolor.cprint("[auth] Starting credential submission.", "cyan")
  termcolor.cprint(f"[auth] Current page URL: {page.url}", "cyan")

  termcolor.cprint("[auth] Waiting for username field (#signInName).", "cyan")
  await page.locator("#signInName").fill(credentials.username)
  termcolor.cprint("[auth] Username entered.", "green")

  termcolor.cprint("[auth] Waiting for password field (#password).", "cyan")
  await page.locator("#password").fill(credentials.password)
  termcolor.cprint("[auth] Password entered.", "green")

  await page.keyboard.press("Enter")
  termcolor.cprint("[auth] Submitted login form (pressed Enter).", "green")
