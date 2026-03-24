from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_RELAY_URL = os.getenv(
    "RELAY_URL",
    "https://openchiken-relay-production.up.railway.app",
)
_SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
_MY_AGENT_ID = os.getenv("AGENT_ID", "")
_MY_TRUST_LEVEL = os.getenv("AGENT_TRUST_LEVEL", "platform_verified")


def _log_relay_activity(agent_id: str, skill: str, status: str, summary: str = "") -> None:
    """로컬 서버에 릴레이 송신 활동을 기록합니다 (실패해도 무시)."""
    try:
        body = json.dumps({
            "direction": "sent",
            "agentId":   agent_id,
            "skill":     skill,
            "status":    status,
            "summary":   summary[:300],
        }).encode()
        req = urllib.request.Request(
            f"{_SERVER_URL.rstrip('/')}/api/relay/activity",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def _invoke(agent_id: str, skill: str, params: dict) -> dict:
    """Relay REST API로 외부 에이전트를 호출합니다."""
    url = f"{_RELAY_URL.rstrip('/')}/api/agents/{agent_id}/invoke"
    body = json.dumps({
        "skill":  skill,
        "params": params,
        "caller": {
            "agentId":    _MY_AGENT_ID or "openchiken-local",
            "trustLevel": _MY_TRUST_LEVEL,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=65) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        try:
            detail = json.loads(error_body).get("error", error_body)
        except Exception:
            detail = error_body
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Relay 서버 연결 실패: {e}") from e


@tool
def invoke_agent(agent_id: str, skill: str, params: str = "{}") -> str:
    """OpenChiken Relay를 통해 외부 에이전트에게 작업을 위임하고 결과를 받습니다.

    먼저 discover_agents로 사용 가능한 에이전트와 agentId를 확인하세요.
    상대방 에이전트의 정책에 따라 자동 승인 또는 거절될 수 있습니다.

    Args:
        agent_id: 호출할 에이전트의 ID (예: "oc_ext_abc123def456")
        skill: 실행을 요청할 스킬 이름 (예: "web_search", "weather", "memo")
        params: 스킬에 전달할 파라미터 (JSON 문자열, 예: '{"query": "서울 날씨"}')
    """
    try:
        parsed_params = json.loads(params) if params.strip() else {}
    except json.JSONDecodeError:
        # JSON이 아니면 message 키로 감쌈
        parsed_params = {"message": params}

    try:
        result = _invoke(agent_id, skill, parsed_params)
    except RuntimeError as e:
        _log_relay_activity(agent_id, skill, "error", str(e))
        return f"외부 에이전트 호출 실패: {e}"

    if not result.get("ok"):
        err_msg = result.get("error", "알 수 없는 오류")
        _log_relay_activity(agent_id, skill, "rejected", err_msg)
        return f"에이전트가 요청을 거절했습니다: {err_msg}"

    payload = result.get("result", result)

    # reply 필드가 있으면 우선 반환
    if isinstance(payload, dict) and "reply" in payload:
        reply_text = str(payload["reply"])
        _log_relay_activity(agent_id, skill, "approved", reply_text[:200])
        return reply_text

    result_str = json.dumps(payload, ensure_ascii=False, indent=2)
    _log_relay_activity(agent_id, skill, "approved", result_str[:200])
    return result_str


def get_tools() -> list:
    return [invoke_agent]
