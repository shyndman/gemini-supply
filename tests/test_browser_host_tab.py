from pathlib import Path

import pytest

from gemini_supply.computers import CamoufoxHost, EnvState, ScreenSize

# Tests cover the consolidated browser host/tab implementation.


@pytest.fixture(autouse=True)
def enable_headless_mode(monkeypatch: pytest.MonkeyPatch) -> None:
  """Automatically enable headless mode for all Playwright tests."""
  monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "1")


@pytest.fixture(autouse=True)
def bypass_auth(monkeypatch: pytest.MonkeyPatch) -> None:
  async def _always_authenticated(self, page) -> bool:  # type: ignore[unused-argument]
    return True

  monkeypatch.setattr(CamoufoxHost, "is_authenticated", _always_authenticated, raising=False)  # type: ignore


@pytest.mark.asyncio
async def test_tab_context_manager(tmp_path: Path) -> None:
  """Tab can be created from host and used as a context manager."""
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      size = tab.screen_size()
      assert isinstance(size, ScreenSize)
      assert size.width == 1440
      assert size.height == 900


@pytest.mark.asyncio
async def test_tab_screen_size(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1920, 1080), enforce_restrictions=False, user_data_dir=tmp_path
  ) as host:
    tab = await host.new_tab()
    async with tab:
      size = tab.screen_size()
      assert size.width == 1920
      assert size.height == 1080


@pytest.mark.asyncio
async def test_tab_open_web_browser(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.open_web_browser()
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0
      assert "google.com" in state.url.lower()


@pytest.mark.asyncio
async def test_tab_navigate(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.navigate("https://www.example.com")
      assert isinstance(state, EnvState)
      assert "example.com" in state.url.lower()
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0


@pytest.mark.asyncio
async def test_tab_navigate_without_protocol(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.navigate("www.example.com")
      assert isinstance(state, EnvState)
      assert "example.com" in state.url.lower()


@pytest.mark.asyncio
async def test_tab_current_state(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.current_state()
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
      assert len(state.screenshot) > 0
      assert isinstance(state.url, str)
      assert len(state.url) > 0


@pytest.mark.asyncio
async def test_tab_search(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.example.com",
    search_engine_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      await tab.navigate("https://www.example.com")
      state = await tab.search()
      assert isinstance(state, EnvState)
      assert "google.com" in state.url.lower()


@pytest.mark.asyncio
async def test_tab_key_combination(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.key_combination(["enter"])
      assert isinstance(state, EnvState)


@pytest.mark.asyncio
async def test_tab_scroll_document(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      for direction in ["down", "up"]:
        state = await tab.scroll_document(direction)  # type: ignore[arg-type]
        assert isinstance(state, EnvState)
        assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_tab_click_at(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.click_at(720, 450)
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)


@pytest.mark.asyncio
async def test_tab_hover_at(tmp_path: Path) -> None:
  async with CamoufoxHost(
    screen_size=(1440, 900),
    initial_url="https://www.google.com",
    enforce_restrictions=False,
    user_data_dir=tmp_path,
  ) as host:
    tab = await host.new_tab()
    async with tab:
      state = await tab.hover_at(720, 450)
      assert isinstance(state, EnvState)
      assert isinstance(state.screenshot, bytes)
