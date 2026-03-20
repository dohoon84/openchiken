"""
OpenChiken Slack 채널
─────────────────────
Slack Bolt (Socket Mode) 기반 채널 어댑터.

필요한 Slack App 권한(Bot Token Scopes):
  app_mentions:read, chat:write, im:history, im:read, im:write

이벤트 구독:
  app_mention   — 채널에서 @봇이름 멘션
  message.im    — DM 메시지
"""

from __future__ import annotations

import logging
import re

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from channels.base import ChannelAdapter
from channels.router import InboundEvent, parse_command, route_message
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_LEN = 3000


class SlackAdapter(ChannelAdapter):
    """Slack 채널 어댑터."""

    channel_name = "slack"

    def __init__(self) -> None:
        self._handler: AsyncSocketModeHandler | None = None

    async def start(self) -> None:
        """Slack 봇을 Socket Mode로 시작합니다."""
        app = self._build_app()
        self._handler = AsyncSocketModeHandler(app, settings.slack_app_token)
        logger.info("Slack bot (Socket Mode) starting...")
        await self._handler.start_async()

    async def send_message(self, session_id: str, text: str) -> None:
        raise NotImplementedError("Slack 능동 전송은 아직 구현되지 않았습니다.")

    # ── 앱 빌더 ──────────────────────────────────────────────────────────────

    def _build_app(self) -> AsyncApp:
        app = AsyncApp(token=settings.slack_bot_token)

        @app.event("message")
        async def handle_dm(event: dict, say) -> None:
            """DM 메시지 처리."""
            if event.get("channel_type") != "im" or event.get("subtype"):
                return
            user_id = event.get("user", "")
            text: str = event.get("text", "").strip()
            if not text or not user_id:
                return
            if not self.is_authorised(user_id):
                await say("접근이 허용되지 않은 사용자입니다.")
                return
            await self._dispatch(user_id, text, say)

        @app.event("app_mention")
        async def handle_mention(event: dict, say) -> None:
            """채널에서 @봇이름 멘션 처리."""
            user_id = event.get("user", "")
            raw_text: str = event.get("text", "")
            text = re.sub(r"<@\w+>", "", raw_text).strip()
            if not text or not user_id:
                return
            if not self.is_authorised(user_id):
                await say("접근이 허용되지 않은 사용자입니다.")
                return
            await self._dispatch(user_id, text, say)

        return app

    # ── 공통 디스패치 ─────────────────────────────────────────────────────────

    async def _dispatch(self, user_id: str, text: str, say) -> None:
        cmd, args = parse_command(text)
        event = InboundEvent(
            channel=self.channel_name,
            session_id=self.make_session_id(user_id),
            user_id=user_id,
            text=text,
            command=cmd,
            args=args,
        )
        logger.info("Slack %s: %s", user_id, text[:80])
        try:
            reply = await route_message(event)
        except Exception:
            logger.exception("Slack route_message error for user %s", user_id)
            reply = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        for chunk in self.split_message(reply, MAX_LEN):
            await say(chunk)
