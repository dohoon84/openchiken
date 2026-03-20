from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_VALID_STATUSES = {"pending", "running", "completed", "failed"}


def _db_path() -> str:
    return settings.database_url.replace("sqlite:///", "")


def _init_table() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS task_store (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT    NOT NULL DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'pending',
                result      TEXT    NOT NULL DEFAULT '',
                created_at  TEXT    NOT NULL,
                updated_at  TEXT    NOT NULL
            )
        """)
        conn.commit()


_init_table()


@tool
def task_create(title: str, description: str = "") -> str:
    """Create a new task entry to track complex or long-running work.
    Use this when starting a multi-step job so progress can be monitored.
    Args:
        title: Short name for the task
        description: Detailed description of what the task involves
    """
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            cur = conn.execute(
                "INSERT INTO task_store (title, description, status, created_at, updated_at) VALUES (?, ?, 'running', ?, ?)",
                (title, description, now, now),
            )
            task_id = cur.lastrowid
        return f"작업이 생성되었습니다. (ID: {task_id}) 제목: {title}"
    except Exception as e:
        logger.error("task_create failed: %s", e, exc_info=True)
        return f"작업 생성 중 오류가 발생했습니다: {e}"


@tool
def task_list(status: str = "all") -> str:
    """List tracked tasks filtered by status.
    Args:
        status: Filter by status – 'all', 'pending', 'running', 'completed', 'failed'
    """
    try:
        with sqlite3.connect(_db_path()) as conn:
            if status == "all":
                rows = conn.execute(
                    "SELECT id, title, status, updated_at FROM task_store ORDER BY updated_at DESC LIMIT 20"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, status, updated_at FROM task_store WHERE status = ? ORDER BY updated_at DESC LIMIT 20",
                    (status,),
                ).fetchall()
        if not rows:
            label = f"'{status}'" if status != "all" else ""
            return f"{label} 작업이 없습니다."
        lines = [f"- [#{row[0]}] [{row[2]}] {row[1]} ({row[3][:16]})" for row in rows]
        return f"작업 목록 ({len(rows)}개):\n" + "\n".join(lines)
    except Exception as e:
        logger.error("task_list failed: %s", e, exc_info=True)
        return f"작업 목록 조회 중 오류가 발생했습니다: {e}"


@tool
def task_complete(task_id: int, result: str = "") -> str:
    """Mark a task as completed and record its result.
    Args:
        task_id: The task ID to update
        result: Summary of what was accomplished
    """
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "UPDATE task_store SET status = 'completed', result = ?, updated_at = ? WHERE id = ?",
                (result, now, task_id),
            ).rowcount
        if affected == 0:
            return f"ID {task_id}인 작업을 찾을 수 없습니다."
        return f"작업 #{task_id}이 완료로 표시되었습니다."
    except Exception as e:
        logger.error("task_complete failed: %s", e, exc_info=True)
        return f"작업 완료 처리 중 오류가 발생했습니다: {e}"


@tool
def task_fail(task_id: int, reason: str = "") -> str:
    """Mark a task as failed and record the reason.
    Args:
        task_id: The task ID to update
        reason: Why the task failed
    """
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "UPDATE task_store SET status = 'failed', result = ?, updated_at = ? WHERE id = ?",
                (reason, now, task_id),
            ).rowcount
        if affected == 0:
            return f"ID {task_id}인 작업을 찾을 수 없습니다."
        return f"작업 #{task_id}이 실패로 표시되었습니다."
    except Exception as e:
        logger.error("task_fail failed: %s", e, exc_info=True)
        return f"작업 실패 처리 중 오류가 발생했습니다: {e}"


def get_task_tools() -> list:
    """Return all task queue tools for agent binding."""
    return [task_create, task_list, task_complete, task_fail]
