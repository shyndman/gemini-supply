from pathlib import Path

import pytest

from gemini_supply.computers import CamoufoxHost, EnvState, ScreenSize
from gemini_supply.term import ActivityLog

# Tests cover the consolidated browser host/tab implementation.


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch: pytest.MonkeyPatch) -> None:
  async def _always_authenticated(self, page) -> bool:  # type: ignore[unused-argument]
    return True

  monkeypatch.setattr(CamoufoxHost, "is_authenticated", _always_authenticated, raising=False)  # type: ignore


@pytest.fixture
def log() -> ActivityLog:
  return ActivityLog()


@pytest.mark.asyncio
async def test_tab_context_manager(tmp_path: Path, log: ActivityLog) -> None:
  """AgentManagedPage can be created from host and used as a context manager."""
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      size = page.screen_size()
      assert isinstance(size, ScreenSize)
      assert size.width == 1280
      assert size.height == 720


@pytest.mark.asyncio
async def test_tab_screen_size(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1920, 1080), enforce_restrictions=False, user_data_dir=tmp_path, log=log
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      size = page.screen_size()
      assert size.width == 1280
      assert size.height == 720


@pytest.mark.asyncio
async def test_tab_open_web_browser(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.open_web_browser()
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0
      assert "example.com" in state.url.lower()


@pytest.mark.asyncio
async def test_tab_navigate(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.navigate("https://www.example.com")
      assert isinstance(state, EnvState)
      assert "example.com" in state.url.lower()
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0


@pytest.mark.asyncio
async def test_tab_current_state(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.current_state()
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0
      assert isinstance(state.url, str)
      assert len(state.url) > 0


@pytest.mark.asyncio
async def test_tab_key_combination(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.key_combination(["enter"])
      assert isinstance(state, EnvState)


@pytest.mark.asyncio
async def test_tab_scroll_document(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      for direction in ["down", "up"]:
        state = await page.scroll_document(direction, magnitude=200)  # type: ignore[arg-type]
        assert isinstance(state, EnvState)
        assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_tab_click_at(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.click_at(720, 450)
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_tab_hover_at(tmp_path: Path, log: ActivityLog) -> None:
  async with CamoufoxHost(
    screen_size=ScreenSize(1440, 900),
    initial_url="https://example.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
    log=log,
  ) as host:
    page = await host.new_agent_managed_page()
    async with page:
      state = await page.hover_at(720, 450)
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
