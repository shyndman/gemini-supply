from __future__ import annotations

import asyncio

import termcolor

from gemini_supply import AuthManager, build_camoufox_options
from gemini_supply.computers import CamoufoxHost
from gemini_supply import resolve_camoufox_exec, resolve_profile_dir

PLAYWRIGHT_SCREEN_SIZE = (1440, 900)


async def run() -> None:
  profile_dir = resolve_profile_dir()
  camoufox_exec = resolve_camoufox_exec()
  termcolor.cprint(f"Using profile: {profile_dir}", color="cyan")

  async with CamoufoxHost(
    screen_size=PLAYWRIGHT_SCREEN_SIZE,
    user_data_dir=profile_dir,
    initial_url="https://www.metro.ca",
    highlight_mouse=True,
    enforce_restrictions=False,
    executable_path=camoufox_exec,
    headless="virtual",
    camoufox_options=build_camoufox_options(),
  ) as host:
    manager = AuthManager(host)
    await manager.ensure_authenticated(force=True)
    termcolor.cprint(
      "Authentication complete. Credentials persisted in the profile.", color="green"
    )


def main() -> int:
  try:
    asyncio.run(run())
    return 0
  except KeyboardInterrupt:
    termcolor.cprint("\nInterrupted by user.", color="yellow")
    return 130
  except Exception:
    raise


if __name__ == "__main__":
  raise SystemExit(main())
