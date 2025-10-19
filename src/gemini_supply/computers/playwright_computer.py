# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncio
import os
import sys
from types import TracebackType
from typing import Literal

import playwright.async_api
import termcolor
from playwright.async_api import async_playwright

from .computer import Computer, EnvState, ScreenSize

# Define a mapping from the user-friendly key names to Playwright's expected key names.
# Playwright is generally good with case-insensitivity for these, but it's best to be canonical.
# See: https://playwright.dev/docs/api/class-keyboard#keyboard-press
# Keys like 'a', 'b', '1', '$' are passed directly.
PLAYWRIGHT_KEY_MAP: dict[str, str] = {
  "backspace": "Backspace",
  "tab": "Tab",
  "return": "Enter",  # Playwright uses 'Enter'
  "enter": "Enter",
  "shift": "Shift",
  "control": "ControlOrMeta",
  "alt": "Alt",
  "escape": "Escape",
  "space": "Space",  # Can also just be " "
  "pageup": "PageUp",
  "pagedown": "PageDown",
  "end": "End",
  "home": "Home",
  "left": "ArrowLeft",
  "up": "ArrowUp",
  "right": "ArrowRight",
  "down": "ArrowDown",
  "insert": "Insert",
  "delete": "Delete",
  "semicolon": ";",  # For actual character ';'
  "equals": "=",  # For actual character '='
  "multiply": "Multiply",  # NumpadMultiply
  "add": "Add",  # NumpadAdd
  "separator": "Separator",  # Numpad specific
  "subtract": "Subtract",  # NumpadSubtract, or just '-' for character
  "decimal": "Decimal",  # NumpadDecimal, or just '.' for character
  "divide": "Divide",  # NumpadDivide, or just '/' for character
  "f1": "F1",
  "f2": "F2",
  "f3": "F3",
  "f4": "F4",
  "f5": "F5",
  "f6": "F6",
  "f7": "F7",
  "f8": "F8",
  "f9": "F9",
  "f10": "F10",
  "f11": "F11",
  "f12": "F12",
  "command": "Meta",  # 'Meta' is Command on macOS, Windows key on Windows
}


class PlaywrightComputer(Computer):
  """Connects to a local Playwright instance."""

  def __init__(
    self,
    screen_size: ScreenSize | tuple[int, int],
    initial_url: str = "https://www.google.com",
    search_engine_url: str = "https://www.google.com",
    highlight_mouse: bool = False,
  ):
    self._initial_url = initial_url
    if isinstance(screen_size, ScreenSize):
      self._screen_size = screen_size
    else:
      self._screen_size = ScreenSize(*screen_size)
    self._search_engine_url = search_engine_url
    self._highlight_mouse = highlight_mouse
    # Runtime-managed Playwright objects (initialized in __aenter__)
    self._playwright: playwright.async_api.Playwright | None = None
    self._browser: playwright.async_api.Browser | None = None
    self._context: playwright.async_api.BrowserContext | None = None
    self._page: playwright.async_api.Page | None = None

  async def _handle_new_page(self, new_page: playwright.async_api.Page) -> None:
    """The Computer Use model only supports a single tab at the moment.

    Some websites, however, try to open links in a new tab.
    For those situations, we intercept the page-opening behavior, and instead overwrite the current page.
    """
    new_url = new_page.url
    await new_page.close()
    page = self._page
    assert page is not None
    await page.goto(new_url)

  async def __aenter__(self) -> "PlaywrightComputer":
    print("Creating session...")
    self._playwright = await async_playwright().start()
    assert self._playwright is not None
    p = self._playwright
    self._browser = await p.chromium.launch(
      args=[
        "--disable-extensions",
        "--disable-file-system",
        "--disable-plugins",
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-sync",
        # No '--no-sandbox' arg means the sandbox is on.
      ],
      headless=bool(os.environ.get("PLAYWRIGHT_HEADLESS", False)),
    )
    assert self._browser is not None
    self._context = await self._browser.new_context(
      viewport={
        "width": self._screen_size.width,
        "height": self._screen_size.height,
      }
    )
    context = self._context
    assert context is not None
    self._page = await context.new_page()
    page = self._page
    assert page is not None
    await page.goto(self._initial_url)

    context.on("page", self._handle_new_page)

    termcolor.cprint(
      "Started local playwright.",
      color="green",
      attrs=["bold"],
    )
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc_val: BaseException | None,
    exc_tb: TracebackType | None,
  ) -> None:
    """Cleanup resources when exiting context manager."""
    if self._context is not None:
      try:
        await self._context.close()
      except Exception:
        pass
      finally:
        self._context = None
    if self._browser is not None:
      try:
        await self._browser.close()
      except Exception as e:
        if "Browser.close: Connection closed while reading from the driver" in str(e):
          pass
        else:
          raise
      finally:
        self._browser = None
    if self._playwright is not None:
      try:
        await self._playwright.stop()
      except Exception:
        pass
      finally:
        self._playwright = None

  async def open_web_browser(self) -> EnvState:
    return await self.current_state()

  async def click_at(self, x: int, y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    page = self._page
    assert page is not None
    await page.mouse.click(x, y)
    await page.wait_for_load_state()
    return await self.current_state()

  async def hover_at(self, x: int, y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    page = self._page
    assert page is not None
    await page.mouse.move(x, y)
    await page.wait_for_load_state()
    return await self.current_state()

  async def type_text_at(
    self,
    x: int,
    y: int,
    text: str,
    press_enter: bool = False,
    clear_before_typing: bool = True,
  ) -> EnvState:
    await self.highlight_mouse(x, y)
    page = self._page
    assert page is not None
    await page.mouse.click(x, y)
    await page.wait_for_load_state()

    if clear_before_typing:
      if sys.platform == "darwin":
        await self.key_combination(["Command", "A"])
      else:
        await self.key_combination(["Control", "A"])
      await self.key_combination(["Delete"])

    await page.keyboard.type(text)
    await page.wait_for_load_state()

    if press_enter:
      await self.key_combination(["Enter"])
    await page.wait_for_load_state()
    return await self.current_state()

  async def _horizontal_document_scroll(self, direction: Literal["left", "right"]) -> EnvState:
    # Scroll by 50% of the viewport size.
    horizontal_scroll_amount = self.screen_size().width // 2
    if direction == "left":
      sign = "-"
    else:
      sign = ""
    scroll_argument = f"{sign}{horizontal_scroll_amount}"
    # Scroll using JS.
    page = self._page
    assert page is not None
    await page.evaluate(f"window.scrollBy({scroll_argument}, 0); ")
    await page.wait_for_load_state()
    return await self.current_state()

  async def scroll_document(self, direction: Literal["up", "down", "left", "right"]) -> EnvState:
    if direction == "down":
      return await self.key_combination(["PageDown"])
    elif direction == "up":
      return await self.key_combination(["PageUp"])
    elif direction in ("left", "right"):
      return await self._horizontal_document_scroll(direction)
    else:
      raise ValueError("Unsupported direction: ", direction)

  async def scroll_at(
    self,
    x: int,
    y: int,
    direction: Literal["up", "down", "left", "right"],
    magnitude: int = 800,
  ) -> EnvState:
    await self.highlight_mouse(x, y)

    page = self._page
    assert page is not None
    await page.mouse.move(x, y)
    await page.wait_for_load_state()

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

    await page.mouse.wheel(dx, dy)
    await page.wait_for_load_state()
    return await self.current_state()

  async def wait_5_seconds(self) -> EnvState:
    await asyncio.sleep(5)
    return await self.current_state()

  async def go_back(self) -> EnvState:
    page = self._page
    assert page is not None
    await page.go_back()
    await page.wait_for_load_state()
    return await self.current_state()

  async def go_forward(self) -> EnvState:
    page = self._page
    assert page is not None
    await page.go_forward()
    await page.wait_for_load_state()
    return await self.current_state()

  async def search(self) -> EnvState:
    return await self.navigate(self._search_engine_url)

  async def navigate(self, url: str) -> EnvState:
    normalized_url = url
    if not normalized_url.startswith(("http://", "https://")):
      normalized_url = "https://" + normalized_url
    page = self._page
    assert page is not None
    await page.goto(normalized_url)
    await page.wait_for_load_state()
    return await self.current_state()

  async def key_combination(self, keys: list[str]) -> EnvState:
    # Normalize all keys to the Playwright compatible version.
    keys = [PLAYWRIGHT_KEY_MAP.get(k.lower(), k) for k in keys]

    page = self._page
    assert page is not None
    for key in keys[:-1]:
      await page.keyboard.down(key)

    await page.keyboard.press(keys[-1])

    for key in reversed(keys[:-1]):
      await page.keyboard.up(key)

    return await self.current_state()

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
    await self.highlight_mouse(x, y)
    page = self._page
    assert page is not None
    await page.mouse.move(x, y)
    await page.wait_for_load_state()
    await page.mouse.down()
    await page.wait_for_load_state()

    await self.highlight_mouse(destination_x, destination_y)
    await page.mouse.move(destination_x, destination_y)
    await page.wait_for_load_state()
    await page.mouse.up()
    return await self.current_state()

  async def current_state(self) -> EnvState:
    page = self._page
    assert page is not None
    await page.wait_for_load_state()
    # Even if Playwright reports the page as loaded, it may not be so.
    # Add a manual sleep to make sure the page has finished rendering.
    await asyncio.sleep(0.5)
    screenshot_bytes = await page.screenshot(type="png", full_page=False)
    return EnvState(screenshot=screenshot_bytes, url=page.url)

  def screen_size(self) -> ScreenSize:
    page = self._page
    assert page is not None
    viewport_size = page.viewport_size
    # If available, try to take the local playwright viewport size.
    if viewport_size:
      return ScreenSize(viewport_size["width"], viewport_size["height"])
    # If unavailable, fall back to the original provided size.
    return self._screen_size

  async def highlight_mouse(self, x: int, y: int) -> None:
    if not self._highlight_mouse:
      return
    page = self._page
    assert page is not None
    await page.evaluate(
      f"""
        () => {{
            const element_id = "playwright-feedback-circle";
            const div = document.createElement('div');
            div.id = element_id;
            div.style.pointerEvents = 'none';
            div.style.border = '4px solid red';
            div.style.borderRadius = '50%';
            div.style.width = '20px';
            div.style.height = '20px';
            div.style.position = 'fixed';
            div.style.zIndex = '9999';
            document.body.appendChild(div);

            div.hidden = false;
            div.style.left = {x} - 10 + 'px';
            div.style.top = {y} - 10 + 'px';

            setTimeout(() => {{
                div.hidden = true;
            }}, 2000);
        }}
    """
    )
    # Wait a bit for the user to see the cursor.
    await asyncio.sleep(1)
