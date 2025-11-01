"""Shared pytest fixtures and configuration for all tests."""

from __future__ import annotations

import pytest

from gemini_supply.term import ActivityLog, set_activity_log


@pytest.fixture(autouse=True)
def enable_headless_mode(monkeypatch: pytest.MonkeyPatch) -> None:
  """Force headless mode for all browser-based tests across the entire suite."""
  monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "1")


@pytest.fixture(autouse=True)
def setup_activity_log() -> None:
  """Set up activity log context for all tests."""
  log = ActivityLog()
  set_activity_log(log)
