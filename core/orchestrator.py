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
import os

from core.hub import download_skill, get_skill_requires_env, hub_skill_exists
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


def _check_missing_env_vars(skill_name: str) -> list[str]:
    """스킬이 필요로 하는 환경변수 중 설정되지 않은 항목을 반환합니다.

    허브 인덱스의 requires_env 목록을 우선 확인하고,
    설치된 스킬의 SKILL.md에서도 재확인합니다.
    """
    required = get_skill_requires_env(skill_name)

    # 설치된 SKILL.md에서 requires_env를 직접 파싱하여 보완
    if not required:
        from pathlib import Path
        import re
        skill_path = Path.home() / ".openchiken" / "skills" / skill_name / "SKILL.md"
        if skill_path.exists():
            text = skill_path.read_text(encoding="utf-8")
            match = re.search(r"requires_env:\s*(.+)", text)
            if match:
                required = [v.strip() for v in match.group(1).split(",") if v.strip()]

    return [env for env in required if not os.getenv(env, "").strip()]


async def _ensure_skills(plan_result: SkillPlanResult) -> tuple[list[str], dict[str, list[str]]]:
    """누락된 스킬을 허브 다운로드 또는 자동 생성으로 확보합니다.

    Returns:
        (설치된 스킬 이름 목록, {스킬명: 누락된 환경변수 목록} 딕셔너리)
    """
    installed: list[str] = []
    missing_env_map: dict[str, list[str]] = {}
    purpose_map = {s.name: s.purpose for s in plan_result.plan.skills}

    for skill_name in plan_result.missing_skills:
        purpose = purpose_map.get(skill_name, "")

        # 1차: 허브에서 다운로드 시도
        if hub_skill_exists(skill_name):
            # 다운로드 전 필요 환경변수 사전 확인
            pre_missing = [
                env for env in get_skill_requires_env(skill_name)
                if not os.getenv(env, "").strip()
            ]
            if pre_missing:
                logger.warning(
                    "[허브 설치] 스킬 '%s'에 필요한 환경변수 미설정: %s — 다운로드는 진행하나 활성화되지 않습니다.",
                    skill_name, pre_missing,
                )
                missing_env_map[skill_name] = pre_missing

            try:
                download_skill(skill_name)
                installed.append(skill_name)
                logger.info("[허브 설치] 스킬 '%s' 허브에서 다운로드 완료", skill_name)
                continue
            except Exception as e:
                logger.warning("[허브 설치 실패] 스킬 '%s': %s → AI 자동 생성으로 전환", skill_name, e)

        # 2차: LLM 자동 생성 (허브에 없는 스킬)
        try:
            await generate_skill(skill_name, purpose)
            installed.append(skill_name)
            logger.info("[AI 자동생성] 스킬 '%s' LLM이 코드를 생성했습니다 (허브 미등록 스킬)", skill_name)
        except Exception as e:
            logger.error("[AI 자동생성 실패] 스킬 '%s': %s", skill_name, e)

    return installed, missing_env_map


def _build_env_setup_guide(missing_env_map: dict[str, list[str]]) -> str:
    """환경변수 설정 안내 메시지를 생성합니다."""
    lines = [
        "⚠️ 다음 스킬을 사용하려면 API 키(환경변수) 설정이 필요합니다.\n",
        "프로젝트 루트의 `.env` 파일에 아래 항목을 추가한 후 다시 시도해 주세요:\n",
    ]
    for skill_name, env_vars in missing_env_map.items():
        lines.append(f"[{skill_name} 스킬]")
        for env in env_vars:
            example = _ENV_EXAMPLES.get(env, "<발급받은 키를 입력>")
            lines.append(f"  {env}={example}")
    lines.append("\n📌 API 키 발급 안내:")
    for skill_name in missing_env_map:
        if skill_name in _SKILL_API_DOCS:
            lines.append(f"  • {skill_name}: {_SKILL_API_DOCS[skill_name]}")
    return "\n".join(lines)


_ENV_EXAMPLES: dict[str, str] = {
    "YOUTUBE_API_KEY": "AIzaSy...",
    "OPENAI_API_KEY": "sk-...",
    "SERPAPI_API_KEY": "your_serpapi_key",
    "GOOGLE_API_KEY": "AIzaSy...",
    "WEATHER_API_KEY": "your_openweathermap_key",
    "NEWS_API_KEY": "your_newsapi_key",
}

_SKILL_API_DOCS: dict[str, str] = {
    "youtube": "https://console.cloud.google.com/ → YouTube Data API v3 활성화 후 API 키 발급",
    "weather": "https://openweathermap.org/api → 무료 플랜 가입 후 API 키 발급",
    "news_api": "https://newsapi.org/ → 무료 플랜 가입 후 API 키 발급",
}


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
    missing_env_map: dict[str, list[str]] = {}
    newly_installed: list[str] = []
    if plan_result.missing_skills:
        newly_installed, missing_env_map = await _ensure_skills(plan_result)
        if newly_installed:
            _reload_skill_cache()
            logger.info("새로 설치된 스킬: %s", newly_installed)

    # Step 2-1: 필수 환경변수 누락으로 인해 스킬이 활성화되지 않은 경우 즉시 안내
    if missing_env_map:
        # 캐시 리로드 후 실제로 로드된 스킬 목록으로 재확인
        loader = get_skill_loader()
        loaded_skill_names = {s.name for s in loader.load_all()}
        still_missing = {
            name: envs
            for name, envs in missing_env_map.items()
            if name not in loaded_skill_names
        }
        if still_missing:
            guide = _build_env_setup_guide(still_missing)
            logger.warning("환경변수 누락으로 스킬 비활성화: %s", list(still_missing.keys()))
            return guide

    # Step 3: Plan-and-Execute 에이전트로 실행
    from core.agent import chat_plan

    enhanced_query = (
        f"{query}\n\n"
        f"[사용 가능한 스킬: {', '.join(s.name for s in plan_result.plan.skills)}]"
    )

    result = await chat_plan(session_id, enhanced_query)

    logger.info("=== Autonomous orchestration complete ===")
    return result


async def run_app(app_name: str, session_id: str, extra_context: str = "") -> str:
    """APP.md steps를 LLM 플래너 없이 직접 실행합니다 (결정론적 앱 실행).

    Args:
        app_name:      설치된 앱의 name (APP.md의 name 필드)
        session_id:    대화 세션 ID
        extra_context: 사용자가 전달한 추가 컨텍스트 (예: 조회 지역, 파라미터)

    Returns:
        최종 실행 결과 텍스트.

    Raises:
        ValueError: 앱을 찾을 수 없을 때
    """
    from skills import get_skill_loader

    loader = get_skill_loader()
    apps = loader.load_apps()
    app = next((a for a in apps if a.name == app_name), None)
    if app is None:
        raise ValueError(f"앱 '{app_name}'을 찾을 수 없습니다. 설치 여부를 확인하세요.")

    logger.info("=== App execution start: %s ===", app_name)

    # steps가 없으면 instructions 전체를 일반 run_autonomous로 처리
    if not app.steps:
        logger.warning(
            "App '%s' has no structured steps — falling back to run_autonomous", app_name
        )
        query = app.instructions
        if extra_context:
            query = f"{extra_context}\n\n{app.instructions}"
        return await run_autonomous(query, session_id)

    # steps를 plan으로 직접 주입 (LLM 플래너 완전 우회)
    from core.agent import get_tools

    try:
        from core.planner import get_app_execute_graph
        graph = get_app_execute_graph(get_tools())
    except Exception as e:
        logger.warning("App graph build failed (%s), fallback to run_autonomous", e)
        return await run_autonomous(app.instructions, session_id)

    # extra_context가 있으면 첫 번째 단계에 컨텍스트를 주입
    steps = list(app.steps)
    if extra_context and steps:
        steps[0] = f"[컨텍스트: {extra_context}] {steps[0]}"

    input_summary = f"{app.description}"
    if extra_context:
        input_summary += f" (요청: {extra_context})"

    logger.info("App '%s' steps (%d): %s", app_name, len(steps), steps)

    try:
        state = await graph.ainvoke({
            "input": input_summary,
            "plan": steps,
            "past_steps": [],
            "response": "",
        })
        result = state.get("response") or "앱 실행이 완료되었지만 최종 응답이 없습니다."
    except Exception as e:
        logger.error("App '%s' execution failed: %s", app_name, e, exc_info=True)
        result = f"앱 '{app_name}' 실행 중 오류가 발생했습니다: {e}"

    logger.info("=== App execution complete: %s ===", app_name)
    return result


async def find_matching_app(query: str) -> str | None:
    """쿼리가 trigger_keywords와 매칭되는 설치된 앱 이름을 반환합니다.

    매칭되는 앱이 없으면 None을 반환합니다.
    """
    from skills import get_skill_loader

    loader = get_skill_loader()
    apps = loader.load_apps()

    query_lower = query.lower()
    for app in apps:
        if not app.trigger_keywords:
            continue
        for kw in app.trigger_keywords:
            if kw.strip().lower() in query_lower:
                logger.info("App trigger matched: app=%s, keyword=%s", app.name, kw)
                return app.name

    return None


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
