# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a browser automation agent using Google's Gemini Computer Use API. The agent can execute natural language queries to control a web browser through two environment backends: Playwright (local) and Browserbase (remote).

## Setup and Configuration

### Environment Setup
This project uses `uv` for dependency management and builds.

```bash
# Install dependencies using uv
uv sync

# Install Playwright browser dependencies
uv run playwright install-deps chrome
uv run playwright install chrome
```

### API Configuration

**For Gemini Developer API:**
```bash
export GEMINI_API_KEY="YOUR_API_KEY"
```

**For Vertex AI:**
```bash
export USE_VERTEXAI=true
export VERTEXAI_PROJECT="your-project-id"
export VERTEXAI_LOCATION="your-location"
```

**For Browserbase (optional):**
```bash
export BROWSERBASE_API_KEY="your-api-key"
export BROWSERBASE_PROJECT_ID="your-project-id"
```

## Running the Agent

### Basic Usage
```bash
# Run with Playwright (local browser)
uv run gemini-supply --query="Go to Google and type 'Hello World'" --env="playwright"

# Run with Browserbase (remote browser)
uv run gemini-supply --query="Your query here" --env="browserbase"

# Run with custom initial URL
uv run gemini-supply --query="Your query" --env="playwright" --initial_url="https://example.com"

# Enable mouse highlighting for debugging
uv run gemini-supply --query="Your query" --env="playwright" --highlight_mouse

# Use a different model
uv run gemini-supply --query="Your query" --model="gemini-2.5-computer-use-preview-10-2025"
```

### Running in Headless Mode
```bash
export PLAYWRIGHT_HEADLESS=1
uv run gemini-supply --query="Your query" --env="playwright"
```

## Development Commands

### Code Quality
```bash
# Run Ruff linter
uv run ruff check .

# Run Ruff formatter
uv run ruff format .

# Fix auto-fixable lint issues
uv run ruff check --fix .
```

### Testing
```bash
# Run all tests
uv run pytest

# Run tests with verbose output
uv run pytest -v
```

## Architecture

### Core Components

**`agent.py` - BrowserAgent**
- Main orchestration layer for the agent loop
- Handles communication with Gemini API
- Manages conversation history and screenshots
- Translates function calls to computer actions
- Implements coordinate denormalization (Gemini uses 1000x1000 normalized coordinates)
- Screenshot retention: keeps only last 3 turns with screenshots to manage context size

**`computers/computer.py` - Computer (Abstract Base)**
- Defines the interface for browser environments
- All actions return `EnvState` (screenshot + URL)
- Actions include: click, hover, type, scroll, navigate, key combinations, drag-and-drop

**`computers/playwright_computer.py` - PlaywrightComputer**
- Local browser automation using Playwright
- Implements all Computer interface methods
- Handles new page/tab interception (model only supports single tab)
- Optional mouse highlighting for debugging
- Key mapping for cross-platform compatibility

**`display.py` - Screenshot Display**
- Displays screenshots in terminal using Kitty graphics protocol
- Called automatically after each browser action
- Uses base64 encoding and Kitty escape sequences for inline image display

**`main.py` - CLI Entry Point**
- Parses command-line arguments
- Initializes appropriate Computer implementation
- Creates BrowserAgent and runs agent loop

### Agent Loop Flow

1. User query sent to Gemini model with current conversation history
2. Model responds with reasoning and/or function calls
3. Function calls are executed via Computer interface
4. Screenshots are displayed in terminal using Kitty graphics protocol
5. Results (screenshot + URL) added to conversation history
6. Loop continues until model completes task (no more function calls)

### Coordinate System

- Gemini API uses normalized 1000x1000 coordinate space
- Agent denormalizes to actual screen dimensions in `denormalize_x()` and `denormalize_y()`
- Default screen size: 1440x900 (configurable via `PLAYWRIGHT_SCREEN_SIZE`)

### Custom Functions

To add custom tool functions beyond predefined computer use actions:

1. Define function with proper TypedDict return type in `agent.py` (e.g., `multiply_numbers` returns `MultiplyResult`)
2. Add the return type to the `FunctionResponseT` union type
3. Add to `custom_functions` list in `BrowserAgent.__init__()` using `FunctionDeclaration.from_callable()`
4. Add handler case in `BrowserAgent.handle_action()`

**Important**: All custom functions must return typed dictionaries (TypedDict), never `dict[str, object]` or `Any`.

### Safety Confirmations

The agent includes safety decision handling using typed `SafetyDecision` objects. If the model returns a `safety_decision` requiring confirmation:
- User is prompted to proceed or terminate
- Acknowledgement is passed back to the model

## Key Implementation Details

- **Single tab limitation**: The model only supports one browser tab. New page requests are intercepted and redirected to current page.
- **Screenshot management**: Only the 3 most recent turns with screenshots are retained in conversation history to manage token usage.
- **Screenshot display**: Screenshots are automatically displayed in the terminal after each action using Kitty graphics protocol (requires Kitty terminal).
- **Retry logic**: Model requests retry on failures with exponential backoff (max 5 attempts).
- **Load state waiting**: All browser actions wait for page load state before taking screenshots.
- **Manual sleep**: A 0.5s sleep is added after load state to ensure rendering completes.
- **Type safety**: The codebase enforces strict typing - never use `Any` or `dict[str, object]` for function returns.

## Documentation Guidelines

When creating or updating documentation:

- **Describe, don't spell out**: Document component behavior, responsibilities, and interfaces rather than providing complete code listings
- **No full-file code examples**: Implementors don't need code spelled out. Focus on:
  - What the component does
  - Key methods and their signatures
  - Important data structures and types
  - Interactions with other components
  - Configuration options and behavior
- **Keep code snippets minimal**: Only show code when illustrating a specific pattern or non-obvious implementation detail
- **Use structured descriptions**: Bullet points, tables, and short paragraphs over long code blocks
- **Focus on architecture**: Help readers understand how pieces fit together, not how to write the code

## Environment Variables Reference

| Variable | Purpose | Required |
|----------|---------|----------|
| `GEMINI_API_KEY` | Gemini API authentication | Yes (unless using Vertex AI) |
| `USE_VERTEXAI` | Enable Vertex AI client | No (default: false) |
| `VERTEXAI_PROJECT` | Vertex AI project ID | Yes (if using Vertex AI) |
| `VERTEXAI_LOCATION` | Vertex AI location | Yes (if using Vertex AI) |
| `BROWSERBASE_API_KEY` | Browserbase authentication | Yes (if using Browserbase) |
| `BROWSERBASE_PROJECT_ID` | Browserbase project ID | Yes (if using Browserbase) |
| `PLAYWRIGHT_HEADLESS` | Run Playwright headless | No (default: false) |
