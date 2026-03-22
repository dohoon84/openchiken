from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from config.settings import settings
from core.memory import load_history_messages, save_message
from core.provider import get_provider
from skills import get_skill_loader

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_SYSTEM_PROMPT_BASE = """당신은 '{assistant_name}'이라는 이름의 개인 AI 비서입니다.

## 현재 시간
{current_datetime} (한국 표준시, KST)

## 페르소나
{assistant_persona}

## 말투
{assistant_tone}

## 역할
- 사용자의 일정, 이메일, 정보 검색 등을 도와주는 개인 비서입니다.
- 항상 한국어로 답변합니다.
- 작업 결과를 간결하고 명확하게 보고합니다.

## 대화 기억
- SQLite 기반 대화 기록으로 이전 세션 내용도 기억합니다 (최근 20개 메시지).
- 사용자가 '/clear'를 입력하기 전까지 대화 흐름을 유지합니다.
- 이전 대화의 문맥(이름, 날짜, 주제 등)을 반드시 활용하여 답변하세요.
- "세션이 끊기면 기억 못 한다"는 답변은 사실이 아닙니다.

## 일반 규칙
- 민감한 작업(이메일 전송, 일정 삭제)은 수행 전에 요약을 보여주고 확인을 요청하세요.
- 모르는 정보는 추측하지 말고 도구로 확인하세요.
{assistant_extra_section}
## 사용 가능한 스킬 및 도구

{skill_instructions}
"""


# ── 캐시 ──────────────────────────────────────────────────────────────────────

_tools_cache: list | None = None
_skill_instructions_cache: str | None = None


def _load_skills() -> tuple[list, str]:
    """스킬 로더로 도구와 지시 텍스트를 불러옵니다 (첫 호출 시 캐시)."""
    global _tools_cache, _skill_instructions_cache

    if _tools_cache is not None and _skill_instructions_cache is not None:
        return _tools_cache, _skill_instructions_cache

    loader = get_skill_loader()
    skills = loader.load_all()

    tools: list = []
    instructions_parts: list[str] = []

    for skill in skills:
        tools.extend(skill.tools)
        if skill.instructions:
            instructions_parts.append(skill.instructions.strip())

    _tools_cache = tools
    _skill_instructions_cache = "\n\n---\n\n".join(instructions_parts)

    logger.info(
        "Skills loaded: %d skills, %d tools",
        len(skills),
        len(tools),
    )
    return _tools_cache, _skill_instructions_cache


def get_tools() -> list:
    tools, _ = _load_skills()
    return tools


# ── ReAct 에이전트 ──────────────────────────────────────────────────────────────

_agent = None


def get_agent():
    global _agent
    if _agent is None:
        llm = get_provider().get_model()
        _agent = create_react_agent(llm, get_tools())
    return _agent


# ── Plan-and-Execute 에이전트 ───────────────────────────────────────────────────

_plan_graph = None


def get_plan_graph():
    global _plan_graph
    if _plan_graph is None:
        from core.planner import build_plan_execute_graph
        _plan_graph = build_plan_execute_graph(get_tools())
    return _plan_graph


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    _, skill_instructions = _load_skills()
    now = datetime.now(KST)
    extra = settings.assistant_extra.strip()
    extra_section = f"\n## 추가 지침\n{extra}\n" if extra else ""
    return _SYSTEM_PROMPT_BASE.format(
        assistant_name=settings.assistant_name,
        assistant_persona=settings.assistant_persona,
        assistant_tone=settings.assistant_tone,
        assistant_extra_section=extra_section,
        current_datetime=now.strftime("%Y년 %m월 %d일 %H시 %M분 (%A)"),
        skill_instructions=skill_instructions or "(로드된 스킬 없음)",
    )


# ── 재시도 헬퍼 ─────────────────────────────────────────────────────────────────

async def _invoke_with_retry(agent, messages: list, max_retries: int = 2) -> dict:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await agent.ainvoke({"messages": messages})
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(
                    "Agent invocation failed (attempt %d/%d), retrying in %ds: %s",
                    attempt + 1, max_retries + 1, wait, e,
                )
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


# ── Public API ─────────────────────────────────────────────────────────────────

async def chat(session_id: str, user_message: str) -> str:
    """ReAct 에이전트로 사용자 메시지를 처리합니다."""
    agent = get_agent()

    history = load_history_messages(session_id)
    system_prompt = _build_system_prompt()
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=user_message)]

    save_message(session_id, HumanMessage(content=user_message))

    try:
        result = await _invoke_with_retry(agent, messages)
    except Exception as e:
        logger.error("chat() failed after retries: %s", e, exc_info=True)
        reply = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        save_message(session_id, AIMessage(content=reply))
        return reply

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
    reply = ai_messages[-1].content if ai_messages else "죄송합니다, 응답을 생성하지 못했습니다."

    save_message(session_id, AIMessage(content=reply))
    return reply


async def chat_plan(session_id: str, user_message: str) -> str:
    """Plan-and-Execute 에이전트로 복잡한 다단계 요청을 처리합니다."""
    graph = get_plan_graph()

    save_message(session_id, HumanMessage(content=user_message))

    try:
        state = await graph.ainvoke({
            "input": user_message,
            "plan": [],
            "past_steps": [],
            "response": "",
        })
        reply = state.get("response") or "작업이 완료되었지만 최종 응답을 생성하지 못했습니다."
    except Exception as e:
        logger.error("chat_plan() failed: %s", e, exc_info=True)
        reply = f"복잡 작업 처리 중 오류가 발생했습니다: {e}"
        state = {}

    past = state.get("past_steps", []) if state else []
    if past:
        steps_summary = "\n".join(f"  {i+1}. {s}" for i, (s, _) in enumerate(past))
        logger.info("chat_plan completed %d steps:\n%s", len(past), steps_summary)

    save_message(session_id, AIMessage(content=reply))
    return reply


async def chat_plan_with_tools(session_id: str, user_message: str, tools: list) -> str:
    """필터링된 툴 세트로 Plan-and-Execute 에이전트를 실행합니다.

    전체 툴 캐시 대신 필요한 스킬의 툴만 전달하여
    LLM 컨텍스트 크기와 API 비용을 줄입니다.

    Args:
        session_id:   대화 세션 ID
        user_message: 실행할 쿼리
        tools:        사용할 툴 목록 (get_tools_for_skills()로 필터링된 것)
    """
    from core.planner import build_plan_execute_graph

    graph = build_plan_execute_graph(tools)
    save_message(session_id, HumanMessage(content=user_message))

    try:
        state = await graph.ainvoke({
            "input": user_message,
            "plan": [],
            "past_steps": [],
            "response": "",
        })
        reply = state.get("response") or "작업이 완료되었지만 최종 응답을 생성하지 못했습니다."
    except Exception as e:
        logger.error("chat_plan_with_tools() failed: %s", e, exc_info=True)
        reply = f"복잡 작업 처리 중 오류가 발생했습니다: {e}"
        state = {}

    past = state.get("past_steps", []) if state else []
    if past:
        steps_summary = "\n".join(f"  {i+1}. {s}" for i, (s, _) in enumerate(past))
        logger.info(
            "chat_plan_with_tools completed %d steps (%d tools used):\n%s",
            len(past), len(tools), steps_summary,
        )

    save_message(session_id, AIMessage(content=reply))
    return reply
