import logging
import logfire
from libsh import setup_logging_from_env


def setup_logging() -> None:
  setup_logging_from_env()

  """Configure logging for the application."""
  # Suppress all logging from third-party libraries
  logging.getLogger("playwright-captcha").setLevel(logging.CRITICAL)
  logfire.configure(console=logfire.ConsoleOptions(verbose=True))
  logfire.instrument_httpx()
  logfire.instrument_pydantic_ai()
