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
    response: str = Field(description="사용자에게 전달할 최종 답변 (완료된 작업 요약 포함)")


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
- 각 단계는 한 문장으로 작성하세요."""

_EXECUTOR_SYSTEM = """당신은 주어진 단 하나의 단계를 실행하는 실행자입니다.

규칙:
- 제시된 단계만 실행하세요. 다른 단계는 건드리지 마세요.
- 사용 가능한 도구를 적극 활용하세요.
- 실행 결과를 간결하게 보고하세요.
- 도구 호출이 실패하면, 대안적인 방법을 시도하고 그 결과를 보고하세요."""

_REPLANNER_SYSTEM = """당신은 진행 중인 계획을 검토하고 다음 행동을 결정하는 전문가입니다.

다음 중 하나를 반환하세요:
1. FinalResponse: 원래 목표가 완전히 달성된 경우 → 사용자에게 전달할 최종 답변
2. Plan: 아직 남은 작업이 있는 경우 → 업데이트된 남은 단계 목록"""


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
    return {"plan": remaining_plan, "past_steps": [(current_step, step_result)]}


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
    graph.add_edge("executor", "replanner")
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
