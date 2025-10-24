import logging
import logfire


def setup_logging() -> None:
  """Configure logging for the application."""
  # Suppress all logging from third-party libraries
  logging.getLogger("playwright-captcha").setLevel(logging.CRITICAL)
  logfire.configure(console=logfire.ConsoleOptions(verbose=True))
  logfire.instrument_httpx()
  logfire.instrument_pydantic_ai()
