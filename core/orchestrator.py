"""
Autonomous Skill Orchestrator — 완전 자율 스킬 오케스트레이션 엔진.

사용자 쿼리를 받으면:
  1. skill_planner로 필요 스킬 식별
  2. 로컬에 존재하는지 확인
  3. 없으면 허브(GitHub)에서 다운로드
  4. 허브에도 없으면 LLM이 자동 생성
  5. 스킬 캐시 리로드
  6. Plan-and-Execute 에이전트로 전체 플로우 실행

외부 에이전트 위임(Relay)은 사용자가 명시적으로 요청한 경우에만 동작합니다.
"""

from __future__ import annotations

import asyncio
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
    requires_google_auth: true 인 스킬은 Google 인증 여부도 확인합니다.
    """
    required = get_skill_requires_env(skill_name)

    # 설치된 SKILL.md에서 requires_env 및 requires_google_auth를 직접 파싱하여 보완
    from pathlib import Path
    import re
    skill_path = Path.home() / ".openchiken" / "skills" / skill_name / "SKILL.md"
    if skill_path.exists():
        text = skill_path.read_text(encoding="utf-8")
        if not required:
            match = re.search(r"requires_env:\s*(.+)", text)
            if match:
                required = [v.strip() for v in match.group(1).split(",") if v.strip()]
        # requires_google_auth 체크
        if re.search(r"requires_google_auth:\s*true", text, re.IGNORECASE):
            from skills import _google_credentials_available
            if not _google_credentials_available():
                required = list(required) + ["GOOGLE_CREDENTIALS"]

    return [env for env in required if not os.getenv(env, "").strip()]


def _find_relay_agent_for_skill(skill_name: str) -> str | None:
    """Relay에 연결된 에이전트 중 해당 capability를 보유한 최고 평판 에이전트를 반환합니다.

    현재 오케스트레이터의 자동 파이프라인에서는 호출되지 않습니다.
    사용자가 명시적으로 외부 에이전트 위임을 요청한 경우에만 사용됩니다.
    """
    try:
        from skills.relay_discover.tool import _get_agents, _enrich_with_reputation
    except ImportError:
        logger.warning("[Relay Fallback] relay_discover 스킬 미설치 — relay agent 탐색 건너뜀")
        return None

    try:
        agents = _get_agents()
    except RuntimeError as e:
        logger.warning("[Relay Fallback] Relay 조회 실패: %s", e)
        return None

    matched = [
        a for a in agents
        if any(skill_name.lower() in cap.lower() for cap in a.get("capabilities", []))
    ]
    if not matched:
        logger.info("[Relay Fallback] '%s' capability를 가진 에이전트 없음", skill_name)
        return None

    matched = _enrich_with_reputation(matched)

    def _sort_key(a: dict):
        trust_order = {"platform_verified": 0, "community_verified": 1, "unverified": 2}
        return (trust_order.get(a.get("trustLevel", "unverified"), 2), -(a.get("reputation_avg") or 0))

    matched.sort(key=_sort_key)
    best = matched[0]
    agent_id = best.get("agentId", "")
    rep_avg  = best.get("reputation_avg")
    rep_count = best.get("reputation_count", 0)
    logger.info(
        "[Relay Fallback] '%s' → 에이전트 '%s' 선택 (신뢰: %s, 평판: %s점 %d건)",
        skill_name, agent_id, best.get("trustLevel"), rep_avg, rep_count,
    )
    return agent_id


async def _ensure_skills(plan_result: SkillPlanResult) -> tuple[list[str], dict[str, list[str]]]:
    """누락된 스킬을 허브 다운로드 → 자동 생성 순으로 확보합니다.

    스킬 확보 우선순위: ① 허브 다운로드 → ② LLM 자동 생성
    (외부 에이전트 위임은 사용자 명시 요청 시에만, skill_planner가 처리)

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
            # 다운로드 전 필요 환경변수 사전 확인 (requires_env)
            pre_missing_env = [
                env for env in get_skill_requires_env(skill_name)
                if not os.getenv(env, "").strip()
            ]

            # 허브 인덱스의 auth 필드로 Google OAuth 사전 확인
            from core.hub import get_hub_index
            hub_index = get_hub_index()
            hub_skill_meta = next(
                (s for s in hub_index.get("skills", []) if s.get("name") == skill_name),
                {},
            )
            requires_google_auth = hub_skill_meta.get("auth", "") == "google_oauth"
            pre_missing_google: list[str] = []
            if requires_google_auth:
                from skills import _google_credentials_available
                if not _google_credentials_available():
                    pre_missing_google = ["GOOGLE_CREDENTIALS"]

            pre_missing = pre_missing_env + pre_missing_google
            if pre_missing:
                logger.warning(
                    "[허브 설치] 스킬 '%s'에 필요한 인증/환경변수 미설정: %s — 다운로드는 진행하나 활성화되지 않습니다.",
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
    """환경변수/인증 설정 안내 메시지를 생성합니다."""
    env_skills: dict[str, list[str]] = {}
    google_auth_skills: list[str] = []

    for skill_name, missing in missing_env_map.items():
        env_only = [e for e in missing if e != "GOOGLE_CREDENTIALS"]
        needs_google = "GOOGLE_CREDENTIALS" in missing
        if env_only:
            env_skills[skill_name] = env_only
        if needs_google:
            google_auth_skills.append(skill_name)

    lines: list[str] = []

    if google_auth_skills:
        lines.append("🔑 다음 스킬은 Google 계정 인증(OAuth)이 필요합니다.\n")
        lines.append("아직 Google 연동이 설정되어 있지 않습니다.")
        lines.append("터미널에서 아래 명령을 실행하여 Google 인증을 완료하세요:\n")
        lines.append("  openchiken-setup")
        lines.append("\n또는 Google Cloud Console에서 credentials.json을 발급받아")
        lines.append("프로젝트 루트에 저장한 후 다시 시도해 주세요.\n")
        for skill_name in google_auth_skills:
            if skill_name in _SKILL_API_DOCS:
                lines.append(f"  📌 {skill_name} 설정 가이드: {_SKILL_API_DOCS[skill_name]}")
        lines.append("")

    if env_skills:
        lines.append("⚠️ 다음 스킬을 사용하려면 API 키(환경변수) 설정이 필요합니다.\n")
        lines.append("프로젝트 루트의 `.env` 파일에 아래 항목을 추가한 후 다시 시도해 주세요:\n")
        for skill_name, env_vars in env_skills.items():
            lines.append(f"[{skill_name} 스킬]")
            for env in env_vars:
                example = _ENV_EXAMPLES.get(env, "<발급받은 키를 입력>")
                lines.append(f"  {env}={example}")
        lines.append("\n📌 API 키 발급 안내:")
        for skill_name in env_skills:
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
    "youtube": "https://console.cloud.google.com/ → YouTube Data API v3 활성화 → OAuth 클라이언트 ID 발급 → credentials.json 다운로드",
    "weather": "https://openweathermap.org/api → 무료 플랜 가입 후 API 키 발급",
    "news_api": "https://newsapi.org/ → 무료 플랜 가입 후 API 키 발급",
    "gmail": "https://console.cloud.google.com/ → Gmail API 활성화 → OAuth 클라이언트 ID 발급",
    "calendar": "https://console.cloud.google.com/ → Google Calendar API 활성화 → OAuth 클라이언트 ID 발급",
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

    # Step 3: 스킬이 0개 → 단순 대화형 메시지, 바로 chat()으로 처리
    needed_skills = [s.name for s in plan_result.plan.skills]
    if not needed_skills:
        logger.info("run_autonomous: no skills needed — routing to simple chat()")
        from core.agent import chat
        result = await chat(session_id, query)
        logger.info("=== Autonomous orchestration complete (chat path) ===")
        return result

    # Step 4: 필요한 스킬의 툴만 필터링하여 Plan-and-Execute 실행
    loader = get_skill_loader()
    filtered_tools = loader.get_tools_for_skills(needed_skills)

    enhanced_query = (
        f"{query}\n\n"
        f"[사용 가능한 도구(스킬): {', '.join(needed_skills)}]\n"
        f"위 도구들은 모두 로컬에서 직접 호출 가능합니다. 반드시 도구를 사용하여 작업을 수행하세요."
    )

    if filtered_tools:
        from core.agent import chat_plan_with_tools
        logger.info(
            "run_autonomous: %d skills → %d tools (전체 대비 축소)",
            len(needed_skills), len(filtered_tools),
        )
        result = await chat_plan_with_tools(session_id, enhanced_query, filtered_tools)
    else:
        from core.agent import chat_plan
        logger.warning("run_autonomous: tool filtering returned empty — using all tools")
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

    # ── 툴 필터링: 앱의 sub_skills에 해당하는 툴만 로드 ──────────────────────
    loader = get_skill_loader()
    if app.sub_skills:
        tools = loader.get_tools_for_skills(app.sub_skills)
        logger.info(
            "App '%s' tools: %d tools for skills %s",
            app_name, len(tools), app.sub_skills,
        )
    else:
        from core.agent import get_tools
        tools = get_tools()
        logger.warning("App '%s' has no sub_skills — using all tools", app_name)

    if not tools:
        from core.agent import get_tools
        tools = get_tools()
        logger.warning("App '%s' tool filtering returned empty — using all tools", app_name)

    # extra_context가 있으면 첫 번째 단계에 컨텍스트를 주입
    steps = list(app.steps)
    if extra_context and steps:
        steps[0] = f"[컨텍스트: {extra_context}] {steps[0]}"

    logger.info("App '%s' steps (%d)", app_name, len(steps))

    # ── 병렬 실행: 수집 단계(N-1개) 동시 실행 → 마지막 종합 단계 순차 실행 ──
    from core.planner import run_step_with_tools

    try:
        if len(steps) == 1:
            # 단계가 하나뿐이면 그냥 실행
            result = await run_step_with_tools(steps[0], tools)
        else:
            collection_steps = steps[:-1]   # 데이터 수집 단계 (병렬)
            synthesis_step   = steps[-1]    # 최종 종합/리포트 단계 (순차)

            logger.info(
                "App '%s': %d collection steps (parallel) + 1 synthesis step",
                app_name, len(collection_steps),
            )

            # 수집 단계 병렬 실행
            raw_results = await asyncio.gather(
                *[run_step_with_tools(step, tools) for step in collection_steps],
                return_exceptions=True,
            )

            # 결과 취합 (예외 포함)
            context_parts: list[str] = []
            for i, (step, res) in enumerate(zip(collection_steps, raw_results)):
                if isinstance(res, BaseException):
                    context_parts.append(f"[단계 {i+1}] {step}\n결과: 실행 실패 — {res}")
                    logger.warning("Parallel step %d failed: %s", i + 1, res)
                else:
                    context_parts.append(f"[단계 {i+1}] {step}\n결과: {res}")

            collected_context = "이전 단계 수집 결과:\n\n" + "\n\n".join(context_parts)

            # 종합 단계 실행 (수집 결과 전체를 컨텍스트로 전달)
            result = await run_step_with_tools(synthesis_step, tools, context=collected_context)

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
