from libsh import setup_logging_from_env
from structlog import get_logger


def setup_logging() -> None:
  """Configure logging for the application."""
  setup_logging_from_env()
  get_logger().info("Logging initialized from environment")
  _setup_logging_dependencies()


def _setup_logging_dependencies() -> None:
  import logging
  import logfire

  # Suppress all logging from third-party libraries
  logging.getLogger("playwright-captcha").setLevel(logging.CRITICAL)
  # Configure logfire to get their tendrils into some of our deps
  logfire.configure(console=logfire.ConsoleOptions(verbose=True))
  logfire.instrument_httpx()
  logfire.instrument_pydantic_ai()
