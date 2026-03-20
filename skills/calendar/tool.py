from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _get_calendar_service():
    """Build and return an authenticated Google Calendar API service."""
    creds = get_google_credentials()
    return build("calendar", "v3", credentials=creds)


@tool
def calendar_today(calendar_id: str = "primary") -> str:
    """Get today's events from Google Calendar. Returns a formatted list of today's events."""
    try:
        service = _get_calendar_service()
        now = datetime.now(KST)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_of_day,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy="startTime",
                timeZone="Asia/Seoul",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return "오늘 예정된 일정이 없습니다."

        return "오늘의 일정:\n" + "\n".join(_format_event(e) for e in events)
    except Exception as e:
        logger.error("calendar_today failed: %s", e, exc_info=True)
        return f"오늘 일정을 조회하는 중 오류가 발생했습니다: {e}"


@tool
def calendar_upcoming(days: int = 7, calendar_id: str = "primary") -> str:
    """Get upcoming events from Google Calendar for the next N days.
    Args:
        days: Number of days to look ahead (default: 7)
        calendar_id: Calendar ID (default: primary)
    """
    try:
        service = _get_calendar_service()
        now = datetime.now(KST)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days)).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=20,
                singleEvents=True,
                orderBy="startTime",
                timeZone="Asia/Seoul",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return f"향후 {days}일간 예정된 일정이 없습니다."

        return f"향후 {days}일간 일정:\n" + "\n".join(_format_event(e) for e in events)
    except Exception as e:
        logger.error("calendar_upcoming failed: %s", e, exc_info=True)
        return f"향후 일정을 조회하는 중 오류가 발생했습니다: {e}"


@tool
def calendar_create(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> str:
    """Create a new event on Google Calendar.
    Args:
        summary: Event title
        start_time: Start time in ISO format (e.g. '2025-03-20T09:00:00+09:00')
        end_time: End time in ISO format (e.g. '2025-03-20T10:00:00+09:00')
        description: Optional event description
        location: Optional event location
        calendar_id: Calendar ID (default: primary)
    """
    try:
        service = _get_calendar_service()
        event_body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_time, "timeZone": "Asia/Seoul"},
            "end": {"dateTime": end_time, "timeZone": "Asia/Seoul"},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        logger.info("Creating calendar event: %s", event_body)

        event = service.events().insert(calendarId=calendar_id, body=event_body).execute()

        event_id = event.get("id", "")
        html_link = event.get("htmlLink", "")
        logger.info("Calendar event created successfully: id=%s, link=%s", event_id, html_link)

        return (
            f"일정이 생성되었습니다!\n"
            f"제목: {event.get('summary')}\n"
            f"시간: {start_time} ~ {end_time}\n"
            f"링크: {html_link}"
        )
    except Exception as e:
        logger.error("calendar_create failed: %s", e, exc_info=True)
        return f"일정 생성에 실패했습니다: {e}"


@tool
def calendar_delete(event_id: str, calendar_id: str = "primary") -> str:
    """Delete an event from Google Calendar by its exact event ID.
    IMPORTANT: Always call calendar_today first to get the exact event ID before deleting.
    Args:
        event_id: The exact event ID (from calendar_today results)
        calendar_id: Calendar ID (default: primary)
    """
    try:
        service = _get_calendar_service()
        logger.info("Deleting calendar event: id=%s", event_id)
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        logger.info("Calendar event deleted successfully: id=%s", event_id)
        return f"일정(ID: {event_id})이 삭제되었습니다."
    except Exception as e:
        logger.error("calendar_delete failed: %s", e, exc_info=True)
        return f"일정 삭제에 실패했습니다: {e}"


@tool
def calendar_delete_by_name(
    keyword: str,
    calendar_id: str = "primary",
) -> str:
    """Find and delete a calendar event by searching its title (summary).
    Use this when you know the event name but not the exact event ID.
    Args:
        keyword: A keyword to search in event titles (e.g. '헬스장')
        calendar_id: Calendar ID (default: primary)
    """
    try:
        service = _get_calendar_service()
        now = datetime.now(KST)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end_of_search = (now + timedelta(days=30)).isoformat()

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=start_of_day,
                timeMax=end_of_search,
                singleEvents=True,
                orderBy="startTime",
                q=keyword,
                timeZone="Asia/Seoul",
            )
            .execute()
        )

        events = events_result.get("items", [])
        if not events:
            return f"'{keyword}' 키워드와 일치하는 일정을 찾을 수 없습니다."

        deleted: list[str] = []
        for event in events:
            eid = event["id"]
            summary = event.get("summary", "(제목 없음)")
            logger.info("Deleting matched event: id=%s, summary=%s", eid, summary)
            service.events().delete(calendarId=calendar_id, eventId=eid).execute()
            deleted.append(f"- {summary} (ID: {eid})")

        return f"다음 일정을 삭제했습니다:\n" + "\n".join(deleted)
    except Exception as e:
        logger.error("calendar_delete_by_name failed: %s", e, exc_info=True)
        return f"일정 삭제에 실패했습니다: {e}"


def _format_event(event: dict[str, Any]) -> str:
    """Format a single calendar event into a readable string."""
    start = event["start"].get("dateTime", event["start"].get("date", ""))
    end = event["end"].get("dateTime", event["end"].get("date", ""))
    summary = event.get("summary", "(제목 없음)")
    location = event.get("location", "")
    event_id = event.get("id", "")

    line = f"- [{start} ~ {end}] {summary}"
    if location:
        line += f" @ {location}"
    line += f" (ID: {event_id})"
    return line


def get_calendar_tools() -> list:
    """Return all Calendar tools for agent binding."""
    return [
        calendar_today,
        calendar_upcoming,
        calendar_create,
        calendar_delete,
        calendar_delete_by_name,
    ]
