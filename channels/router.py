"""
OpenChiken Channel Router
─────────────────────────
모든 채널의 공통 라우팅 로직.
채널 어댑터는 InboundEvent를 만들어 route_message()에 위임합니다.

지원 커맨드:
  plan  — Plan-and-Execute 에이전트로 복잡한 다단계 요청 처리
  clear — 대화 기록 초기화 (한글 별칭 포함)
  tasks — 진행 중인 작업 목록 조회
  그 외  — ReAct 에이전트로 일반 대화
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from core.agent import chat, chat_plan
from core.memory import clear_history

logger = logging.getLogger(__name__)

_CLEAR_ALIASES = frozenset({"/clear", "clear", "대화 초기화", "기록 초기화", "초기화"})


@dataclass
class InboundEvent:
    channel: str        # "telegram" | "slack" | "discord" | ...
    session_id: str     # ChannelAdapter.make_session_id() 결과
    user_id: str        # 플랫폼 원본 유저 ID
    text: str           # 정제된 메시지 본문
    command: str | None  # "plan" | "clear" | "tasks" | None
    args: str = field(default="")  # command 이후 나머지 텍스트


def parse_command(text: str) -> tuple[str | None, str]:
    """텍스트에서 커맨드와 나머지 인자를 추출합니다.

    반환값: (command, args)
      - command: "plan" | "clear" | "tasks" | None
      - args: 커맨드 이후 나머지 텍스트 (command가 None이면 원본 text 그대로)
    """
    stripped = text.strip()
    if stripped.lower() in _CLEAR_ALIASES:
        return "clear", ""

    match = re.match(r"^/?(plan|tasks)(?:\s+(.*))?$", stripped, re.IGNORECASE | re.DOTALL)
    if match:
        cmd = match.group(1).lower()
        args = (match.group(2) or "").strip()
        return cmd, args

    return None, stripped


async def route_message(event: InboundEvent) -> str:
    """InboundEvent를 받아 적절한 에이전트로 라우팅하고 응답 텍스트를 반환합니다."""
    logger.info(
        "[%s] user=%s command=%s text=%.80s",
        event.channel, event.user_id, event.command, event.text,
    )

    match event.command:
        case "clear":
            clear_history(event.session_id)
            return "대화 기록이 초기화되었습니다."

        case "plan":
            if not event.args:
                return (
                    "사용법: /plan <복잡한 요청>\n\n"
                    "예시:\n"
                    "- /plan 이번 주 미팅 관련 이메일을 모두 찾아서 요약해줘\n"
                    "- /plan 오늘 날씨 확인하고 야외 일정 있으면 메모해줘"
                )
            return await chat_plan(event.session_id, event.args)

        case "tasks":
            return await chat(event.session_id, "작업 목록을 보여줘 (task_list 도구 사용)")

        case _:
            return await chat(event.session_id, event.text)
