from __future__ import annotations

# agent.py exports
from gemini_supply.agent import (
  BrowserAgent,
  CustomFunctionCallable,
  FunctionResponseT,
  MAX_RECENT_TURN_WITH_SCREENSHOTS,
  PREDEFINED_COMPUTER_USE_FUNCTIONS,
  SafetyDecision,
  report_item_added,
  report_item_not_found,
  request_preference_choice,
)

# auth.py exports
from gemini_supply.auth import (
  SHORT_FENCE_TYPE,
  SHORT_FENCE_WAIT_MS,
  AuthCredentials,
  AuthManager,
  AuthenticationError,
  build_camoufox_options,
)

# cli.py exports
from gemini_supply.cli import PLAYWRIGHT_SCREEN_SIZE, Cli, Shop, run

# config.py exports
from gemini_supply.config import (
  DEFAULT_CONFIG_PATH,
  DEFAULT_PREFERENCES_PATH,
  AppConfig,
  HomeAssistantShoppingListConfig,
  PreferencesConfig,
  PreferencesTelegramConfig,
  ShoppingListConfig,
  YAMLShoppingListConfig,
  load_config,
)

# display.py exports
from gemini_supply.display import display_image_kitty

# log.py exports
from gemini_supply.log import TTYLogger, setup_logging

# profile.py exports
from gemini_supply.profile import (
  DEFAULT_PROFILE,
  ENV_PROFILE,
  resolve_camoufox_exec,
  resolve_profile_dir,
)

__all__ = [
  # agent.py
  "BrowserAgent",
  "CustomFunctionCallable",
  "FunctionResponseT",
  "MAX_RECENT_TURN_WITH_SCREENSHOTS",
  "PREDEFINED_COMPUTER_USE_FUNCTIONS",
  "SafetyDecision",
  "report_item_added",
  "report_item_not_found",
  "request_preference_choice",
  # auth.py
  "SHORT_FENCE_TYPE",
  "SHORT_FENCE_WAIT_MS",
  "AuthCredentials",
  "AuthManager",
  "AuthenticationError",
  "build_camoufox_options",
  # cli.py
  "Cli",
  "PLAYWRIGHT_SCREEN_SIZE",
  "Shop",
  "run",
  # config.py
  "DEFAULT_CONFIG_PATH",
  "DEFAULT_PREFERENCES_PATH",
  "AppConfig",
  "HomeAssistantShoppingListConfig",
  "PreferencesConfig",
  "PreferencesTelegramConfig",
  "ShoppingListConfig",
  "YAMLShoppingListConfig",
  "load_config",
  # display.py
  "display_image_kitty",
  # log.py
  "TTYLogger",
  "setup_logging",
  # profile.py
  "DEFAULT_PROFILE",
  "ENV_PROFILE",
  "resolve_camoufox_exec",
  "resolve_profile_dir",
]
