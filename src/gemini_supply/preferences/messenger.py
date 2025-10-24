from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import TypeAlias, cast

from pydantic.types import NegativeInt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
  Application,
  ApplicationBuilder,
  CallbackContext,
  CallbackQueryHandler,
  ExtBot,
  JobQueue,
  MessageHandler,
  filters,
)
from telegram.helpers import escape_markdown

from .types import ProductChoice, ProductChoiceRequest, ProductDecision


@dataclass(slots=True)
class TelegramSettings:
  bot_token: str
  chat_id: NegativeInt
  nag_interval: timedelta


@dataclass(slots=True)
class PendingRequest:
  request_id: int
  request: ProductChoiceRequest
  future: asyncio.Future[ProductDecision]
  message_id: int
  nag_job_id: str


BotType = ExtBot[None]
UserDataDict: TypeAlias = dict[int, object]
ChatDataDict: TypeAlias = dict[int, object]
BotDataDict: TypeAlias = dict[str, object]
CallbackContextType: TypeAlias = CallbackContext[BotType, UserDataDict, ChatDataDict, BotDataDict]
JobQueueType: TypeAlias = JobQueue[CallbackContextType]
ApplicationType: TypeAlias = Application[
  BotType,
  CallbackContextType,
  UserDataDict,
  ChatDataDict,
  BotDataDict,
  JobQueueType,
]


class TelegramPreferenceMessenger:
  """Bridges preference prompts to Telegram using python-telegram-bot."""

  def __init__(
    self,
    settings: TelegramSettings,
    nag_strings: Sequence[str],
  ) -> None:
    self._settings = settings
    self._nag_strings = nag_strings
    self._application: ApplicationType | None = None
    self._pending: PendingRequest | None = None
    self._condition = asyncio.Condition()
    self._next_request_id = 1

  async def start(self) -> None:
    if self._application is not None:
      return
    app = cast(
      ApplicationType,
      ApplicationBuilder().token(self._settings.bot_token).concurrent_updates(False).build(),
    )
    app.add_handler(CallbackQueryHandler(self._handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
    await app.initialize()
    await app.start()
    updater = app.updater
    if updater is None:
      raise RuntimeError("telegram application did not provide an updater")
    await updater.start_polling()
    self._application = app

  async def stop(self) -> None:
    app = self._application
    if app is None:
      return
    updater = app.updater
    if updater is not None:
      await updater.stop()
    await app.stop()
    await app.shutdown()
    self._application = None

  async def request_choice(self, request: ProductChoiceRequest) -> ProductDecision:
    if self._application is None:
      raise RuntimeError("TelegramPreferenceMessenger.start() must be called before use.")
    async with self._condition:
      while self._pending is not None:
        await self._condition.wait()
      loop = asyncio.get_running_loop()
      future: asyncio.Future[ProductDecision] = loop.create_future()
      request_id = self._next_request_id
      self._next_request_id += 1
      message_id = await self._send_prompt(request)
      nag_job_id = self._schedule_nag(request_id)
      self._pending = PendingRequest(
        request_id=request_id,
        request=request,
        future=future,
        message_id=message_id,
        nag_job_id=nag_job_id,
      )
    try:
      result = await future
      return result
    finally:
      self._cancel_nag(nag_job_id)
      async with self._condition:
        self._pending = None
        self._condition.notify_all()

  async def _send_prompt(self, request: ProductChoiceRequest) -> int:
    app = self._application
    assert app is not None
    bot: BotType = app.bot
    lines: list[str] = []
    lines.append(f"*{escape_markdown(request.category_label, version=2)}*")
    lines.append(f"_List entry:_ {escape_markdown(request.original_text, version=2)}")
    lines.append("")
    lines.append("Reply with a number, tap a button, type a different product, or send `skip`.")
    lines.append("Use a ⭐ button (or prefix like `⭐3`) to remember the choice as default.")
    lines.append("Titles, prices, and links are shown for each option.")
    lines.append("")
    buttons: list[list[InlineKeyboardButton]] = []
    for idx, choice in enumerate(request.choices, start=1):
      block = self._format_choice_block(idx, choice)
      lines.extend(block)
      lines.append("")
      buttons.append(
        [
          InlineKeyboardButton(
            text=str(idx),
            callback_data=f"select:{idx}",
          ),
          InlineKeyboardButton(
            text=f"⭐ {idx}",
            callback_data=f"default:{idx}",
          ),
        ]
      )
    buttons.append([InlineKeyboardButton(text="Skip", callback_data="skip")])
    keyboard = InlineKeyboardMarkup(buttons)
    if lines and lines[-1] == "":
      lines.pop()
    message: Message = await bot.send_message(
      chat_id=self._settings.chat_id,
      text="\n".join(lines),
      parse_mode=ParseMode.MARKDOWN_V2,
      reply_markup=keyboard,
      disable_notification=True,
    )
    return message.message_id

  def _format_choice_block(self, idx: int, choice: ProductChoice) -> list[str]:
    title = escape_markdown(choice.title or f"Option {idx}", version=2)
    block: list[str] = [f"{idx}. *{title}*"]
    price_display = self._choice_price_display(choice)
    if price_display is not None:
      block.append("   Price: `" + escape_markdown(price_display, version=2) + "`")
    # if choice.url:
    #   safe_url = escape_markdown(f"{choice.url}", version=2)
    #   block.append(f"   [View Product]({safe_url})")
    return block

  @staticmethod
  def _choice_price_display(choice: ProductChoice) -> str | None:
    if choice.price_text is not None:
      trimmed = choice.price_text.strip()
      if trimmed:
        return trimmed
    if choice.price_cents is not None and choice.price_cents >= 0:
      return f"${choice.price_cents / 100:.2f}"
    return None

  def _format_acknowledgement(self, status: str, choice: ProductChoice) -> str:
    title_raw = choice.title
    title = title_raw.strip() if isinstance(title_raw, str) else "Selected choice"
    if not title:
      title = "Selected choice"
    escaped_title = escape_markdown(title, version=2)
    price_display = self._choice_price_display(choice)
    if price_display is not None:
      escaped_price = escape_markdown(price_display, version=2)
      return f"{status} *{escaped_title}* - `{escaped_price}`"
    return f"{status} *{escaped_title}*"

  def _schedule_nag(self, request_id: int) -> str:
    app = self._application
    assert app is not None
    job_queue = app.job_queue
    if job_queue is None:
      raise RuntimeError("Telegram application is missing a job queue")
    job_queue = cast(JobQueueType, job_queue)
    job_name = f"preference-nag-{request_id}"
    job_queue.run_repeating(
      self._send_nag,
      interval=self._settings.nag_interval,
      first=self._settings.nag_interval,
      data=request_id,
      name=job_name,
    )
    return job_name

  def _cancel_nag(self, job_name: str) -> None:
    app = self._application
    if app is None or app.job_queue is None:
      return
    job_queue = cast(JobQueueType, app.job_queue)
    job = job_queue.get_jobs_by_name(job_name)
    for j in job:
      j.schedule_removal()

  async def _send_nag(self, context: CallbackContextType) -> None:
    if self._pending is None:
      return
    if context.job is None or context.job.data != self._pending.request_id:
      return
    app = self._application
    assert app is not None
    bot: BotType = app.bot
    message = random.choice(self._nag_strings)
    await bot.send_message(
      chat_id=self._settings.chat_id,
      text=f"{message}\nReply with a number, product, or `skip`.",
      disable_notification=True,
    )

  async def _handle_callback(self, update: Update, context: CallbackContextType) -> None:
    query = update.callback_query
    if not query:
      return
    await query.answer()
    pending = self._pending
    if pending is None:
      return
    msg = query.message
    if msg is None or msg.chat is None or msg.chat.id != self._settings.chat_id:
      return
    raw_data = (query.data or "").strip()
    lowered = raw_data.lower()
    if lowered == "skip":
      result = ProductDecision(
        decision="skip",
        selected_index=None,
        selected_choice=None,
        make_default=False,
      )
      await self._resolve_pending(result)
      await context.bot.send_message(
        chat_id=self._settings.chat_id,
        text="👍 Skip recorded.",
        disable_notification=True,
      )
      return
    is_default = False
    idx_text: str | None = None
    if lowered.startswith("select:"):
      idx_text = lowered.split(":", 1)[1]
    elif lowered.startswith("default:"):
      idx_text = lowered.split(":", 1)[1]
      is_default = True
    elif lowered.isdigit():
      idx_text = lowered
    if not idx_text:
      return
    try:
      idx = int(idx_text)
    except ValueError:
      return
    choices = pending.request.choices
    if idx < 1 or idx > len(choices):
      return
    option = choices[idx - 1]
    result = ProductDecision(
      decision="selected",
      selected_index=idx,
      selected_choice=option,
      make_default=is_default,
    )
    await self._resolve_pending(result)
    ack_status = "✅ Default set" if is_default else "✅ Noted"
    ack_message = self._format_acknowledgement(ack_status, option)
    await context.bot.send_message(
      chat_id=self._settings.chat_id,
      text=ack_message,
      parse_mode=ParseMode.MARKDOWN_V2,
      disable_notification=True,
    )

  async def _handle_message(self, update: Update, context: CallbackContextType) -> None:
    pending = self._pending
    if pending is None:
      return
    message = update.message
    if not message or not message.text:
      return
    chat = message.chat
    if chat is None or chat.id != self._settings.chat_id:
      return
    text = message.text.strip()
    if not text:
      return
    lowered = text.lower()
    if lowered == "skip":
      result = ProductDecision(
        decision="skip",
        selected_index=None,
        selected_choice=None,
        make_default=False,
      )
      await self._resolve_pending(result)
      await context.bot.send_message(
        chat_id=self._settings.chat_id,
        text="👍 Skip recorded.",
        disable_notification=True,
      )
      return
    parsed = self._parse_selection_text(text, len(pending.request.choices))
    if parsed is not None:
      idx, is_default = parsed
      choice = pending.request.choices[idx - 1]
      result = ProductDecision(
        decision="selected",
        selected_index=idx,
        selected_choice=choice,
        make_default=is_default,
      )
      await self._resolve_pending(result)
      ack_status = "✅ Default set" if is_default else "✅ Noted"
      ack_message = self._format_acknowledgement(ack_status, choice)
      await context.bot.send_message(
        chat_id=self._settings.chat_id,
        text=ack_message,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_notification=True,
      )
      return
    result = ProductDecision(
      decision="alternate",
      selected_index=None,
      selected_choice=None,
      alternate_text=text,
      make_default=False,
    )
    await self._resolve_pending(result)
    await context.bot.send_message(
      chat_id=self._settings.chat_id,
      text="✍️ Got it—trying that alternative.",
      disable_notification=True,
    )

  async def _resolve_pending(self, result: ProductDecision) -> None:
    pending = self._pending
    if pending is None:
      return
    if not pending.future.done():
      pending.future.set_result(result)
    app = self._application
    if app is not None:
      try:
        await app.bot.edit_message_reply_markup(
          chat_id=self._settings.chat_id,
          message_id=pending.message_id,
          reply_markup=None,
        )
      except Exception:
        pass

  def _parse_selection_text(self, text: str, choice_count: int) -> tuple[int, bool] | None:
    collapsed = text.strip()
    if not collapsed:
      return None
    cleaned = collapsed.replace(" ", "")
    is_default = False
    lowered = cleaned.lower()
    if lowered.startswith("default"):
      is_default = True
      cleaned = cleaned[7:]
    elif lowered.startswith("star"):
      is_default = True
      cleaned = cleaned[4:]
    if cleaned.startswith(":"):
      cleaned = cleaned[1:]
    while cleaned.startswith("⭐") or cleaned.startswith("*"):
      is_default = True
      cleaned = cleaned[1:]
    while cleaned.endswith("⭐") or cleaned.endswith("*"):
      is_default = True
      cleaned = cleaned[:-1]
    if not cleaned or not cleaned.isdigit():
      return None
    idx = int(cleaned)
    if idx < 1 or idx > choice_count:
      return None
    return idx, is_default
