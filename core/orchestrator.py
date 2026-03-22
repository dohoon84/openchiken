"""
Autonomous Skill Orchestrator — 완전 자율 스킬 오케스트레이션 엔진.

사용자 쿼리를 받으면:
  1. skill_planner로 필요 스킬 식별
  2. 로컬에 존재하는지 확인
  3. 없으면 허브(GitHub)에서 다운로드
  4. 허브에도 없으면 LLM이 자동 생성
  5. 스킬 캐시 리로드
  6. Plan-and-Execute 에이전트로 전체 플로우 실행
"""

from __future__ import annotations

import logging

from core.hub import download_skill, hub_skill_exists
from core.skill_generator import generate_skill
from core.skill_planner import SkillPlanResult, plan_skills
from skills import get_skill_loader

logger = logging.getLogger(__name__)


def _reload_skill_cache() -> None:
    """스킬 캐시를 무효화하여 새로 설치된 스킬이 반영되도록 합니다."""
    try:
        import core.agent as ag
        import skills as sk

        ag._tools_cache = None
        ag._skill_instructions_cache = None
        ag._agent = None
        ag._plan_graph = None
        sk._loader = None
        logger.info("Skill cache invalidated")
    except Exception as e:
        logger.warning("Failed to invalidate skill cache: %s", e)


async def _ensure_skills(plan_result: SkillPlanResult) -> list[str]:
    """누락된 스킬을 허브 다운로드 또는 자동 생성으로 확보합니다.

    Returns:
        실제로 새로 설치된 스킬 이름 목록.
    """
    installed: list[str] = []
    purpose_map = {s.name: s.purpose for s in plan_result.plan.skills}

    for skill_name in plan_result.missing_skills:
        purpose = purpose_map.get(skill_name, "")

        # 1차: 허브에서 다운로드 시도
        if hub_skill_exists(skill_name):
            try:
                download_skill(skill_name)
                installed.append(skill_name)
                logger.info("Skill '%s' downloaded from hub", skill_name)
                continue
            except Exception as e:
                logger.warning("Hub download failed for '%s': %s", skill_name, e)

        # 2차: LLM 자동 생성
        try:
            await generate_skill(skill_name, purpose)
            installed.append(skill_name)
            logger.info("Skill '%s' auto-generated", skill_name)
        except Exception as e:
            logger.error("Failed to generate skill '%s': %s", skill_name, e)

    return installed


async def run_autonomous(query: str, session_id: str) -> str:
    """완전 자율 오케스트레이션: 쿼리 → 스킬 확보 → 실행 → 결과 반환.

    Args:
        query: 사용자 쿼리
        session_id: 대화 세션 ID

    Returns:
        최종 실행 결과 텍스트.
    """
    # Step 1: 필요 스킬 분석
    logger.info("=== Autonomous orchestration start ===")
    logger.info("Query: %s", query[:100])

    plan_result = await plan_skills(query)

    logger.info(
        "Plan: app=%s, existing=%s, missing=%s",
        plan_result.plan.app_name,
        plan_result.existing_skills,
        plan_result.missing_skills,
    )

    # Step 2: 누락 스킬 확보 (허브 다운로드 → 자동 생성)
    newly_installed: list[str] = []
    if plan_result.missing_skills:
        newly_installed = await _ensure_skills(plan_result)
        if newly_installed:
            _reload_skill_cache()
            logger.info("Newly installed skills: %s", newly_installed)

    # Step 3: Plan-and-Execute 에이전트로 실행
    from core.agent import chat_plan

    enhanced_query = (
        f"{query}\n\n"
        f"[사용 가능한 스킬: {', '.join(s.name for s in plan_result.plan.skills)}]"
    )

    result = await chat_plan(session_id, enhanced_query)

    logger.info("=== Autonomous orchestration complete ===")
    return result


async def get_orchestration_plan(query: str) -> dict:
    """스킬 플래닝만 수행하고 실행하지 않습니다 (미리보기용).

    Returns:
        플래닝 결과를 딕셔너리로 반환.
    """
    plan_result = await plan_skills(query)

    return {
        "app_name": plan_result.plan.app_name,
        "app_description": plan_result.plan.app_description,
        "skills": [
            {
                "name": s.name,
                "purpose": s.purpose,
                "priority": s.priority,
                "status": "exists" if s.name in plan_result.existing_skills else "missing",
            }
            for s in plan_result.plan.skills
        ],
        "existing_skills": plan_result.existing_skills,
        "missing_skills": plan_result.missing_skills,
    }
