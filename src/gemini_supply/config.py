from __future__ import annotations

from pathlib import Path
from typing import TypedDict


DEFAULT_CONFIG_PATH = Path("~/.config/gemini-supply/config.yaml").expanduser()


class _ShoppingListCfg(TypedDict, total=False):
  provider: str


class _HACfg(TypedDict, total=False):
  url: str
  token: str


class AppConfig(TypedDict, total=False):
  shopping_list: _ShoppingListCfg
  home_assistant: _HACfg
  postal_code: str
  concurrency: int


def load_config(path: Path | None) -> AppConfig | None:
  """Load config YAML if present.

  Returns None if file missing or YAML cannot be parsed.
  """
  p = (path or DEFAULT_CONFIG_PATH).expanduser()
  if not p.exists():
    return None
  try:
    import yaml  # type: ignore[reportMissingImports]
  except Exception:
    # No hard dependency; treat as absent config
    return None
  try:
    raw = p.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
      return None
    # Coerce
    cfg: AppConfig = AppConfig()
    sl = data.get("shopping_list", {})
    if isinstance(sl, dict):
      cfg["shopping_list"] = _ShoppingListCfg(provider=str(sl.get("provider", "")).strip())
    ha = data.get("home_assistant", {})
    if isinstance(ha, dict):
      cfg["home_assistant"] = _HACfg(
        url=str(ha.get("url", "")).strip(),
        token=str(ha.get("token", "")).strip(),
      )
    pc = data.get("postal_code", "")
    if isinstance(pc, str) and pc.strip():
      cfg["postal_code"] = pc.strip()
    conc = data.get("concurrency")
    try:
      if isinstance(conc, int) and conc >= 1:
        cfg["concurrency"] = int(conc)
    except Exception:
      pass
    return cfg
  except Exception:
    return None
