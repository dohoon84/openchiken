"""
OpenChiken Telegram 채널
─────────────────────────
python-telegram-bot 기반 채널 어댑터.

핸들러는 InboundEvent를 생성해 channels/router.py의 route_message()에 위임합니다.
채널 특화 커맨드(/start, /briefing, /weekly)는 어댑터에서 직접 처리합니다.
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from channels.base import ChannelAdapter
from channels.router import InboundEvent, parse_command, route_message
from config.settings import settings
from scheduler.jobs import job_morning_briefing, job_weekly_briefing

logger = logging.getLogger(__name__)

MAX_LEN = 4096

_STATUS_MESSAGES = [
    "⏳ 처리 중이에요...",
    "🔍 스킬을 확인하고 있어요...",
    "⚙️ 조금만 기다려 주세요...",
    "📡 데이터를 가져오고 있어요...",
    "🧠 답변을 작성하고 있어요...",
    "✍️ 거의 다 됐어요...",
]

_SLOW_RESPONSE_THRESHOLD = 3  # 이 시간(초) 이내 완료되면 상태 메시지 표시 안 함


class TelegramAdapter(ChannelAdapter):
    """Telegram 채널 어댑터."""

    channel_name = "telegram"

    def build_app(self, post_init=None, post_shutdown=None) -> Application:
        """핸들러가 등록된 Telegram Application을 생성합니다."""
        builder = Application.builder().token(settings.telegram_bot_token)
        if post_init:
            builder = builder.post_init(post_init)
        if post_shutdown:
            builder = builder.post_shutdown(post_shutdown)

        app = builder.build()
        app.add_handler(CommandHandler("start", self._start_command))
        app.add_handler(CommandHandler("clear", self._command_handler))
        app.add_handler(CommandHandler("plan", self._command_handler))
        app.add_handler(CommandHandler("tasks", self._command_handler))
        app.add_handler(CommandHandler("run", self._command_handler))
        app.add_handler(CommandHandler("apps", self._command_handler))
        app.add_handler(CommandHandler("briefing", self._briefing_command))
        app.add_handler(CommandHandler("weekly", self._weekly_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._message_handler))
        return app

    async def start(self) -> None:
        raise NotImplementedError("Telegram은 main.py에서 build_app() + run_polling()으로 시작합니다.")

    async def send_message(self, session_id: str, text: str) -> None:
        raise NotImplementedError("Telegram은 scheduler.jobs에서 bot.send_message()로 직접 전송합니다.")

    # ── 핸들러 헬퍼 ───────────────────────────────────────────────────────────

    def _make_event(
        self,
        user_id: str,
        text: str,
        command: str | None = None,
        args: str = "",
    ) -> InboundEvent:
        return InboundEvent(
            channel=self.channel_name,
            session_id=self.make_session_id(user_id),
            user_id=user_id,
            text=text,
            command=command,
            args=args,
        )

    async def _reply(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        event: InboundEvent,
    ) -> None:
        chat_id = update.effective_chat.id
        status_msg = None

        async def _keep_alive() -> None:
            """_SLOW_RESPONSE_THRESHOLD 초 후에도 완료 안 되면 상태 메시지 표시 및 갱신."""
            nonlocal status_msg
            try:
                await asyncio.sleep(_SLOW_RESPONSE_THRESHOLD)
                status_msg = await update.message.reply_text(_STATUS_MESSAGES[0])
                idx = 0
                while True:
                    await asyncio.sleep(6)
                    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                    idx += 1
                    label = _STATUS_MESSAGES[min(idx, len(_STATUS_MESSAGES) - 1)]
                    try:
                        await status_msg.edit_text(label)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        keep_alive_task = asyncio.create_task(_keep_alive())

        try:
            reply = await route_message(event)
        except Exception:
            logger.exception("route_message error for user %s", event.user_id)
            reply = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        finally:
            keep_alive_task.cancel()
            if status_msg:
                try:
                    await status_msg.delete()
                except Exception:
                    pass

        for chunk in self.split_message(reply, MAX_LEN):
            await update.message.reply_text(chunk)

    # ── 커맨드 핸들러 ─────────────────────────────────────────────────────────

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not self.is_authorised(str(user.id)):
            await update.message.reply_text("접근이 허용되지 않은 사용자입니다.")
            return
        await update.message.reply_text(
            "안녕하세요! OpenChiken AI 비서입니다.\n\n"
            "저에게 무엇이든 물어보세요:\n"
            "- 이메일 확인/전송\n"
            "- 오늘 일정 확인 및 등록\n"
            "- 웹 검색 및 날씨 조회\n"
            "- 메모 저장/불러오기\n"
            "- 복잡한 다단계 작업 자동화\n\n"
            "명령어:\n"
            "/start    - 시작 메시지\n"
            "/clear    - 대화 기록 초기화\n"
            "/briefing - 지금 바로 아침 브리핑\n"
            "/weekly   - 이번 주 일정 브리핑\n"
            "/tasks    - 진행 중인 작업 목록\n"
            "/plan <요청> - 복잡한 작업을 단계별로 계획하고 실행"
        )

    async def _command_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """/clear, /plan, /tasks 처리."""
        user = update.effective_user
        if not self.is_authorised(str(user.id)):
            await update.message.reply_text("접근이 허용되지 않은 사용자입니다.")
            return

        raw = update.message.text or ""
        cmd_word = raw.split()[0].lstrip("/").lower()
        args = " ".join(context.args) if context.args else ""

        command = cmd_word if cmd_word in {"clear", "plan", "tasks"} else None
        event = self._make_event(str(user.id), raw, command=command, args=args)
        await self._reply(update, context, event)

    async def _briefing_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self.is_authorised(str(update.effective_user.id)):
            return
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await job_morning_briefing(context.bot)

    async def _weekly_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not self.is_authorised(str(update.effective_user.id)):
            return
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action=ChatAction.TYPING
        )
        await job_weekly_briefing(context.bot)

    async def _message_handler(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        user = update.effective_user
        if not self.is_authorised(str(user.id)):
            await update.message.reply_text("접근이 허용되지 않은 사용자입니다.")
            return

        text = update.message.text or ""
        logger.info("Message from %s (id=%s): %s", user.full_name, user.id, text[:80])
        cmd, args = parse_command(text)
        event = self._make_event(str(user.id), text, command=cmd, args=args)
        await self._reply(update, context, event)
