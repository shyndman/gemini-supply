#!/usr/bin/env -S uv run
"""Send a Telegram message using generative-supply config.

The message text is passed as a positional argument and sent verbatim,
without any escaping or modification.

Usage:
  ./send_telegram_message.py "Your message here"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests
import requests.exceptions

from generative_supply.config import AppConfig, load_config


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Send a Telegram message using generative-supply config.",
  )
  parser.add_argument(
    "message",
    help="The message text to send (sent verbatim, no escaping)",
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=None,
    help="Path to config.yaml (defaults to generative-supply standard location)",
  )
  parser.add_argument(
    "--timeout",
    type=float,
    default=10.0,
    help="HTTP timeout in seconds (default: 10)",
  )
  parser.add_argument(
    "--parse-mode",
    choices=["Markdown", "MarkdownV2", "HTML", "plain"],
    default="MarkdownV2",
    help="Parse mode for the message (default: MarkdownV2)",
  )
  return parser


def _load_app_config(path: Path | None) -> AppConfig:
  try:
    return load_config(path)
  except Exception as exc:
    print(f"failed to load config: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc


def _send_telegram_message(
  bot_token: str,
  chat_id: int,
  message: str,
  parse_mode: str | None,
  timeout: float,
) -> None:
  url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
  payload: dict[str, str | int] = {
    "chat_id": chat_id,
    "text": message,
  }
  if parse_mode is not None and parse_mode != "plain":
    payload["parse_mode"] = parse_mode

  try:
    response = requests.post(
      url,
      json=payload,
      timeout=timeout,
    )
    response.raise_for_status()
  except requests.exceptions.RequestException as exc:
    print(f"request failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

  print(f"Message sent successfully to chat {chat_id}")


def main() -> None:
  parser = _build_parser()
  args = parser.parse_args()

  cfg = _load_app_config(args.config)

  bot_token = cfg.preferences.telegram.bot_token
  chat_id = cfg.preferences.telegram.chat_id

  _send_telegram_message(
    bot_token=bot_token,
    chat_id=chat_id,
    message=args.message,
    parse_mode=args.parse_mode,
    timeout=args.timeout,
  )


if __name__ == "__main__":
  main()
