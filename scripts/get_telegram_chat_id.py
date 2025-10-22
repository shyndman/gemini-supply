#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "requests",
# ]
# ///
"""Quick script to get a Telegram group's chat ID.

Usage:
1. Add your bot to the group
2. Send a message in the group (mention the bot or just send any message)
3. Run this script with your bot token:
   ./get_telegram_chat_id.py YOUR_BOT_TOKEN
"""

import sys

import requests


def get_chat_id(bot_token: str) -> None:
  url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
  response = requests.get(url, timeout=10)
  response.raise_for_status()

  data = response.json()

  if not data.get("ok"):
    print(f"Error: {data}")
    return

  updates = data.get("result", [])
  if not updates:
    print("No updates found. Make sure:")
    print("1. The bot is added to the group")
    print("2. A message has been sent in the group recently")
    return

  print("\nFound chat IDs:\n")
  seen_chats: set[int] = set()

  for update in updates:
    chat = None
    if "message" in update:
      chat = update["message"].get("chat")
    elif "channel_post" in update:
      chat = update["channel_post"].get("chat")

    if chat and chat["id"] not in seen_chats:
      seen_chats.add(chat["id"])
      chat_type = chat.get("type", "unknown")
      chat_title = chat.get("title", chat.get("username", "N/A"))
      print(f"Chat ID: {chat['id']}")
      print(f"  Type: {chat_type}")
      print(f"  Title: {chat_title}")
      print()


if __name__ == "__main__":
  if len(sys.argv) != 2:
    print("Usage: ./get_telegram_chat_id.py YOUR_BOT_TOKEN")
    sys.exit(1)

  bot_token = sys.argv[1]
  get_chat_id(bot_token)
