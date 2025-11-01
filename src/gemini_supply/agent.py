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
from enum import StrEnum
from typing import Any, Callable, Literal, TypeAlias, TypedDict, cast

import google.genai
from google.genai._extra_utils import (
  convert_number_values_for_dict_function_call_args,
  invoke_function_from_dict_args_async,
)
from google.genai.types import (
  Candidate,
  ComputerUse,
  Content,
  ContentListUnionDict,
  Environment,
  FinishReason,
  FunctionCall,
  FunctionDeclaration,
  FunctionResponse,
  FunctionResponseBlob,
  FunctionResponsePart,
  GenerateContentConfig,
  GenerateContentResponse,
  Part,
  Tool,
)
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from gemini_supply.computers import Computer, EnvState
from gemini_supply.grocery import ItemAddedResult, ItemNotFoundResult
from gemini_supply.preferences import ProductDecision
from gemini_supply.term import ActivityLog, activity_log

MAX_RECENT_TURN_WITH_SCREENSHOTS = 3
PREDEFINED_COMPUTER_USE_FUNCTIONS = [
  "open_web_browser",
  "click_at",
  "hover_at",
  "type_text_at",
  "scroll_document",
  "scroll_at",
  "wait_5_seconds",
  "go_back",
  "go_forward",
  "navigate",
  "key_combination",
  "drag_and_drop",
]
EXCLUDED_PREDEFINED_FUNCTIONS = [
  "search",
]


console = Console()


class SafetyDecision(TypedDict):
  """Type definition for safety decision objects."""

  decision: str
  explanation: str


# Built-in Computer Use tools return EnvState.
# Custom provided functions return Pydantic models.
CustomToolResult = ItemAddedResult | ItemNotFoundResult | ProductDecision
ActionResult = EnvState | CustomToolResult

CustomFunctionCallable: TypeAlias = Callable[..., Any]


class LoopStatus(StrEnum):
  COMPLETE = "COMPLETE"
  CONTINUE = "CONTINUE"


class BrowserAgent:
  def __init__(
    self,
    browser_computer: Computer,
    query: str,
    model_name: str,
    verbose: bool = True,
    client: google.genai.Client | None = None,
    custom_tools: list[CustomFunctionCallable] = [],
    output_label: str | None = None,
    agent_label: str | None = None,
  ):
    self._browser_computer = browser_computer
    self._query = query
    self._model_name = model_name
    self._verbose = verbose
    self.final_reasoning = None
    self._turn_index = 0
    self._output_label = output_label
    self._agent_label = agent_label
    self._client: google.genai.Client = client or google.genai.Client(
      api_key=os.environ.get("GEMINI_API_KEY"),
    )
    self._contents: list[Content] = [
      Content(
        role="user",
        parts=[
          Part(text=self._query),
        ],
      )
    ]

    self._custom_tools_by_name = {
      fn.__name__: (
        FunctionDeclaration.from_callable(client=self._client._api_client, callable=fn),
        fn,
      )
      for fn in custom_tools
    }
    self._generate_content_config: GenerateContentConfig | None = None

  def _with_agent_prefix(self, message: str) -> str:
    if not self._agent_label:
      return message
    return f"[{self._agent_label}] {message}"

  def _ensure_client_and_config(self) -> None:
    self._generate_content_config = self._generate_content_config or GenerateContentConfig(
      temperature=1,
      top_p=0.95,
      top_k=40,
      max_output_tokens=8192,
      tools=[
        Tool(
          computer_use=ComputerUse(
            environment=Environment.ENVIRONMENT_BROWSER,
            excluded_predefined_functions=EXCLUDED_PREDEFINED_FUNCTIONS,
          ),
        ),
        Tool(function_declarations=[decl for (decl, _) in self._custom_tools_by_name.values()]),
      ],
    )

  async def handle_action(self, action: FunctionCall) -> ActionResult:
    await self._browser_computer.pre_action()

    """Handles the action and returns the environment state."""
    assert action.args is not None, f"Action {action.name} missing required args"
    match action.name:
      case "open_web_browser":
        return await self._browser_computer.open_web_browser()

      case "click_at":
        x = self.denormalize_x(action.args["x"])
        y = self.denormalize_y(action.args["y"])
        return await self._browser_computer.click_at(x=x, y=y)

      case "hover_at":
        x = self.denormalize_x(action.args["x"])
        y = self.denormalize_y(action.args["y"])
        return await self._browser_computer.hover_at(x=x, y=y)

      case "type_text_at":
        x = self.denormalize_x(action.args["x"])
        y = self.denormalize_y(action.args["y"])
        press_enter = action.args.get("press_enter", False)
        clear_before_typing = action.args.get("clear_before_typing", True)
        return await self._browser_computer.type_text_at(
          x=x,
          y=y,
          text=action.args["text"],
          press_enter=press_enter,
          clear_before_typing=clear_before_typing,
        )

      case "scroll_document":
        magnitude = action.args.get("magnitude", 300)
        return await self._browser_computer.scroll_document(action.args["direction"], magnitude)

      case "scroll_at":
        x = self.denormalize_x(action.args["x"])
        y = self.denormalize_y(action.args["y"])
        magnitude = action.args.get("magnitude", 300)
        direction = action.args["direction"]

        if direction in ("up", "down"):
          magnitude = self.denormalize_y(magnitude)
        elif direction in ("left", "right"):
          magnitude = self.denormalize_x(magnitude)
        else:
          raise ValueError(f"Unknown direction: {direction}")
        return await self._browser_computer.scroll_at(
          x=x, y=y, direction=direction, magnitude=magnitude
        )

      case "wait_5_seconds":
        return await self._browser_computer.wait_5_seconds()

      case "go_back":
        return await self._browser_computer.go_back()

      case "go_forward":
        return await self._browser_computer.go_forward()

      case "search":
        return await self._browser_computer.search()

      case "navigate":
        return await self._browser_computer.navigate(action.args["url"])

      case "key_combination":
        return await self._browser_computer.key_combination(action.args["keys"].split("+"))

      case "drag_and_drop":
        x = self.denormalize_x(action.args["x"])
        y = self.denormalize_y(action.args["y"])
        destination_x = self.denormalize_x(action.args["destination_x"])
        destination_y = self.denormalize_y(action.args["destination_y"])
        return await self._browser_computer.drag_and_drop(
          x=x,
          y=y,
          destination_x=destination_x,
          destination_y=destination_y,
        )

      case _ if action.name in self._custom_tools_by_name:
        (_, custom_fn) = self._custom_tools_by_name[action.name]
        args = convert_number_values_for_dict_function_call_args(action.args)
        return await invoke_function_from_dict_args_async(args, custom_fn)

      case _:
        raise ValueError(f"Unsupported function: {action.name}")

  async def get_model_response(
    self, max_retries: int = 5, base_delay_s: int = 1
  ) -> GenerateContentResponse:
    # Lazy init for client/config to avoid destructor issues when unused
    self._ensure_client_and_config()
    for attempt in range(max_retries):
      try:
        assert self._client is not None
        assert self._generate_content_config is not None
        # Use async client for native async/await support (uses aiohttp internally)
        response = await self._client.aio.models.generate_content(
          model=self._model_name,
          contents=cast(ContentListUnionDict, self._contents),
          config=self._generate_content_config,
        )
        return cast(GenerateContentResponse, response)  # Return response on success
      except Exception as e:
        print(self._with_agent_prefix(str(e)))
        if attempt < max_retries - 1:
          delay = base_delay_s * (2**attempt)
          message = (
            f"Generating content failed on attempt {attempt + 1}. Retrying in {delay} seconds...\n"
          )
          activity_log().agent(self._agent_label).warning(message.strip())
          await asyncio.sleep(delay)
        else:
          message = f"Generating content failed after {max_retries} attempts.\n"
          activity_log().agent(self._agent_label).failure(message.strip())
          raise

    # This line should never be reached because the exception is always raised on the last attempt
    raise AssertionError("Unreachable code: all retries should have either returned or raised")

  def get_text(self, candidate: Candidate) -> str | None:
    """Extracts the text from the candidate."""
    if not candidate.content or not candidate.content.parts:
      return None
    text: list[str] = []
    for part in candidate.content.parts:
      if part.text:
        text.append(part.text)
    return " ".join(text) or None

  def extract_function_calls(self, candidate: Candidate) -> list[FunctionCall]:
    """Extracts the function call from the candidate."""
    if not candidate.content or not candidate.content.parts:
      return []
    ret: list[FunctionCall] = []
    for part in candidate.content.parts:
      if part.function_call:
        ret.append(part.function_call)
    return ret

  async def run_one_iteration(self) -> LoopStatus:
    self._turn_index += 1

    # Generate a response from the model.
    with console.status(self._with_agent_prefix("Generating response from Gemini Computer Use...")):
      response = await self.get_model_response()

    if not response.candidates:
      print(self._with_agent_prefix("Response has no candidates!"))
      print(response)
      raise ValueError("Empty response")

    # Extract the text and function call from the response.
    candidate = response.candidates[0]
    # Append the model turn to conversation history.
    if candidate.content:
      self._contents.append(candidate.content)

    reasoning = self.get_text(candidate)
    function_calls = self.extract_function_calls(candidate)

    # Retry the request in case of malformed FCs.
    if (
      not function_calls
      and not reasoning
      and candidate.finish_reason == FinishReason.MALFORMED_FUNCTION_CALL
    ):
      return LoopStatus.CONTINUE

    if not function_calls:
      print(self._with_agent_prefix(f"Agent Loop Complete: {reasoning}"))
      self.final_reasoning = reasoning
      return LoopStatus.COMPLETE

    function_call_strs: list[str] = []
    for function_call in function_calls:
      # Print the function call and any reasoning.
      function_call_str = f"Name: {function_call.name}"
      if function_call.args:
        function_call_str += "\nArgs:"
        for key, value in function_call.args.items():
          function_call_str += f"\n  {key}: {value}"
      function_call_strs.append(function_call_str)

    table = Table(expand=True)
    table.add_column("Gemini Computer Use Reasoning", header_style="magenta", ratio=1)
    table.add_column("Function Call(s)", header_style="cyan", ratio=1)
    table.add_row(reasoning, "\n".join(function_call_strs))
    if self._verbose:
      activity_log().print_reasoning(
        label=self._output_label, turn_index=self._turn_index, table=table
      )

    function_responses: list[FunctionResponse] = []
    for function_call in function_calls:
      extra_fr_fields: dict[str, str] = {}
      if function_call.args and (safety_obj := function_call.args.get("safety_decision")):
        # Type narrow the safety object to SafetyDecision
        if isinstance(safety_obj, dict):
          safety = cast(SafetyDecision, safety_obj)
          decision = self._get_safety_confirmation(safety)
          if decision == "TERMINATE":
            print(self._with_agent_prefix("Terminating agent loop"))
            return LoopStatus.COMPLETE
          # Explicitly mark the safety check as acknowledged.
          extra_fr_fields["safety_acknowledgement"] = "true"
      if self._verbose:
        with console.status(self._with_agent_prefix("Sending command to Computer...")):
          fc_result = await self.handle_action(function_call)
      else:
        fc_result = await self.handle_action(function_call)

      # Handle EnvState responses from computer use functions
      if isinstance(fc_result, EnvState):
        env_state = cast(EnvState, fc_result)
        # Render the screenshot in the terminal using term-image
        img_enabled = os.environ.get("GEMINI_SUPPLY_IMG_ENABLE", "1").strip().lower()
        show_img = img_enabled not in ("0", "false", "no")

        if show_img:
          activity_log().show_screenshot(
            label=self._output_label,
            action_name=(function_call.name or ""),
            url=env_state.url,
            png_bytes=env_state.screenshot,
          )
        function_responses.append(
          FunctionResponse(
            name=function_call.name,
            response={
              "url": env_state.url,
              **extra_fr_fields,
            },
            parts=[
              FunctionResponsePart(
                inline_data=FunctionResponseBlob(mime_type="image/png", data=env_state.screenshot)
              )
            ],
          )
        )
      # Handle custom function responses (Pydantic models)
      else:
        # fc_result is a Pydantic model; convert to dict at SDK boundary
        assert isinstance(fc_result, BaseModel), f"Expected BaseModel, got {type(fc_result)}"
        function_responses.append(
          FunctionResponse(name=function_call.name, response=fc_result.model_dump())
        )

    self._contents.append(
      Content(
        role="user",
        parts=[Part(function_response=fr) for fr in function_responses],
      )
    )

    # only keep screenshots in the few most recent turns, remove the screenshot images from the old turns.
    turn_with_screenshots_found = 0
    for content in reversed(self._contents):
      if content.role == "user" and content.parts:
        # check if content has screenshot of the predefined computer use functions.
        has_screenshot = False
        for part in content.parts:
          if (
            part.function_response
            and part.function_response.parts
            and part.function_response.name in PREDEFINED_COMPUTER_USE_FUNCTIONS
          ):
            has_screenshot = True
            break

        if has_screenshot:
          turn_with_screenshots_found += 1
          # remove the screenshot image if the number of screenshots exceed the limit.
          if turn_with_screenshots_found > MAX_RECENT_TURN_WITH_SCREENSHOTS:
            for part in content.parts:
              if (
                part.function_response
                and part.function_response.parts
                and part.function_response.name in PREDEFINED_COMPUTER_USE_FUNCTIONS
              ):
                part.function_response.parts = None

    return LoopStatus.CONTINUE

  def _get_safety_confirmation(self, safety: SafetyDecision) -> Literal["CONTINUE", "TERMINATE"]:
    """Prompts user for safety confirmation when required by the model."""
    if safety["decision"] != "require_confirmation":
      raise ValueError(f"Unknown safety decision: {safety['decision']}")
    activity_log().agent(self._agent_label).warning(
      "Safety service requires explicit confirmation!"
    )
    print(self._with_agent_prefix(safety["explanation"]))
    user_decision = ""
    while user_decision.lower() not in ("y", "n", "ye", "yes", "no"):
      user_decision = input(self._with_agent_prefix("Do you wish to proceed? [Yes]/[No]\n"))
    if user_decision.lower() in ("n", "no"):
      return "TERMINATE"
    return "CONTINUE"

  async def agent_loop(self) -> None:
    """Runs the main agent loop until completion."""
    status: LoopStatus = LoopStatus.CONTINUE
    while status == LoopStatus.CONTINUE:
      status = await self.run_one_iteration()

  async def close(self) -> None:
    """Close the underlying Gemini client if initialized."""
    try:
      await self._client.aio.aclose()
    except Exception:
      pass
    try:
      self._client.close()
    except Exception:
      pass

  def denormalize_x(self, x: int | float) -> int:
    """Denormalizes x coordinate from 1000-based system to actual screen width."""
    screen = self._browser_computer.screen_size()
    return int(x / 1000 * screen.width)

  def denormalize_y(self, y: int | float) -> int:
    """Denormalizes y coordinate from 1000-based system to actual screen height."""
    screen = self._browser_computer.screen_size()
    return int(y / 1000 * screen.height)
