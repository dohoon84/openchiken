"""
OpenChiken Channel Router
─────────────────────────
모든 채널의 공통 라우팅 로직.
채널 어댑터는 InboundEvent를 만들어 route_message()에 위임합니다.

모든 일반 메시지는 자율 오케스트레이터(run_autonomous)로 처리됩니다.
오케스트레이터는 쿼리에서 필요 스킬을 파악하고, 로컬에 없으면
허브(dohoon84/skill-hub)에서 자동 설치하거나 LLM이 직접 생성합니다.

지원 커맨드:
  clear — 대화 기록 초기화 (한글 별칭 포함)
  tasks — 진행 중인 작업 목록 조회
  그 외  — 자율 오케스트레이터 (스킬 자동 탐색 → 허브 설치 → LLM 생성 → 실행)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from core.agent import chat
from core.memory import clear_history

logger = logging.getLogger(__name__)

_CLEAR_ALIASES = frozenset({"/clear", "clear", "대화 초기화", "기록 초기화", "초기화"})


@dataclass
class InboundEvent:
    channel: str        # "telegram" | "slack" | "discord" | ...
    session_id: str     # ChannelAdapter.make_session_id() 결과
    user_id: str        # 플랫폼 원본 유저 ID
    text: str           # 정제된 메시지 본문
    command: str | None  # "clear" | "tasks" | "run" | None
    args: str = field(default="")  # command 이후 나머지 텍스트


def parse_command(text: str) -> tuple[str | None, str]:
    """텍스트에서 커맨드와 나머지 인자를 추출합니다.

    반환값: (command, args)
      - command: "clear" | "tasks" | "run" | None
      - args: 커맨드 이후 나머지 텍스트 (command가 None이면 원본 text 그대로)
    """
    stripped = text.strip()
    if stripped.lower() in _CLEAR_ALIASES:
        return "clear", ""

    match = re.match(r"^/?tasks(?:\s+(.*))?$", stripped, re.IGNORECASE | re.DOTALL)
    if match:
        return "tasks", (match.group(1) or "").strip()

    # /run <app_name> [추가 컨텍스트]
    match = re.match(r"^/?run\s+(\S+)(?:\s+(.*))?$", stripped, re.IGNORECASE | re.DOTALL)
    if match:
        app_name = match.group(1).strip()
        extra = (match.group(2) or "").strip()
        return "run", f"{app_name} {extra}".strip()

    # /apps — 설치된 앱 목록
    match = re.match(r"^/?apps$", stripped, re.IGNORECASE)
    if match:
        return "apps", ""

    return None, stripped


async def route_message(event: InboundEvent) -> str:
    """InboundEvent를 받아 적절한 에이전트로 라우팅하고 응답 텍스트를 반환합니다.

    일반 메시지는 자율 오케스트레이터를 통해 처리됩니다.
    오케스트레이터가 필요 스킬을 파악하고, 없는 스킬은 허브 또는 LLM으로 자동 확보합니다.

    /run <app_name> [컨텍스트] — APP.md steps 기반 결정론적 앱 실행
    /apps — 설치된 앱 목록 조회
    """
    logger.info(
        "[%s] user=%s command=%s text=%.80s",
        event.channel, event.user_id, event.command, event.text,
    )

    match event.command:
        case "clear":
            clear_history(event.session_id)
            return "대화 기록이 초기화되었습니다."

        case "tasks":
            return await chat(event.session_id, "작업 목록을 보여줘 (task_list 도구 사용)")

        case "run":
            # args = "<app_name> [extra_context]"
            parts = event.args.split(None, 1)
            app_name = parts[0] if parts else ""
            extra_context = parts[1] if len(parts) > 1 else ""
            if not app_name:
                return "사용법: /run <앱 이름> [추가 컨텍스트]\n예: /run btc_daily_advisor"
            try:
                from core.orchestrator import run_app
                return await run_app(app_name, session_id=event.session_id, extra_context=extra_context)
            except ValueError as e:
                from skills import get_skill_loader
                loader = get_skill_loader()
                app_names = [a.name for a in loader.load_apps()]
                apps_str = ", ".join(app_names) if app_names else "(없음)"
                return f"❌ {e}\n설치된 앱 목록: {apps_str}"

        case "apps":
            from skills import get_skill_loader
            loader = get_skill_loader()
            apps = loader.load_apps()
            if not apps:
                return "설치된 앱이 없습니다.\n앱 허브에서 다운로드하세요."
            lines = ["📱 설치된 앱 목록\n"]
            for a in apps:
                sched = f" ⏰ {a.schedule}" if a.schedule else ""
                kw = f" 🔑 [{', '.join(a.trigger_keywords[:3])}]" if a.trigger_keywords else ""
                lines.append(f"• /run {a.name}{sched}{kw}\n  {a.description}")
            lines.append("\n사용법: /run <앱 이름>")
            return "\n".join(lines)

        case _:
            # trigger_keywords 기반 자동 앱 매칭 시도
            from core.orchestrator import find_matching_app, run_autonomous, run_app
            matched_app = await find_matching_app(event.text)
            if matched_app:
                logger.info("Auto-triggering app '%s' for query: %.60s", matched_app, event.text)
                return await run_app(matched_app, session_id=event.session_id, extra_context=event.text)

            # 일반 메시지 → 자율 오케스트레이터
            return await run_autonomous(event.text, event.session_id)
