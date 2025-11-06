from libsh import setup_logging_from_env
from structlog import get_logger


def setup_logging() -> None:
  """Configure logging for the application."""
  setup_logging_from_env()
  get_logger().info("Logging initialized from environment")
  _setup_logging_dependencies()


def _setup_logging_dependencies() -> None: ...
