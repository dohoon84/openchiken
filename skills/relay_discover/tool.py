from __future__ import annotations

import logging
import os
import urllib.request
import urllib.error
import json

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_RELAY_URL = os.getenv(
    "RELAY_URL",
    "https://openchiken-relay-production.up.railway.app",
)


def _get_agents() -> list[dict]:
    """Relay REST API로 연결된 에이전트 목록을 가져옵니다."""
    url = f"{_RELAY_URL.rstrip('/')}/api/agents"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("agents", [])
    except urllib.error.URLError as e:
        raise RuntimeError(f"Relay 서버에 연결할 수 없습니다: {e}") from e


def _get_reputation(agent_id: str) -> dict:
    """특정 에이전트의 on-chain 평판 정보를 조회합니다."""
    url = f"{_RELAY_URL.rstrip('/')}/api/agents/{agent_id}/reputation"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"count": 0, "average": None}


def _enrich_with_reputation(agents: list[dict]) -> list[dict]:
    """에이전트 목록에 평판 정보를 추가합니다."""
    enriched = []
    for a in agents:
        rep = _get_reputation(a.get("agentId", ""))
        enriched.append({**a, "reputation_count": rep.get("count", 0), "reputation_avg": rep.get("average")})
    return enriched


@tool
def discover_agents(capability_filter: str = "") -> str:
    """OpenChiken Relay에 현재 연결된 외부 에이전트 목록을 조회합니다.

    각 에이전트의 agentId, capabilities(기능 목록), trustLevel(신뢰 등급),
    on-chain 평판 점수를 반환합니다.
    특정 기능을 가진 에이전트를 찾거나, relay_invoke로 호출하기 전에 사용하세요.

    Args:
        capability_filter: 특정 capability로 필터링 (예: "web_search", "weather"). 빈 문자열이면 전체 반환.
    """
    try:
        agents = _get_agents()
    except RuntimeError as e:
        return str(e)

    if not agents:
        return "현재 Relay에 연결된 외부 에이전트가 없습니다."

    if capability_filter:
        agents = [
            a for a in agents
            if any(capability_filter.lower() in cap.lower() for cap in a.get("capabilities", []))
        ]
        if not agents:
            return f"'{capability_filter}' 기능을 가진 에이전트가 없습니다."

    agents = _enrich_with_reputation(agents)

    # 평판 점수 높은 순, platform_verified 우선 정렬
    def _sort_key(a: dict):
        trust_order = {"platform_verified": 0, "community_verified": 1, "unverified": 2}
        return (trust_order.get(a.get("trustLevel", "unverified"), 2), -(a.get("reputation_avg") or 0))

    agents.sort(key=_sort_key)

    lines = [f"Relay에 연결된 에이전트 {len(agents)}개 (평판 높은 순):\n"]
    for a in agents:
        agent_id = a.get("agentId", "—")
        caps = ", ".join(a.get("capabilities", [])) or "없음"
        trust = a.get("trustLevel", "unverified")
        token_id = a.get("tokenId") or "미등록"
        rep_avg = a.get("reputation_avg")
        rep_count = a.get("reputation_count", 0)
        trust_label = {
            "platform_verified":  "✅ 플랫폼 검증",
            "community_verified": "🔵 커뮤니티 검증",
            "unverified":         "⚠️ 미검증",
        }.get(trust, trust)
        rep_label = f"{rep_avg:.0f}점 ({rep_count}건)" if rep_avg is not None else f"없음 ({rep_count}건)"
        lines.append(
            f"• {agent_id}\n"
            f"  기능: {caps}\n"
            f"  신뢰: {trust_label}  |  Token ID: {token_id}  |  평판: {rep_label}"
        )

    return "\n".join(lines)


@tool
def find_best_agent(capability: str, min_reputation: int = 0) -> str:
    """특정 capability를 갖고 평판이 가장 높은 외부 에이전트를 자동으로 찾아 반환합니다.

    로컬에 해당 스킬이 없을 때, Relay에 연결된 에이전트 중 가장 적합한 에이전트를 선택합니다.
    platform_verified 에이전트를 우선하며, 동급 신뢰도에서는 평판 점수가 높은 순으로 선택합니다.

    Args:
        capability: 필요한 기능 키워드 (예: "weather", "web_search", "calendar")
        min_reputation: 최소 평판 점수 (기본 0 = 제한 없음). 이 점수 미만은 제외합니다.

    Returns:
        최적 에이전트의 agentId (relay_invoke에 바로 사용 가능)
        또는 적합한 에이전트가 없을 때 안내 메시지
    """
    try:
        agents = _get_agents()
    except RuntimeError as e:
        return str(e)

    if not agents:
        return "현재 Relay에 연결된 외부 에이전트가 없습니다."

    # capability 필터링
    matched = [
        a for a in agents
        if any(capability.lower() in cap.lower() for cap in a.get("capabilities", []))
    ]
    if not matched:
        return f"'{capability}' 기능을 가진 에이전트가 없습니다. relay_invoke 없이 로컬에서 처리하거나 사용자에게 안내하세요."

    matched = _enrich_with_reputation(matched)

    # min_reputation 필터 (평판 없는 에이전트는 0점으로 간주)
    if min_reputation > 0:
        matched = [a for a in matched if (a.get("reputation_avg") or 0) >= min_reputation]
        if not matched:
            return (
                f"'{capability}' 기능을 가진 에이전트는 있지만 평판 점수 {min_reputation}점 이상인 에이전트가 없습니다. "
                "min_reputation을 낮추거나 0으로 설정해 재시도하세요."
            )

    # platform_verified 우선, 평판 높은 순 정렬
    def _sort_key(a: dict):
        trust_order = {"platform_verified": 0, "community_verified": 1, "unverified": 2}
        return (trust_order.get(a.get("trustLevel", "unverified"), 2), -(a.get("reputation_avg") or 0))

    matched.sort(key=_sort_key)
    best = matched[0]

    agent_id   = best.get("agentId", "")
    caps       = ", ".join(best.get("capabilities", [])) or "없음"
    trust      = best.get("trustLevel", "unverified")
    rep_avg    = best.get("reputation_avg")
    rep_count  = best.get("reputation_count", 0)
    trust_label = {
        "platform_verified":  "✅ 플랫폼 검증",
        "community_verified": "🔵 커뮤니티 검증",
        "unverified":         "⚠️ 미검증",
    }.get(trust, trust)
    rep_label = f"{rep_avg:.0f}점 ({rep_count}건)" if rep_avg is not None else f"없음"

    return (
        f"최적 에이전트: {agent_id}\n"
        f"  기능: {caps}\n"
        f"  신뢰: {trust_label}  |  평판: {rep_label}\n"
        f"→ invoke_agent(agent_id=\"{agent_id}\", skill=\"{capability}\", ...) 로 호출하세요."
    )


def get_tools() -> list:
    return [discover_agents, find_best_agent]
