from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _db_path() -> str:
    return settings.database_url.replace("sqlite:///", "")


def _init_table() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memo_store (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL UNIQUE,
                content    TEXT    NOT NULL,
                created_at TEXT    NOT NULL,
                updated_at TEXT    NOT NULL
            )
        """)
        conn.commit()


_init_table()


@tool
def memo_save(title: str, content: str) -> str:
    """Save or update a memo with a given title and content.
    Use this to remember important information such as user preferences,
    key facts mentioned in conversation, or anything worth keeping long-term.
    If a memo with the same title already exists, it will be overwritten.
    Args:
        title: Short descriptive title for the memo (used as unique key)
        content: The content to save
    """
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            exists = conn.execute(
                "SELECT id FROM memo_store WHERE title = ?", (title,)
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE memo_store SET content = ?, updated_at = ? WHERE title = ?",
                    (content, now, title),
                )
                return f"메모 '{title}'가 업데이트되었습니다."
            else:
                conn.execute(
                    "INSERT INTO memo_store (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (title, content, now, now),
                )
                return f"메모 '{title}'가 저장되었습니다."
    except Exception as e:
        logger.error("memo_save failed: %s", e, exc_info=True)
        return f"메모 저장 중 오류가 발생했습니다: {e}"


@tool
def memo_list() -> str:
    """List all saved memos showing their titles and last updated time.
    Use this to browse what information has been saved before reading a specific one.
    """
    try:
        with sqlite3.connect(_db_path()) as conn:
            rows = conn.execute(
                "SELECT title, updated_at FROM memo_store ORDER BY updated_at DESC"
            ).fetchall()
        if not rows:
            return "저장된 메모가 없습니다."
        lines = [f"- [{row[1][:16]}] {row[0]}" for row in rows]
        return f"저장된 메모 ({len(rows)}개):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("memo_list failed: %s", e, exc_info=True)
        return f"메모 목록 조회 중 오류가 발생했습니다: {e}"


@tool
def memo_read(title: str) -> str:
    """Read the full content of a specific memo by its title.
    Args:
        title: The exact title of the memo to read
    """
    try:
        with sqlite3.connect(_db_path()) as conn:
            row = conn.execute(
                "SELECT title, content, updated_at FROM memo_store WHERE title = ?",
                (title,),
            ).fetchone()
        if not row:
            return f"'{title}' 제목의 메모를 찾을 수 없습니다. memo_list로 목록을 확인하세요."
        return f"[{row[2][:16]}] {row[0]}\n\n{row[1]}"
    except Exception as e:
        logger.error("memo_read failed: %s", e, exc_info=True)
        return f"메모 읽기 중 오류가 발생했습니다: {e}"


@tool
def memo_delete(title: str) -> str:
    """Delete a memo by its title.
    Args:
        title: The exact title of the memo to delete
    """
    try:
        with sqlite3.connect(_db_path()) as conn:
            result = conn.execute(
                "DELETE FROM memo_store WHERE title = ?", (title,)
            )
        if result.rowcount == 0:
            return f"'{title}' 제목의 메모를 찾을 수 없습니다."
        return f"메모 '{title}'가 삭제되었습니다."
    except Exception as e:
        logger.error("memo_delete failed: %s", e, exc_info=True)
        return f"메모 삭제 중 오류가 발생했습니다: {e}"


def get_memo_tools() -> list:
    """Return all memo tools for agent binding."""
    return [memo_save, memo_list, memo_read, memo_delete]
