"""Shared pytest fixtures and configuration for all tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def enable_headless_mode(monkeypatch: pytest.MonkeyPatch) -> None:
  """Force headless mode for all browser-based tests across the entire suite."""
  monkeypatch.setenv("PLAYWRIGHT_HEADLESS", "1")
