"""
OpenChiken Channel Adapter Base
────────────────────────────────
모든 채널 어댑터가 구현해야 하는 추상 기반 클래스.

새 채널을 추가하는 방법:
  1. ChannelAdapter를 상속받아 channel_name, start(), send_message() 구현
  2. channels/__init__.py의 CHANNEL_REGISTRY에 이름과 팩토리 등록
  3. ENABLED_CHANNELS 환경변수에 채널 이름 추가
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from config.settings import settings


class ChannelAdapter(ABC):
    """채널 어댑터 추상 기반 클래스."""

    channel_name: str  # 서브클래스에서 반드시 정의

    def make_session_id(self, user_id: str) -> str:
        """채널 네임스페이스가 포함된 세션 ID를 생성합니다. 예: 'telegram_123456'"""
        return f"{self.channel_name}_{user_id}"

    def is_authorised(self, user_id: str) -> bool:
        """허용 사용자 목록을 확인합니다. 빈 목록이면 모든 사용자를 허용합니다."""
        allowed = settings.allowed_user_ids
        if not allowed:
            return True
        try:
            return int(user_id) in allowed
        except (ValueError, TypeError):
            return False

    def split_message(self, text: str, max_len: int) -> list[str]:
        """텍스트를 플랫폼 최대 길이에 맞게 분할합니다."""
        if len(text) <= max_len:
            return [text]
        chunks: list[str] = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks

    @abstractmethod
    async def start(self) -> None:
        """채널 봇을 시작합니다. 봇이 종료될 때까지 블록합니다."""
        ...

    @abstractmethod
    async def send_message(self, session_id: str, text: str) -> None:
        """특정 세션(사용자)에게 메시지를 전송합니다."""
        ...
