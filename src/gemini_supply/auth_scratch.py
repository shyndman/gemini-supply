from __future__ import annotations

import asyncio
import os
from typing import Sequence

import termcolor
from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright_captcha import CaptchaType, ClickSolver, FrameworkType
from playwright_captcha.utils.camoufox_add_init_script.add_init_script import get_addon_path

from gemini_supply.computers import CamoufoxHost
from gemini_supply.profile import resolve_camoufox_exec, resolve_profile_dir

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)
SHORT_FENCE_WAIT_MS = 1000


def _build_camoufox_options() -> dict[str, object]:
  addon_path = get_addon_path()
  return {
    "humanize": True,
    "config": {
      "humanize:maxTime": 0.9,
      "humanize:minTime": 0.6,
      "showcursor": True,
      "forceScopeAccess": True,
    },
    "main_world_eval": True,
    "addons": [os.path.abspath(addon_path)],
    "i_know_what_im_doing": True,
    "disable_coop": True,
  }


def _resolve_env_credentials() -> tuple[str, str]:
  username = os.environ.get("GEMINI_SUPPLY_METRO_USERNAME", "").strip()
  password = os.environ.get("GEMINI_SUPPLY_METRO_PASSWORD", "").strip()
  if not username or not password:
    raise RuntimeError(
      "Set GEMINI_SUPPLY_METRO_USERNAME and GEMINI_SUPPLY_METRO_PASSWORD before running auth_scratch."
    )
  return username, password


async def _move_mouse(page: Page, x: float, y: float) -> None:
  await page.mouse.move(x, y)


async def _hover_and_click_selector(page: Page, selector: str, *, timeout: float = 10000) -> None:
  termcolor.cprint(f"[auth] Waiting for selector (visible): {selector}", color="cyan")
  element = await page.wait_for_selector(selector, state="visible", timeout=timeout)
  if element is None:
    raise RuntimeError(f"Element '{selector}' not found.")
  try:
    await element.wait_for_element_state("stable", timeout=timeout)
  except Exception:
    termcolor.cprint(f"[auth] Element not stable, proceeding anyway: {selector}", color="yellow")
  try:
    await element.scroll_into_view_if_needed()
  except Exception:
    termcolor.cprint(
      f"[auth] scroll_into_view_if_needed failed (ignored): {selector}", color="yellow"
    )
  box = await element.bounding_box()
  if box is None:
    raise RuntimeError(f"Element '{selector}' missing bounding box")
  target_x = box["x"] + box["width"] / 2
  target_y = box["y"] + box["height"] / 2
  termcolor.cprint(
    f"[auth] Moving to target and clicking: {selector} -> x={target_x:.1f}, y={target_y:.1f}",
    color="magenta",
  )
  await _move_mouse(page, target_x, target_y)
  await page.mouse.click(target_x, target_y)


async def _handle_short_fence(page: Page, solver: ClickSolver) -> None:
  termcolor.cprint("[auth] Waiting briefly before handling short fence...", color="cyan")
  await page.wait_for_timeout(SHORT_FENCE_WAIT_MS)  # Allow the page to settle

  termcolor.cprint("[auth] Starting short fence handler...", color="cyan")
  await solver.solve_captcha(
    captcha_container=page,
    captcha_type=CaptchaType.CLOUDFLARE_TURNSTILE,
  )
  termcolor.cprint("[auth] Short fence handler completed.", color="green")


async def _type_credentials(page: Page, username: str, password: str) -> None:
  user_input = await page.wait_for_selector("#signInName", timeout=15000)
  if user_input is None:
    raise RuntimeError("Username field not present.")
  user_box = await user_input.bounding_box()
  if user_box is None:
    raise RuntimeError("Username field missing bounding box.")
  await _move_mouse(
    page,
    user_box["x"] + user_box["width"] / 2,
    user_box["y"] + user_box["height"] / 2,
  )
  await page.mouse.click(
    user_box["x"] + user_box["width"] / 2,
    user_box["y"] + user_box["height"] / 2,
  )
  await page.keyboard.type(username, delay=80)
  await page.keyboard.press("Tab")
  password_input = await page.wait_for_selector("#password", timeout=5000)
  if password_input is None:
    raise RuntimeError("Password field not present.")
  password_box = await password_input.bounding_box()
  if password_box is None:
    raise RuntimeError("Password field missing bounding box.")
  await _move_mouse(
    page,
    password_box["x"] + password_box["width"] / 2,
    password_box["y"] + password_box["height"] / 2,
  )
  await page.mouse.click(
    password_box["x"] + password_box["width"] / 2,
    password_box["y"] + password_box["height"] / 2,
  )
  await page.keyboard.type(password, delay=90)
  await page.keyboard.press("Enter")


async def _ensure_cookie_banner(page: Page) -> None:
  try:
    await _hover_and_click_selector(page, "#onetrust-accept-btn-handler", timeout=4000)
    termcolor.cprint("Dismissed cookie banner.", color="magenta")
  except PlaywrightTimeout:
    termcolor.cprint("Cookie banner not present.", color="yellow")


async def _click_flyers(page: Page) -> None:
  await _hover_and_click_selector(page, 'a[href="/en/flyer"]')
  await page.wait_for_load_state()


async def _logout_if_authenticated(host: CamoufoxHost, page: Page) -> None:
  if await host.is_authenticated(page):
    termcolor.cprint("Authenticated session detected; logging out for test run...", color="yellow")
    await _hover_and_click_selector(page, "#authenticatedButton")
    await _hover_and_click_selector(page, "#loginToggleBox .cta-basic-secondary")
    await page.wait_for_load_state("networkidle")
    termcolor.cprint("Logged out; continuing to login flow.", color="yellow")


async def _open_login_drawer(page: Page) -> None:
  termcolor.cprint("[auth] Opening login drawer…", color="cyan")
  await _hover_and_click_selector(page, ".login--btn")
  termcolor.cprint("[auth] Waiting for login side panel to become visible…", color="cyan")
  await page.wait_for_selector("#loginSidePanelForm", state="visible", timeout=5000)
  termcolor.cprint(
    "[auth] Preparing to click drawer login CTA (#loginSidePanelForm .cta-basic-primary)…",
    color="cyan",
  )
  cta = await page.wait_for_selector(
    "#loginSidePanelForm .cta-basic-primary", state="visible", timeout=5000
  )
  if cta is None:
    raise RuntimeError("Login CTA not found in side panel.")
  try:
    await page.wait_for_function(
      "el => { const r = el.getBoundingClientRect(); return r.left >= 0 && r.right <= window.innerWidth; }",
      arg=cta,
      timeout=3000,
    )
  except PlaywrightTimeout:
    termcolor.cprint(
      "[auth] Drawer CTA possibly still animating; proceeding to compute box anyway.",
      color="yellow",
    )
  box = await cta.bounding_box()
  if box is None:
    raise RuntimeError("Login CTA missing bounding box.")
  target_x = box["x"] + box["width"] / 2
  target_y = box["y"] + box["height"] / 2
  termcolor.cprint(
    f"[auth] Clicking drawer login CTA at x={target_x:.1f}, y={target_y:.1f}",
    color="magenta",
  )
  await _move_mouse(page, target_x, target_y)
  await page.mouse.click(target_x, target_y)
  await page.wait_for_timeout(300)
  termcolor.cprint("[auth] Waiting for redirect to identity provider…", color="cyan")
  try:
    await page.wait_for_function(
      "() => location.href.includes('auth.')",
      timeout=30000,
    )
    termcolor.cprint(f"[auth] Redirected to identity provider: {page.url}", color="cyan")
  except PlaywrightTimeout:
    termcolor.cprint(
      "[auth] Timed out waiting for specific auth domain; waiting for load state instead.",
      color="yellow",
    )
    await page.wait_for_load_state()


async def _wait_for_metro_return(host: CamoufoxHost, pages: Sequence[Page]) -> Page:
  for _ in range(40):
    for pg in list(pages):
      if "metro.ca" in pg.url and await host.is_authenticated(pg):
        return pg
    await asyncio.sleep(0.5)
  raise RuntimeError("Authentication did not complete within expected window.")


async def run() -> None:
  username, password = _resolve_env_credentials()
  profile_dir = resolve_profile_dir()
  camoufox_exec = resolve_camoufox_exec()
  termcolor.cprint(f"Using profile: {profile_dir}", color="cyan")
  camoufox_options = _build_camoufox_options()

  async with CamoufoxHost(
    screen_size=PLAYWRIGHT_SCREEN_SIZE,
    user_data_dir=profile_dir,
    initial_url="https://www.metro.ca",
    highlight_mouse=True,
    enforce_restrictions=False,
    executable_path=camoufox_exec,
    headless=False,
    camoufox_options=camoufox_options,
  ) as host:
    page = await host.new_page()
    await page.wait_for_load_state("domcontentloaded")
    await _ensure_cookie_banner(page)
    await _click_flyers(page)
    await page.wait_for_load_state()
    await _logout_if_authenticated(host, page)

    async with ClickSolver(framework=FrameworkType.CAMOUFOX, page=page) as solver:
      await _open_login_drawer(page)
      await _handle_short_fence(page, solver)
    await _type_credentials(page, username, password)
    termcolor.cprint("Submitted credentials, waiting for redirect...", color="cyan")
    await page.wait_for_load_state("networkidle")
    final_page = await _wait_for_metro_return(host, host.context.pages)
    termcolor.cprint(f"Authenticated as: {final_page.url}", color="green")


def main() -> int:
  try:
    asyncio.run(run())
    return 0
  except KeyboardInterrupt:
    termcolor.cprint("\nInterrupted by user.", color="yellow")
    return 130
  except Exception:
    raise


if __name__ == "__main__":
  raise SystemExit(main())
