import asyncio
from collections.abc import Callable
from types import TracebackType
from typing import Awaitable, Literal

from playwright.async_api import Page

from .computer import Computer, EnvState, ScreenSize
from .keys import PLAYWRIGHT_KEY_MAP


class AgentManagedPage(Computer):
  """An agent-managed Computer implementation backed by a single Playwright Page."""

  def __init__(
    self,
    *,
    page: Page,
    screen_size: ScreenSize,
    is_authenticated_delegate: Callable[[Page], Awaitable[bool]],
    pre_iteration_delegate: Callable[[Page], Awaitable[None]] | None = None,
    highlight_mouse: bool = False,
  ) -> None:
    self._page = page
    self._screen_size = screen_size
    self._is_authenticated_delegate = is_authenticated_delegate
    self._pre_iteration_delegate = pre_iteration_delegate
    self._highlight_mouse = highlight_mouse

  async def __aenter__(self) -> "AgentManagedPage":
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

  async def pre_action(self) -> None:
    if self._pre_iteration_delegate is not None:
      await self._pre_iteration_delegate(self._page)

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
      await self.key_combination(["Control", "A"])
      await self.key_combination(["Delete"])
    await self._page.keyboard.type(text)
    await self._page.wait_for_load_state()
    if press_enter:
      await self.key_combination(["Enter"])
    await self._page.wait_for_load_state()
    return await self.current_state()

  async def scroll_document(
    self, direction: Literal["up", "down", "left", "right"], magnitude: int
  ) -> EnvState:
    x, y = 0, 0

    if direction == "down":
      y += magnitude
    elif direction == "up":
      y -= magnitude
    elif direction == "left":
      x -= magnitude
    elif direction == "right":
      x += magnitude

    await self._page.evaluate(f"window.scrollBy({x}, {y});")
    return await self.current_state()

  async def scroll_at(
    self,
    x: int,
    y: int,
    direction: Literal["up", "down", "left", "right"],
    magnitude: int,
  ) -> EnvState:
    magnitude = min(-140, max(140, magnitude))

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
    await self._page.go_back(wait_until="load")
    return await self.current_state()

  async def go_forward(self) -> EnvState:
    await self._page.go_forward(wait_until="load")
    return await self.current_state()

  async def search(self) -> EnvState:
    raise NotImplementedError("search() not implemented in AgentManagedPage")

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
    await self._page.wait_for_load_state()
    await asyncio.sleep(0.5)
    if not await self._is_authenticated_delegate(self._page):
      raise AuthExpiredError("Authentication expired or missing — login required")
    screenshot_bytes = await self._page.screenshot(type="png", full_page=False)
    return EnvState(url=self._page.url, screenshot=screenshot_bytes)

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


class AuthExpiredError(Exception):
  """Raised when a session is no longer authenticated."""

  ...
