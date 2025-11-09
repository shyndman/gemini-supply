from logging import FATAL, getLogger

from libsh import setup_logging_from_env
from structlog import get_logger


def setup_logging() -> None:
  """Configure logging for the application."""
  setup_logging_from_env()
  get_logger().info("Logging initialized from environment")

  getLogger("google_genai.models").setLevel(FATAL)
  getLogger("apscheduler").setLevel(FATAL)
  getLogger("httpx").setLevel(FATAL)
  getLogger("telegram").setLevel(FATAL)
