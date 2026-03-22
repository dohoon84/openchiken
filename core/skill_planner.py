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

from config.settings import settings
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


_PLANNER_SYSTEM = """당신은 사용자 요청을 분석하여 필요한 소프트웨어 스킬(도구) 목록을 추출하는 전문가입니다.

규칙:
- 각 스킬은 하나의 원자적 기능을 담당합니다 (예: web_search, crypto_price, weather 등).
- 스킬 이름은 snake_case로 작성하세요.
- 이미 존재할 수 있는 일반적인 스킬 이름을 먼저 사용하세요:
  weather, web_search, finance, memo, task, calendar, gmail, drive, sheets, docs, workflow,
  crypto_price, exchange_rate, news_rss, geocoding, hacker_news, wikipedia, quickchart,
  air_quality, earthquake, quality_of_life, wallstreetbets, world_bank, sec_edgar
- 존재하지 않을 것 같은 특수한 기능은 새로운 이름을 만드세요.
- 실행 순서(priority)를 고려하여 데이터 수집 → 분석 → 출력 순으로 배치하세요.
- app_name은 전체 워크플로우를 설명하는 간결한 이름이어야 합니다."""


async def plan_skills(query: str) -> SkillPlanResult:
    """사용자 쿼리를 분석하여 필요한 스킬 목록과 로컬 존재 여부를 반환합니다."""
    llm = get_provider().get_model().with_structured_output(SkillPlan)

    result: SkillPlan = await llm.ainvoke([
        SystemMessage(content=_PLANNER_SYSTEM),
        HumanMessage(content=f"사용자 요청: {query}"),
    ])

    result.skills.sort(key=lambda s: s.priority)

    loader = get_skill_loader()
    all_local = loader.get_all_skill_names()

    existing = [s.name for s in result.skills if s.name in all_local]
    missing = [s.name for s in result.skills if s.name not in all_local]

    logger.info(
        "Skill plan: app=%s, total=%d, existing=%d, missing=%d",
        result.app_name, len(result.skills), len(existing), len(missing),
    )

    return SkillPlanResult(plan=result, existing_skills=existing, missing_skills=missing)
