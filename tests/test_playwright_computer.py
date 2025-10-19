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

import pytest

from gemini_supply.computers import EnvState, PlaywrightComputer, ScreenSize


@pytest.fixture(autouse=True)
def enable_headless_mode(monkeypatch: pytest.MonkeyPatch) -> None:
  """Automatically enable headless mode for all Playwright tests."""
  monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "1")


@pytest.mark.asyncio
async def test_playwright_computer_context_manager() -> None:
  """Test that PlaywrightComputer works as an async context manager."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    size = computer.screen_size()
    assert isinstance(size, ScreenSize)
    assert size.width == 1440
    assert size.height == 900


@pytest.mark.asyncio
async def test_playwright_computer_screen_size() -> None:
  """Test that screen_size returns the configured dimensions."""
  async with PlaywrightComputer(screen_size=(1920, 1080)) as computer:
    size = computer.screen_size()
    assert size.width == 1920
    assert size.height == 1080


@pytest.mark.asyncio
async def test_playwright_computer_open_web_browser() -> None:
  """Test that open_web_browser returns EnvState with screenshot and URL."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    state = await computer.open_web_browser()
    assert isinstance(state, EnvState)
    assert isinstance(state.screenshot, bytes)
    assert len(state.screenshot) > 0
    assert "google.com" in state.url.lower()


@pytest.mark.asyncio
async def test_playwright_computer_navigate() -> None:
  """Test that navigate changes the URL and returns EnvState."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    state = await computer.navigate("https://www.example.com")
    assert isinstance(state, EnvState)
    assert "example.com" in state.url.lower()
    assert isinstance(state.screenshot, bytes)
    assert len(state.screenshot) > 0


@pytest.mark.asyncio
async def test_playwright_computer_navigate_without_protocol() -> None:
  """Test that navigate adds https:// if protocol is missing."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    state = await computer.navigate("www.example.com")
    assert isinstance(state, EnvState)
    assert "example.com" in state.url.lower()


@pytest.mark.asyncio
async def test_playwright_computer_current_state() -> None:
  """Test that current_state returns EnvState with screenshot and URL."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    state = await computer.current_state()
    assert isinstance(state, EnvState)
    assert isinstance(state.screenshot, bytes)
    assert len(state.screenshot) > 0
    assert isinstance(state.url, str)
    assert len(state.url) > 0


@pytest.mark.asyncio
async def test_playwright_computer_search() -> None:
  """Test that search navigates to the search engine URL."""
  async with PlaywrightComputer(
    screen_size=(1440, 900),
    initial_url="https://www.example.com",
    search_engine_url="https://www.google.com",
  ) as computer:
    # First navigate away from the search engine
    await computer.navigate("https://www.example.com")
    # Then call search
    state = await computer.search()
    assert isinstance(state, EnvState)
    assert "google.com" in state.url.lower()


@pytest.mark.asyncio
async def test_playwright_computer_key_combination() -> None:
  """Test that key_combination executes without errors."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    # Test a simple key press
    state = await computer.key_combination(["enter"])
    assert isinstance(state, EnvState)


@pytest.mark.asyncio
async def test_playwright_computer_scroll_document() -> None:
  """Test that scroll_document executes for all directions."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    for direction in ["down", "up"]:
      state = await computer.scroll_document(direction)  # type: ignore[arg-type]
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_playwright_computer_click_at() -> None:
  """Test that click_at executes without errors."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    # Click at a safe coordinate (center of screen)
    state = await computer.click_at(720, 450)
    assert isinstance(state, EnvState)
    assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_playwright_computer_hover_at() -> None:
  """Test that hover_at executes without errors."""
  async with PlaywrightComputer(
    screen_size=(1440, 900), initial_url="https://www.google.com"
  ) as computer:
    # Hover at a safe coordinate (center of screen)
    state = await computer.hover_at(720, 450)
    assert isinstance(state, EnvState)
    assert isinstance(state.screenshot, bytes)
