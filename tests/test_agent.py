from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from gemini_supply.agent import BrowserAgent
from gemini_supply.computers import Computer, EnvState, ScreenSize


class MockComputer(Computer):
  """Mock Computer implementation for testing."""

  def screen_size(self) -> ScreenSize:
    return ScreenSize(1440, 900)

  async def open_web_browser(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def click_at(self, x: int, y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com/clicked")

  async def hover_at(self, x: int, y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def type_text_at(
    self, x: int, y: int, text: str, press_enter: bool, clear_before_typing: bool
  ) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def scroll_document(self, direction: Literal["up", "down", "left", "right"]) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def scroll_at(
    self, x: int, y: int, direction: Literal["up", "down", "left", "right"], magnitude: int
  ) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def wait_5_seconds(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def go_back(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def go_forward(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def search(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://google.com")

  async def navigate(self, url: str) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url=url)

  async def key_combination(self, keys: list[str]) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def drag_and_drop(self, x: int, y: int, destination_x: int, destination_y: int) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")

  async def current_state(self) -> EnvState:
    return EnvState(screenshot=b"mock_screenshot", url="https://example.com")


@pytest.fixture
def mock_computer() -> MockComputer:
  """Fixture providing a mock computer instance."""
  return MockComputer()


@pytest.fixture
def set_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
  """Fixture to set GEMINI_API_KEY environment variable."""
  monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")


@pytest.mark.asyncio
async def test_browser_agent_initialization(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that BrowserAgent initializes correctly."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )
  assert agent._query == "Test query"
  assert agent._model_name == "gemini-2.5-computer-use-preview-10-2025"
  assert agent._browser_computer == mock_computer


@pytest.mark.asyncio
async def test_handle_action_open_web_browser(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that handle_action correctly handles open_web_browser."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  function_call = types.FunctionCall(name="open_web_browser", args={})
  result = await agent.handle_action(function_call)

  assert isinstance(result, EnvState)
  assert result.url == "https://example.com"


@pytest.mark.asyncio
async def test_handle_action_click_at(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that handle_action correctly handles click_at with coordinate denormalization."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  # Gemini uses 1000x1000 normalized coordinates
  # 500 on 1000 scale should map to 720 on 1440 screen (500/1000 * 1440 = 720)
  function_call = types.FunctionCall(name="click_at", args={"x": 500, "y": 500})
  result = await agent.handle_action(function_call)

  assert isinstance(result, EnvState)
  assert result.url == "https://example.com/clicked"


@pytest.mark.asyncio
async def test_handle_action_navigate(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that handle_action correctly handles navigate."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  function_call = types.FunctionCall(name="navigate", args={"url": "https://test.com"})
  result = await agent.handle_action(function_call)

  assert isinstance(result, EnvState)
  assert result.url == "https://test.com"


@pytest.mark.asyncio
async def test_handle_action_key_combination(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that handle_action correctly handles key_combination."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  function_call = types.FunctionCall(name="key_combination", args={"keys": "control+c"})
  result = await agent.handle_action(function_call)

  assert isinstance(result, EnvState)


@pytest.mark.asyncio
async def test_denormalize_coordinates(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test coordinate denormalization from 1000-based to actual screen size."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  # Test x coordinate denormalization
  # 500 on 1000 scale should map to 720 on 1440 screen
  assert agent.denormalize_x(500) == 720

  # Test y coordinate denormalization
  # 500 on 1000 scale should map to 450 on 900 screen
  assert agent.denormalize_y(500) == 450

  # Test edge cases
  assert agent.denormalize_x(0) == 0
  assert agent.denormalize_x(1000) == 1440
  assert agent.denormalize_y(0) == 0
  assert agent.denormalize_y(1000) == 900


@pytest.mark.asyncio
async def test_get_model_response_retry_logic(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that get_model_response implements retry logic with exponential backoff."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  # Mock the client's generate_content method to fail once then succeed
  mock_response = MagicMock()
  mock_response.candidates = [
    MagicMock(content=types.Content(role="model", parts=[types.Part(text="Success")]))
  ]

  with patch.object(agent._client.models, "generate_content") as mock_generate:
    mock_generate.side_effect = [Exception("API Error"), mock_response]

    # Should retry and eventually succeed
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
      response = await agent.get_model_response(max_retries=3, base_delay_s=1)
      assert response == mock_response
      # Should have called sleep once for the retry
      assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_get_model_response_max_retries_exhausted(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that get_model_response raises after max retries."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  with patch.object(agent._client.models, "generate_content") as mock_generate:
    mock_generate.side_effect = Exception("API Error")

    with pytest.raises(Exception, match="API Error"):
      with patch("asyncio.sleep", new_callable=AsyncMock):
        await agent.get_model_response(max_retries=2, base_delay_s=1)


@pytest.mark.asyncio
async def test_handle_action_unsupported_function(
  mock_computer: MockComputer, set_gemini_api_key: None
) -> None:
  """Test that handle_action raises ValueError for unsupported functions."""
  agent = BrowserAgent(
    browser_computer=mock_computer,
    query="Test query",
    model_name="gemini-2.5-computer-use-preview-10-2025",
  )

  function_call = types.FunctionCall(name="unsupported_function", args={})

  with pytest.raises(ValueError, match="Unsupported function"):
    await agent.handle_action(function_call)
