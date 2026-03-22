"""
Skill Planner — LLM structured output으로 쿼리에서 필요 스킬 목록을 추출합니다.

사용자 쿼리를 분석하여:
  1. 필요한 스킬 이름·목적 목록을 추출
  2. 로컬에 해당 스킬이 존재하는지 표시
  3. 실행 순서(priority)를 결정
"""

from __future__ import annotations

import logging
from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.hub import list_hub_skills
from core.provider import get_provider
from skills import get_skill_loader

logger = logging.getLogger(__name__)


class SkillRequirement(BaseModel):
    name: str = Field(description="스킬 식별자 (snake_case, 예: crypto_price)")
    purpose: str = Field(description="이 스킬이 필요한 이유 (한 문장)")
    priority: int = Field(description="실행 순서 (1이 가장 먼저)")


class SkillPlan(BaseModel):
    skills: List[SkillRequirement] = Field(description="필요한 스킬 목록 (실행 순서대로)")
    app_name: str = Field(description="이 스킬 조합의 앱 이름 (snake_case)")
    app_description: str = Field(description="앱 설명 (한 문장)")


class SkillPlanResult(BaseModel):
    """플래닝 결과 + 로컬 존재 여부 정보."""

    plan: SkillPlan
    existing_skills: list[str]
    missing_skills: list[str]


_PLANNER_SYSTEM_TEMPLATE = """당신은 사용자 요청을 분석하여 필요한 소프트웨어 스킬(도구) 목록을 추출하는 전문가입니다.

## 현재 설치된 스킬 목록 (정확한 ID):
{installed_skills}

## 허브에서 자동 다운로드 가능한 스킬 목록 (미설치 시 자동 설치됨):
{hub_skills}

## 규칙:
- **설치된 스킬** 목록에 있는 이름은 반드시 **정확한 ID 그대로** 사용하세요. 절대 변형하지 마세요.
- **허브 스킬** 목록에 있는 기능이 필요하다면 반드시 **정확한 허브 스킬 ID 그대로** 사용하세요. 자동으로 다운로드됩니다.
- 위 두 목록 모두에 없는 기능이 필요할 때만 새로운 snake_case 이름을 만드세요.
- 각 스킬은 하나의 원자적 기능을 담당합니다.
- 실행 순서(priority)를 고려하여 데이터 수집 → 분석 → 출력 순으로 배치하세요.
- app_name은 전체 워크플로우를 설명하는 간결한 이름이어야 합니다.

## 중요 — 대화형 메시지 구분:
- 인사, 감사, 잡담, 감정 표현 등 단순 대화성 메시지는 skills 목록을 **비워서** 반환하세요.
  예: "안녕", "고마워", "잘 지내?", "인사한거야", "ㅋㅋ", "좋아" 등
- 명확한 작업 요청(조회, 전송, 분석, 예약 등)이 있을 때만 스킬을 추가하세요."""


async def plan_skills(query: str) -> SkillPlanResult:
    """사용자 쿼리를 분석하여 필요한 스킬 목록과 로컬 존재 여부를 반환합니다."""
    llm = get_provider().get_model().with_structured_output(SkillPlan)

    loader = get_skill_loader()
    all_local = loader.get_all_skill_names()
    installed_skills_str = ", ".join(sorted(all_local)) if all_local else "(없음)"

    # 허브 스킬 목록: 미설치 항목만 표시 (이미 설치된 건 위 목록에 있으므로)
    try:
        hub_skill_list = list_hub_skills()
        hub_only = [s["name"] for s in hub_skill_list if s["name"] not in all_local]
        hub_skills_str = ", ".join(hub_only) if hub_only else "(없음)"
    except Exception:
        hub_skills_str = "(허브 연결 실패)"

    system_prompt = _PLANNER_SYSTEM_TEMPLATE.format(
        installed_skills=installed_skills_str,
        hub_skills=hub_skills_str,
    )

    result: SkillPlan = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"사용자 요청: {query}"),
    ])

    result.skills.sort(key=lambda s: s.priority)

    existing = [s.name for s in result.skills if s.name in all_local]
    missing = [s.name for s in result.skills if s.name not in all_local]

    logger.info(
        "Skill plan: app=%s, total=%d, existing=%d, missing=%d",
        result.app_name, len(result.skills), len(existing), len(missing),
    )

    return SkillPlanResult(plan=result, existing_skills=existing, missing_skills=missing)
