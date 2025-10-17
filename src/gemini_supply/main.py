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
import argparse
import asyncio
from pathlib import Path

from gemini_supply.agent import BrowserAgent
from gemini_supply.computers import PlaywrightComputer
from gemini_supply.grocery_main import run_shopping

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


async def main() -> int:
  parser = argparse.ArgumentParser(description="Run the browser agent with a query.")
  parser.add_argument("--query", type=str, help="General query for the browser agent.")
  parser.add_argument(
    "--list",
    type=str,
    help="Path to a shopping list YAML file for grocery mode.",
  )

  parser.add_argument(
    "--env",
    type=str,
    choices="playwright",
    default="playwright",
    help="The computer use environment to use.",
  )
  parser.add_argument(
    "--initial_url",
    type=str,
    default="https://www.google.com",
    help="The inital URL loaded for the computer.",
  )
  parser.add_argument(
    "--highlight_mouse",
    action="store_true",
    default=False,
    help="If possible, highlight the location of the mouse.",
  )
  parser.add_argument(
    "--model",
    default="gemini-2.5-computer-use-preview-10-2025",
    help="Set which main model to use.",
  )
  args = parser.parse_args()

  # Grocery mode: run orchestrator if --list is provided.
  if args.list:
    return await run_shopping(
      list_path=Path(args.list).expanduser(),
      model_name=args.model,
      highlight_mouse=args.highlight_mouse,
      screen_size=PLAYWRIGHT_SCREEN_SIZE,
    )

  if not args.query:
    parser.error("--query is required when not using --list")

  async with PlaywrightComputer(
    screen_size=PLAYWRIGHT_SCREEN_SIZE,
    initial_url=args.initial_url,
    highlight_mouse=args.highlight_mouse,
  ) as browser_computer:
    agent = BrowserAgent(
      browser_computer=browser_computer,
      query=args.query,
      model_name=args.model,
    )
    await agent.agent_loop()
  return 0


if __name__ == "__main__":
  asyncio.run(main())
