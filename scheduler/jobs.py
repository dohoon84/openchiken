from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build

from config.settings import settings
from core.google_auth import get_google_credentials
from skills.calendar.tool import calendar_today, calendar_upcoming
from skills.gmail.tool import gmail_search

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _db_path() -> str:
    return settings.database_url.replace("sqlite:///", "")


def _init_reminder_table() -> None:
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_sent (
                event_id TEXT PRIMARY KEY,
                sent_at  TEXT NOT NULL
            )
        """)
        conn.commit()


_init_reminder_table()


def _split(text: str, limit: int = 4096) -> list[str]:
    """Split long text into Telegram-safe chunks."""
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


async def _send(bot, user_id: int, text: str) -> None:
    for chunk in _split(text):
        await bot.send_message(chat_id=user_id, text=chunk)


async def job_morning_briefing(bot) -> None:
    """매일 아침 오늘 일정 + 읽지 않은 이메일 요약을 전송합니다."""
    users = settings.allowed_user_ids
    if not users:
        logger.warning("morning_briefing: ALLOWED_USER_IDS가 설정되지 않아 건너뜁니다.")
        return

    now = datetime.now(KST)
    day_str = now.strftime("%Y년 %m월 %d일 (%A)")

    try:
        schedule = calendar_today.invoke({})
    except Exception as e:
        schedule = f"일정 조회 실패: {e}"

    try:
        emails = gmail_search.invoke({"query": "is:unread", "max_results": 5})
    except Exception as e:
        emails = f"이메일 조회 실패: {e}"

    message = (
        f"☀️ 굿모닝! {day_str} 브리핑입니다.\n\n"
        f"📅 오늘 일정\n{schedule}\n\n"
        f"📧 읽지 않은 이메일\n{emails}"
    )

    for user_id in users:
        try:
            await _send(bot, user_id, message)
            logger.info("morning_briefing 전송 완료 → user %s", user_id)
        except Exception as e:
            logger.error("morning_briefing 전송 실패 (user %s): %s", user_id, e)


async def job_event_reminder(bot) -> None:
    """매 5분마다 실행되어 15분 후 시작하는 일정을 리마인드합니다."""
    users = settings.allowed_user_ids
    if not users:
        return

    remind_before = settings.reminder_minutes_before

    try:
        creds = get_google_credentials()
        service = build("calendar", "v3", credentials=creds)

        now = datetime.now(KST)
        remind_start = (now + timedelta(minutes=remind_before - 1)).isoformat()
        remind_end = (now + timedelta(minutes=remind_before + 1)).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=remind_start,
                timeMax=remind_end,
                singleEvents=True,
                orderBy="startTime",
                timeZone="Asia/Seoul",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return

        db_path = _db_path()
        for event in events:
            event_id = event["id"]
            summary = event.get("summary", "(제목 없음)")
            start = event["start"].get("dateTime", event["start"].get("date", ""))
            location = event.get("location", "")

            with sqlite3.connect(db_path) as conn:
                already_sent = conn.execute(
                    "SELECT 1 FROM reminder_sent WHERE event_id = ?", (event_id,)
                ).fetchone()

            if already_sent:
                continue

            lines = [
                f"⏰ {remind_before}분 후 일정 알림",
                f"",
                f"📌 {summary}",
                f"🕐 {start}",
            ]
            if location:
                lines.append(f"📍 {location}")

            message = "\n".join(lines)

            for user_id in users:
                try:
                    await _send(bot, user_id, message)
                    logger.info("event_reminder 전송 완료 (event=%s, user=%s)", summary, user_id)
                except Exception as e:
                    logger.error("event_reminder 전송 실패 (user %s): %s", user_id, e)

            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO reminder_sent (event_id, sent_at) VALUES (?, ?)",
                    (event_id, now.isoformat()),
                )

    except Exception as e:
        logger.error("job_event_reminder 실패: %s", e, exc_info=True)


async def job_weekly_briefing(bot) -> None:
    """매주 월요일 아침 이번 주 일정 전체를 전송합니다."""
    users = settings.allowed_user_ids
    if not users:
        return

    try:
        schedule = calendar_upcoming.invoke({"days": 7})
    except Exception as e:
        schedule = f"일정 조회 실패: {e}"

    now = datetime.now(KST)
    message = (
        f"📋 이번 주 일정 브리핑 ({now.strftime('%m월 %d일')} 기준)\n\n"
        f"{schedule}"
    )

    for user_id in users:
        try:
            await _send(bot, user_id, message)
            logger.info("weekly_briefing 전송 완료 → user %s", user_id)
        except Exception as e:
            logger.error("weekly_briefing 전송 실패 (user %s): %s", user_id, e)
