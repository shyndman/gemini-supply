from typing import Literal

import pytest

from gemini_supply.computers import Computer, EnvState, ScreenSize


class MockComputer(Computer):
  """Mock implementation of Computer for testing."""

  def __init__(self) -> None:
    self._screen_width = 1440
    self._screen_height = 900

  def screen_size(self) -> ScreenSize:
    return ScreenSize(self._screen_width, self._screen_height)

  async def pre_action(self) -> None:
    pass

  async def open_web_browser(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def click_at(self, x: int, y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/clicked")

  async def hover_at(self, x: int, y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/hovered")

  async def type_text_at(
    self,
    x: int,
    y: int,
    text: str,
    press_enter: bool,
    clear_before_typing: bool,
  ) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/typed")

  async def scroll_document(
    self, direction: Literal["up", "down", "left", "right"], magnitude: int
  ) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/scrolled")

  async def scroll_at(
    self,
    x: int,
    y: int,
    direction: Literal["up", "down", "left", "right"],
    magnitude: int,
  ) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/scrolled_at")

  async def wait_5_seconds(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/waited")

  async def go_back(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/back")

  async def go_forward(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/forward")

  async def search(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://google.com")

  async def navigate(self, url: str) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url=url)

  async def key_combination(self, keys: list[str]) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/keys")

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/dragged")

  async def current_state(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")


@pytest.mark.asyncio
async def test_computer_screen_size() -> None:
  """Test that screen_size returns expected dimensions."""
  computer = MockComputer()
  width, height = computer.screen_size()
  assert width == 1440
  assert height == 900


@pytest.mark.asyncio
async def test_computer_open_web_browser() -> None:
  """Test that open_web_browser returns EnvState."""
  computer = MockComputer()
  state = await computer.open_web_browser()
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com"
  assert state.screenshot == b"mock_screenshot"


@pytest.mark.asyncio
async def test_computer_click_at() -> None:
  """Test that click_at returns EnvState with correct URL."""
  computer = MockComputer()
  state = await computer.click_at(100, 200)
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/clicked"


@pytest.mark.asyncio
async def test_computer_hover_at() -> None:
  """Test that hover_at returns EnvState."""
  computer = MockComputer()
  state = await computer.hover_at(300, 400)
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/hovered"


@pytest.mark.asyncio
async def test_computer_type_text_at() -> None:
  """Test that type_text_at returns EnvState."""
  computer = MockComputer()
  state = await computer.type_text_at(
    x=100, y=200, text="Hello World", press_enter=True, clear_before_typing=True
  )
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/typed"


@pytest.mark.asyncio
async def test_computer_scroll_document() -> None:
  """Test that scroll_document works for all directions."""
  computer = MockComputer()
  for direction in ["up", "down", "left", "right"]:
    state = await computer.scroll_document(direction, magnitude=200)  # type: ignore[arg-type]
    assert isinstance(state, EnvState)
    assert state.url == "https://example.com/scrolled"


@pytest.mark.asyncio
async def test_computer_scroll_at() -> None:
  """Test that scroll_at returns EnvState."""
  computer = MockComputer()
  state = await computer.scroll_at(x=100, y=200, direction="down", magnitude=800)
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/scrolled_at"


@pytest.mark.asyncio
async def test_computer_wait_5_seconds() -> None:
  """Test that wait_5_seconds returns EnvState."""
  computer = MockComputer()
  state = await computer.wait_5_seconds()
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/waited"


@pytest.mark.asyncio
async def test_computer_navigate() -> None:
  """Test that navigate returns EnvState with correct URL."""
  computer = MockComputer()
  state = await computer.navigate("https://newsite.com")
  assert isinstance(state, EnvState)
  assert state.url == "https://newsite.com"


@pytest.mark.asyncio
async def test_computer_go_back() -> None:
  """Test that go_back returns EnvState."""
  computer = MockComputer()
  state = await computer.go_back()
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/back"


@pytest.mark.asyncio
async def test_computer_go_forward() -> None:
  """Test that go_forward returns EnvState."""
  computer = MockComputer()
  state = await computer.go_forward()
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/forward"


@pytest.mark.asyncio
async def test_computer_search() -> None:
  """Test that search returns EnvState."""
  computer = MockComputer()
  state = await computer.search()
  assert isinstance(state, EnvState)
  assert state.url == "https://google.com"


@pytest.mark.asyncio
async def test_computer_key_combination() -> None:
  """Test that key_combination returns EnvState."""
  computer = MockComputer()
  state = await computer.key_combination(["Control", "C"])
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/keys"


@pytest.mark.asyncio
async def test_computer_drag_and_drop() -> None:
  """Test that drag_and_drop returns EnvState."""
  computer = MockComputer()
  state = await computer.drag_and_drop(x=100, y=200, destination_x=300, destination_y=400)
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com/dragged"


@pytest.mark.asyncio
async def test_computer_current_state() -> None:
  """Test that current_state returns EnvState."""
  computer = MockComputer()
  state = await computer.current_state()
  assert isinstance(state, EnvState)
  assert state.url == "https://example.com"
  assert state.screenshot == b"mock_screenshot"
