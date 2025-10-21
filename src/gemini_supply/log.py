from __future__ import annotations

import logging


def setup_logging() -> None:
  """Configure logging for the application."""
  # Suppress all logging from third-party libraries
  logging.disable(logging.CRITICAL)


__all__ = ["setup_logging"]
