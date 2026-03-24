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


@tool
def discover_agents(capability_filter: str = "") -> str:
    """OpenChiken Relay에 현재 연결된 외부 에이전트 목록을 조회합니다.

    각 에이전트의 agentId, capabilities(기능 목록), trustLevel(신뢰 등급)을 반환합니다.
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

    lines = [f"Relay에 연결된 에이전트 {len(agents)}개:\n"]
    for a in agents:
        agent_id = a.get("agentId", "—")
        caps = ", ".join(a.get("capabilities", [])) or "없음"
        trust = a.get("trustLevel", "unverified")
        token_id = a.get("tokenId") or "미등록"
        trust_label = {
            "platform_verified":  "✅ 플랫폼 검증",
            "community_verified": "🔵 커뮤니티 검증",
            "unverified":         "⚠️ 미검증",
        }.get(trust, trust)
        lines.append(
            f"• {agent_id}\n"
            f"  기능: {caps}\n"
            f"  신뢰: {trust_label}  |  Token ID: {token_id}"
        )

    return "\n".join(lines)


def get_tools() -> list:
    return [discover_agents]
