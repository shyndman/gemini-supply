from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PROFILE = Path("~/.config/generative-supply/camoufox-profile")
ENV_PROFILE = "GENERATIVE_SUPPLY_USER_DATA_DIR"


def resolve_profile_dir() -> Path:
  """Resolve the Camoufox persistent profile directory (Linux-only).

  Order of precedence:
  - GENERATIVE_SUPPLY_USER_DATA_DIR environment variable, if set
  - Default path: ~/.config/generative-supply/camoufox-profile

  Ensures the directory exists.
  """
  env = os.environ.get(ENV_PROFILE, "").strip()
  path = Path(env).expanduser() if env else DEFAULT_PROFILE.expanduser()
  path.mkdir(parents=True, exist_ok=True)
  return path


def resolve_camoufox_exec() -> Path:
  """Resolve the Camoufox executable path using `python -m camoufox path`.

  The module returns the root Camoufox directory; the binary lives directly under
  it and has the same name.

  Raises RuntimeError if the executable cannot be determined.
  """
  try:
    proc = subprocess.run(
      [sys.executable, "-m", "camoufox", "path"],
      check=True,
      capture_output=True,
      text=True,
    )
    root = proc.stdout.strip()
    if not root:
      raise RuntimeError("Camoufox path query returned empty output")
    rp = Path(root).expanduser()
    if rp.is_dir():
      # Normalize to the executable path: <root>/<name>
      rp = rp / rp.name
    if not rp.exists():
      raise RuntimeError(f"Resolved Camoufox executable does not exist: {rp}")
    return rp
  except Exception as e:  # noqa: BLE001
    raise RuntimeError(
      "Failed to resolve Camoufox executable. Ensure camoufox is installed and available"
    ) from e
