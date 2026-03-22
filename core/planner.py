from __future__ import annotations

"""Plan-and-Execute agent using LangGraph.

Flow:
  planner → executor → replanner → (end | executor → ...)

- planner   : LLM generates an ordered list of concrete steps.
- executor  : ReAct sub-agent executes the *current* step using all tools.
- replanner : LLM decides whether all goals are met (→ final answer) or
              updates the remaining plan (→ next executor round).
"""

import logging
import operator
from functools import partial
from typing import Annotated, List, Tuple, Union

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from config.settings import settings

logger = logging.getLogger(__name__)

MAX_STEPS = 10  # 무한 루프 방지


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class Plan(BaseModel):
    steps: List[str] = Field(description="순서대로 실행할 단계 목록 (구체적이고 실행 가능하게)")


class FinalResponse(BaseModel):
    response: str = Field(
        description=(
            "사용자에게 전달할 최종 답변. "
            "도구가 반환한 실제 데이터(목록, 수치, URL 등)를 그대로 포함해야 합니다. "
            "절대 '알려드렸습니다', '조회했습니다' 같은 메타 표현으로 대체하지 마세요."
        )
    )


class Act(BaseModel):
    action: Union[FinalResponse, Plan] = Field(
        description="모든 목표 달성 시 FinalResponse, 아직 남은 작업이 있으면 Plan"
    )


# ── LangGraph state ───────────────────────────────────────────────────────────

class PlanExecuteState(TypedDict, total=False):
    """LangGraph state for the Plan-and-Execute graph."""
    input: str
    plan: List[str]
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    response: str


# ── Prompts ───────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """당신은 복잡한 요청을 실행 가능한 단계로 분해하는 계획 전문가입니다.

규칙:
- 각 단계는 하나의 명확한 작업이어야 합니다.
- 도구(이메일, 캘린더, 웹 검색, 메모 등)를 활용할 수 있는 형태로 작성하세요.
- 불필요한 단계는 생략하고, 최소한의 단계로 목표를 달성하세요.
- 각 단계는 한 문장으로 작성하세요.
- 이메일 내용을 읽거나 요약해야 할 때는 '목록 조회'와 '내용 읽기'를 별도 단계로 나누지 말고, gmail_read_latest 도구를 사용하는 단일 단계로 합치세요.
- 한 단계의 결과로 얻은 ID나 식별자가 다음 단계에서 필요한 구조는 가능하면 피하세요."""

_EXECUTOR_SYSTEM = """당신은 주어진 단 하나의 단계를 실행하는 실행자입니다.

규칙:
- 제시된 단계만 실행하세요. 다른 단계는 건드리지 마세요.
- 사용 가능한 도구를 적극 활용하세요.
- 실행 결과를 간결하게 보고하세요.
- 도구 호출이 실패하면, 대안적인 방법을 시도하고 그 결과를 보고하세요.
- 도구에서 반환된 메시지 ID, URL, 고유 식별자 등의 값은 결과에 **정확히 그대로** 포함하세요. 후속 단계에서 필요할 수 있습니다.
- 특히 이메일 목록 조회 시, 각 메시지의 실제 ID를 결과에 반드시 나열하세요. (예: ID: 18d1234abcdef567)"""

_REPLANNER_SYSTEM = """당신은 진행 중인 계획을 검토하고 다음 행동을 결정하는 전문가입니다.

다음 중 하나를 반환하세요:
1. FinalResponse: 원래 목표가 완전히 달성된 경우 → 사용자에게 전달할 최종 답변
2. Plan: 아직 남은 작업이 있는 경우 → 업데이트된 남은 단계 목록

FinalResponse 작성 규칙:
- 완료된 단계의 결과에 포함된 실제 데이터(동영상 목록, 이메일 내용, 수치, URL 등)를 그대로 포함하세요.
- '알려드렸습니다', '조회했습니다', '찾아드렸습니다' 같은 표현으로 실제 데이터를 대체하지 마세요.
- 도구가 반환한 원본 내용을 최대한 보존하여 사용자에게 전달하세요."""


# ── Node functions ────────────────────────────────────────────────────────────

async def _plan_node(state: dict) -> dict:
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(Plan)

    result: Plan = await llm.ainvoke([
        SystemMessage(content=_PLANNER_SYSTEM),
        HumanMessage(content=state["input"]),
    ])

    logger.info("Plan generated (%d steps): %s", len(result.steps), result.steps)
    return {"plan": result.steps}


async def _execute_node(state: dict, tools: list) -> dict:
    current_step = state["plan"][0]
    past = state.get("past_steps", [])

    context_lines = [f"- {s}: {r}" for s, r in past[-3:]]
    context = ("\n이전 단계 결과:\n" + "\n".join(context_lines) + "\n\n") if context_lines else ""

    task_prompt = f"{context}지금 실행할 단계: {current_step}"

    executor = create_react_agent(
        ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0),
        tools,
    )

    try:
        result = await executor.ainvoke({
            "messages": [
                SystemMessage(content=_EXECUTOR_SYSTEM),
                HumanMessage(content=task_prompt),
            ]
        })
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage) and m.content]
        step_result = ai_msgs[-1].content if ai_msgs else "(결과 없음)"
    except Exception as e:
        logger.warning("executor step failed (%s): %s", current_step, e)
        step_result = f"실행 실패: {e} – 다음 단계에서 재시도 가능"

    logger.info("Step done: %s → %s", current_step, step_result[:80])
    remaining_plan = state.get("plan", [])[1:]
    update: dict = {"plan": remaining_plan, "past_steps": [(current_step, step_result)]}

    # 남은 단계가 없으면 executor 결과를 바로 최종 응답으로 사용 (replanner 요약 방지)
    if not remaining_plan:
        update["response"] = step_result

    return update


async def _replan_node(state: dict) -> dict:
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    ).with_structured_output(Act)

    past_text = "\n".join(f"  - {s}: {r}" for s, r in state.get("past_steps", []))
    remaining = state.get("plan", [])
    remaining_text = "\n".join(f"  - {s}" for s in remaining) if remaining else "  (없음)"

    prompt = (
        f"원래 목표: {state['input']}\n\n"
        f"완료된 단계:\n{past_text}\n\n"
        f"남은 계획:\n{remaining_text}\n\n"
        "모든 목표가 달성됐으면 FinalResponse로, 아직 남은 작업이 있으면 Plan으로 응답하세요."
    )

    result: Act = await llm.ainvoke([
        SystemMessage(content=_REPLANNER_SYSTEM),
        HumanMessage(content=prompt),
    ])

    if isinstance(result.action, FinalResponse):
        logger.info("Replanner decided: DONE")
        return {"response": result.action.response, "plan": []}
    else:
        logger.info("Replanner updated plan: %s", result.action.steps)
        return {"plan": result.action.steps}


def _after_executor(state: dict) -> str:
    """executor 완료 후 다음 노드를 결정합니다.

    - 이미 response가 설정된 경우(단일 단계 완료): 바로 종료
    - 남은 계획이 없는 경우: 바로 종료
    - 남은 계획이 있는 경우: replanner로 이동
    """
    if state.get("response"):
        return "end"
    plan = state.get("plan", [])
    total_steps = len(state.get("past_steps", [])) + len(plan)
    if not plan or total_steps >= MAX_STEPS:
        return "end"
    return "replan"


def _should_end(state: dict) -> str:
    if state.get("response"):
        return "end"
    plan = state.get("plan", [])
    total_steps = len(state.get("past_steps", [])) + len(plan)
    if not plan or total_steps >= MAX_STEPS:
        return "end"
    return "execute"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_plan_execute_graph(tools: list):
    """Build and compile the Plan-and-Execute LangGraph.

    Args:
        tools: The full list of LangChain tools to give the executor.
    Returns:
        A compiled LangGraph runnable.
    """
    graph = StateGraph(PlanExecuteState)

    graph.add_node("planner", _plan_node)
    graph.add_node("executor", partial(_execute_node, tools=tools))
    graph.add_node("replanner", _replan_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_conditional_edges(
        "executor",
        _after_executor,
        {"end": END, "replan": "replanner"},
    )
    graph.add_conditional_edges(
        "replanner",
        _should_end,
        {"end": END, "execute": "executor"},
    )

    return graph.compile()


# ── Singleton ─────────────────────────────────────────────────────────────────

_plan_graph = None


def get_plan_execute_graph(tools: list):
    global _plan_graph
    if _plan_graph is None:
        _plan_graph = build_plan_execute_graph(tools)
    return _plan_graph
