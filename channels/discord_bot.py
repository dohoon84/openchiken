"""
OpenChiken Discord 채널
────────────────────────
discord.py 기반 채널 어댑터.

필요한 Discord Bot 설정:
  1. discord.com/developers/applications → New Application
  2. Bot 탭 → Token 복사 → DISCORD_BOT_TOKEN 환경변수에 설정
  3. Privileged Gateway Intents → Message Content Intent ON
  4. OAuth2 → URL Generator: bot 권한 선택 후 초대 URL 생성

지원 이벤트:
  DM        — 봇과의 1:1 다이렉트 메시지
  @멘션     — 서버 채널에서 @봇이름 멘션
"""

from __future__ import annotations

import logging

import discord

from channels.base import ChannelAdapter
from channels.router import InboundEvent, parse_command, route_message
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_LEN = 2000  # Discord 메시지 최대 길이


class DiscordAdapter(ChannelAdapter):
    """Discord 채널 어댑터."""

    channel_name = "discord"

    def __init__(self) -> None:
        self._client: discord.Client | None = None

    async def start(self) -> None:
        """Discord 봇을 시작합니다."""
        intents = discord.Intents.default()
        intents.message_content = True  # Privileged Intent 필수

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            logger.info("Discord bot online: %s (id=%s)", client.user, client.user.id)

        @client.event
        async def on_message(message: discord.Message) -> None:
            if message.author == client.user:
                return

            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in message.mentions

            if not is_dm and not is_mention:
                return

            user_id = str(message.author.id)
            if not self.is_authorised(user_id):
                await message.channel.send("접근이 허용되지 않은 사용자입니다.")
                return

            # 멘션 태그 제거
            text = message.content
            for user in message.mentions:
                text = text.replace(f"<@{user.id}>", "").replace(f"<@!{user.id}>", "")
            text = text.strip()
            if not text:
                return

            logger.info("Discord %s (id=%s): %s", message.author, user_id, text[:80])
            cmd, args = parse_command(text)
            event = InboundEvent(
                channel=self.channel_name,
                session_id=self.make_session_id(user_id),
                user_id=user_id,
                text=text,
                command=cmd,
                args=args,
            )

            async with message.channel.typing():
                try:
                    reply = await route_message(event)
                except Exception:
                    logger.exception("Discord route_message error for user %s", user_id)
                    reply = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

            for chunk in self.split_message(reply, MAX_LEN):
                await message.channel.send(chunk)

        logger.info("Discord bot starting...")
        await client.start(settings.discord_bot_token)

    async def send_message(self, session_id: str, text: str) -> None:
        raise NotImplementedError("Discord 능동 전송은 아직 구현되지 않았습니다.")
