"""
OpenChiken iMessage 채널
─────────────────────────
macOS Messages.app + AppleScript 기반 채널 어댑터.

동작 방식:
  수신: ~/Library/Messages/chat.db 를 주기적으로 폴링하여 새 메시지 감지
  발신: osascript(AppleScript) 로 Messages.app 을 통해 전송

사전 조건:
  - macOS 전용 (macOS 12 Monterey 이상 권장)
  - 시스템 설정 > 개인정보 보호 및 보안 > 전체 디스크 접근에서
    Python(또는 터미널) 에 권한 부여 필요
  - Messages.app 이 로그인 되어 있어야 합니다

환경변수:
  IMESSAGE_ALLOWED_HANDLES  — 허용할 전화번호/Apple ID (쉼표 구분)
                              미설정 시 모든 연락처 허용
  IMESSAGE_POLL_INTERVAL    — 폴링 간격(초), 기본값 3
  IMESSAGE_DB_PATH          — chat.db 경로
                              기본값: ~/Library/Messages/chat.db
  IMESSAGE_REPLY_HANDLE     — 모든 답장을 강제로 보낼 handle (Apple ID 이메일 권장)
                              설정 시 메시지 발신자 handle 에 무관하게 항상 이 값으로 답장
                              미설정 시 대화방별 첫 메시지 handle 을 기억하여 재사용

참고:
  iMessage 는 동일 대화에서도 handle 이 이메일 ↔ 전화번호로 바뀔 수 있습니다.
  자신의 Mac Apple ID 와 동일한 핸들(전화번호 등)로 답장하면 자기 자신에게
  보내는 메시지처럼 보이는 문제가 발생합니다.
  이를 방지하기 위해 대화방당 최초 수신된 handle 을 고정하여 사용합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from channels.base import ChannelAdapter
from channels.router import InboundEvent, parse_command, route_message
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_LEN = 1000  # iMessage 실용적 최대 길이 (AppleScript 안정성)

# iMessage DB 조회 쿼리
# chat.chat_identifier: 대화방 고유 식별자 (handle 이 바뀌어도 불변)
# chat_identifier NOT LIKE 'chat%': 1:1 대화만 처리 (그룹 채팅 제외)
_QUERY_NEW_MESSAGES = """
SELECT
    m.ROWID,
    c.chat_identifier,
    h.id        AS handle,
    m.text
FROM message m
JOIN handle h ON m.handle_id = h.ROWID
JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
JOIN chat c ON c.ROWID = cmj.chat_id
WHERE m.ROWID > ?
  AND m.is_from_me = 0
  AND m.text IS NOT NULL
  AND m.text != ''
  AND c.chat_identifier NOT LIKE 'chat%'
ORDER BY m.ROWID ASC
"""

_QUERY_MAX_ROWID = "SELECT COALESCE(MAX(ROWID), 0) FROM message"


def _get_db_path() -> Path:
    raw = os.getenv("IMESSAGE_DB_PATH", "")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Library" / "Messages" / "chat.db"


def _run_db_query(db_path: Path, sql: str, params: tuple) -> list[tuple]:
    """블로킹 SQLite 쿼리 실행 (to_thread 에서 호출)."""
    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        logger.warning("chat.db 읽기 실패: %s", exc)
        return []


def _send_via_applescript(handle: str, text: str) -> None:
    """AppleScript 를 통해 iMessage 발신 (블로킹, to_thread 에서 호출).

    handle 은 대화방별로 최초 수신된 발신자 handle(또는 IMESSAGE_REPLY_HANDLE)을
    사용합니다. 이로 인해 iMessage 가 내부적으로 handle 을 전화번호로 바꾸더라도
    항상 동일한 handle 로 답장하여 자기 자신에게 보내는 현상을 방지합니다.
    """
    safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
    safe_handle = handle.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    set targetBuddy to buddy "{safe_handle}" of targetService
    send "{safe_text}" to targetBuddy
end tell
'''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"AppleScript 실패 (handle={handle}): {result.stderr.strip()}"
        )


class IMessageAdapter(ChannelAdapter):
    """iMessage 채널 어댑터 (macOS 전용)."""

    channel_name = "imessage"

    def __init__(self) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("IMessageAdapter 는 macOS 에서만 동작합니다.")
        self._db_path: Path = _get_db_path()
        self._poll_interval: int = int(os.getenv("IMESSAGE_POLL_INTERVAL", "3"))
        self._allowed_handles: list[str] = self._load_allowed_handles()
        self._forced_reply_handle: str = os.getenv("IMESSAGE_REPLY_HANDLE", "").strip()
        self._last_rowid: int = 0
        # chat_identifier → 최초 수신된 handle (답장 대상 고정용)
        self._reply_handle_cache: dict[str, str] = {}

    # ── 허용 핸들 목록 ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_allowed_handles() -> list[str]:
        raw = os.getenv("IMESSAGE_ALLOWED_HANDLES", "")
        return [h.strip() for h in raw.split(",") if h.strip()]

    def is_authorised(self, user_id: str) -> bool:
        """허용 핸들 목록을 확인합니다. 미설정 시 전체 허용."""
        if not self._allowed_handles:
            return True
        # 전화번호는 +82로 시작하거나 010 형식이 올 수 있으므로 정규화 후 비교
        return user_id in self._allowed_handles

    # ── start ─────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """iMessage 폴링을 시작합니다."""
        if not self._db_path.exists():
            logger.error(
                "chat.db 를 찾을 수 없습니다: %s\n"
                "전체 디스크 접근 권한이 부여되었는지 확인하세요.",
                self._db_path,
            )
            return

        # 시작 시 현재 최대 ROWID 를 기준선으로 설정 (과거 메시지 무시)
        rows = await asyncio.to_thread(
            _run_db_query, self._db_path, _QUERY_MAX_ROWID, ()
        )
        self._last_rowid = rows[0][0] if rows else 0
        logger.info(
            "iMessage 폴링 시작 (interval=%ds, last_rowid=%d, db=%s, forced_reply=%s)",
            self._poll_interval,
            self._last_rowid,
            self._db_path,
            self._forced_reply_handle or "(자동)",
        )

        while True:
            await asyncio.sleep(self._poll_interval)
            try:
                await self._poll_new_messages()
            except Exception:
                logger.exception("iMessage 폴링 중 예외 발생")

    # ── 폴링 ─────────────────────────────────────────────────────────────────

    async def _poll_new_messages(self) -> None:
        rows = await asyncio.to_thread(
            _run_db_query,
            self._db_path,
            _QUERY_NEW_MESSAGES,
            (self._last_rowid,),
        )
        for rowid, chat_identifier, handle, text in rows:
            self._last_rowid = max(self._last_rowid, rowid)
            await self._handle_incoming(chat_identifier, handle, text.strip())

    def _resolve_reply_handle(self, chat_identifier: str, handle: str) -> str:
        """답장에 사용할 handle 을 결정합니다.

        우선순위:
          1. IMESSAGE_REPLY_HANDLE 환경변수 (설정 시 항상 이 값 사용)
          2. 대화방별 최초 수신 handle (이후 handle 이 바뀌어도 첫 값 유지)
        """
        if self._forced_reply_handle:
            return self._forced_reply_handle
        if chat_identifier not in self._reply_handle_cache:
            self._reply_handle_cache[chat_identifier] = handle
            logger.debug(
                "iMessage: chat '%s' 의 reply handle 을 '%s' 로 등록",
                chat_identifier,
                handle,
            )
        return self._reply_handle_cache[chat_identifier]

    async def _handle_incoming(self, chat_identifier: str, handle: str, text: str) -> None:
        if not text:
            return

        if not self.is_authorised(handle):
            logger.info("iMessage: 허용되지 않은 핸들 '%s' — 무시", handle)
            return

        reply_handle = self._resolve_reply_handle(chat_identifier, handle)
        logger.info(
            "iMessage ← %s (handle=%s, reply_to=%s): %s",
            chat_identifier,
            handle,
            reply_handle,
            text[:80],
        )

        cmd, args = parse_command(text)
        event = InboundEvent(
            channel=self.channel_name,
            session_id=self.make_session_id(chat_identifier),
            user_id=handle,
            text=text,
            command=cmd,
            args=args,
        )

        try:
            reply = await route_message(event)
        except Exception:
            logger.exception("iMessage route_message error (chat_identifier=%s)", chat_identifier)
            reply = "처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

        await self.send_message(self.make_session_id(reply_handle), reply)

    # ── 발신 ─────────────────────────────────────────────────────────────────

    async def send_message(self, session_id: str, text: str) -> None:
        """iMessage 로 메시지를 전송합니다."""
        handle = session_id.removeprefix(f"{self.channel_name}_")
        for chunk in self.split_message(text, MAX_LEN):
            try:
                await asyncio.to_thread(_send_via_applescript, handle, chunk)
                logger.info("iMessage → %s: %s", handle, chunk[:80])
            except Exception as exc:
                logger.error("iMessage 전송 실패 (handle=%s): %s", handle, exc)
