"""
OpenChiken Channel Registry
────────────────────────────
ENABLED_CHANNELS 설정에 따라 채널 어댑터를 동적으로 로드합니다.

새 채널 등록:
  1. ChannelAdapter를 상속받는 어댑터 클래스를 channels/<name>_bot.py에 구현
  2. 아래 CHANNEL_REGISTRY에 이름과 팩토리 함수를 추가
  3. .env의 ENABLED_CHANNELS에 채널 이름을 추가
"""

from __future__ import annotations

import logging
from typing import Callable

from channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


def _make_telegram() -> ChannelAdapter:
    from channels.telegram_bot import TelegramAdapter
    return TelegramAdapter()


def _make_slack() -> ChannelAdapter:
    from channels.slack_bot import SlackAdapter
    return SlackAdapter()


def _make_discord() -> ChannelAdapter:
    from channels.discord_bot import DiscordAdapter
    return DiscordAdapter()


def _make_imessage() -> ChannelAdapter:
    from channels.imessage_bot import IMessageAdapter
    return IMessageAdapter()


# 새 채널은 이 딕셔너리에 이름: 팩토리 형식으로 추가합니다.
CHANNEL_REGISTRY: dict[str, Callable[[], ChannelAdapter]] = {
    "telegram": _make_telegram,
    "slack": _make_slack,
    "discord": _make_discord,
    "imessage": _make_imessage,
}


def load_channels(names: list[str]) -> list[ChannelAdapter]:
    """이름 목록으로 채널 어댑터 인스턴스를 생성합니다."""
    adapters: list[ChannelAdapter] = []
    for name in names:
        key = name.strip().lower()
        factory = CHANNEL_REGISTRY.get(key)
        if factory is None:
            logger.warning(
                "알 수 없는 채널: '%s'. 건너뜁니다. 지원 채널: %s",
                name, list(CHANNEL_REGISTRY),
            )
            continue
        try:
            adapter = factory()
            adapters.append(adapter)
            logger.info("채널 로드됨: %s", key)
        except Exception:
            logger.exception("채널 '%s' 로드 실패", key)
    return adapters
