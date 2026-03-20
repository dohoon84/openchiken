from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


def _calendar_service():
    return build("calendar", "v3", credentials=get_google_credentials())


def _gmail_service():
    return build("gmail", "v1", credentials=get_google_credentials())


def _drive_service():
    return build("drive", "v3", credentials=get_google_credentials())


def _get_today_events() -> list[dict]:
    service = _calendar_service()
    now = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    result = service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime",
        timeZone="Asia/Seoul",
    ).execute()
    return result.get("items", [])


def _get_upcoming_events(days: int) -> list[dict]:
    service = _calendar_service()
    now = datetime.now(KST)
    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=(now + timedelta(days=days)).isoformat(),
        maxResults=30,
        singleEvents=True,
        orderBy="startTime",
        timeZone="Asia/Seoul",
    ).execute()
    return result.get("items", [])


def _fmt_event(e: dict) -> str:
    start = e["start"].get("dateTime", e["start"].get("date", ""))[:16]
    end = e["end"].get("dateTime", e["end"].get("date", ""))[:16]
    summary = e.get("summary", "(제목 없음)")
    location = f" @ {e['location']}" if e.get("location") else ""
    attendees = e.get("attendees", [])
    attendee_str = f" | 참석: {len(attendees)}명" if attendees else ""
    return f"  - [{start} ~ {end}] {summary}{location}{attendee_str}"


def _get_unread_email_summary(max_results: int = 5) -> list[str]:
    service = _gmail_service()
    result = service.users().messages().list(
        userId="me", q="is:unread", maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    summaries = []
    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me",
            id=msg_ref["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        summaries.append(
            f"  - {headers.get('Subject', '(제목 없음)')} | From: {headers.get('From', '?')}"
        )
    return summaries


@tool
def workflow_standup_report() -> str:
    """Generate a standup report: today's calendar events + unread emails summary.
    Use this when user asks for a daily standup, morning report, or today's summary.
    """
    try:
        lines = [f"📋 스탠드업 리포트 — {datetime.now(KST).strftime('%Y-%m-%d (%a)')}"]

        # 오늘 일정
        events = _get_today_events()
        lines.append(f"\n📅 오늘 일정 ({len(events)}건):")
        if events:
            lines.extend(_fmt_event(e) for e in events)
        else:
            lines.append("  (일정 없음)")

        # 미처리 이메일
        unread = _get_unread_email_summary(5)
        lines.append(f"\n📧 미처리 이메일 (최근 {len(unread)}건):")
        if unread:
            lines.extend(unread)
        else:
            lines.append("  (미처리 이메일 없음)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("workflow_standup_report failed: %s", e, exc_info=True)
        return f"스탠드업 리포트 생성 실패: {e}"


@tool
def workflow_weekly_digest() -> str:
    """Generate a weekly digest: this week's calendar events + email count summary.
    Use this when user asks for a weekly summary or this week's overview.
    """
    try:
        now = datetime.now(KST)
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        lines = [
            f"📊 주간 다이제스트 — {week_start.strftime('%m/%d')} ~ {week_end.strftime('%m/%d')} ({now.strftime('%Y')})"
        ]

        # 이번 주 일정
        events = _get_upcoming_events(7)
        lines.append(f"\n📅 이번 주 남은 일정 ({len(events)}건):")
        if events:
            lines.extend(_fmt_event(e) for e in events)
        else:
            lines.append("  (일정 없음)")

        # 이메일 현황
        service = _gmail_service()
        unread_result = service.users().messages().list(
            userId="me", q="is:unread", maxResults=1
        ).execute()
        unread_total = unread_result.get("resultSizeEstimate", 0)

        today_result = service.users().messages().list(
            userId="me",
            q=f"after:{now.strftime('%Y/%m/%d')}",
            maxResults=1,
        ).execute()
        today_count = today_result.get("resultSizeEstimate", 0)

        lines.append(f"\n📧 이메일 현황:")
        lines.append(f"  - 미처리(읽지 않음): {unread_total}건")
        lines.append(f"  - 오늘 받은 메일: {today_count}건")

        return "\n".join(lines)
    except Exception as e:
        logger.error("workflow_weekly_digest failed: %s", e, exc_info=True)
        return f"주간 다이제스트 생성 실패: {e}"


@tool
def workflow_meeting_prep(event_keyword: str = "") -> str:
    """Prepare for the next upcoming meeting: event details + related unread emails.
    Args:
        event_keyword: Keyword to filter meetings by title. Empty = next meeting.
    """
    try:
        events = _get_upcoming_events(7)
        if not events:
            return "예정된 미팅이 없습니다."

        if event_keyword:
            events = [e for e in events if event_keyword.lower() in e.get("summary", "").lower()]
            if not events:
                return f"'{event_keyword}' 키워드와 일치하는 미팅이 없습니다."

        event = events[0]
        summary = event.get("summary", "(제목 없음)")
        start = event["start"].get("dateTime", event["start"].get("date", ""))[:16]
        end = event["end"].get("dateTime", event["end"].get("date", ""))[:16]
        location = event.get("location", "")
        description = event.get("description", "")
        attendees = event.get("attendees", [])

        lines = [
            f"🗓️ 미팅 준비 — {summary}",
            f"  시간: {start} ~ {end}",
        ]
        if location:
            lines.append(f"  장소: {location}")
        if attendees:
            lines.append(f"  참석자 ({len(attendees)}명):")
            for a in attendees[:10]:
                status = {"accepted": "✓", "declined": "✗", "tentative": "?"}.get(
                    a.get("responseStatus", ""), "·"
                )
                lines.append(f"    {status} {a.get('displayName', a.get('email', '?'))}")
        if description:
            lines.append(f"  안건:\n    {description[:500]}")

        # 관련 이메일 검색
        gmail = _gmail_service()
        search_query = f'subject:"{summary}"'
        email_result = gmail.users().messages().list(
            userId="me", q=search_query, maxResults=3
        ).execute()
        emails = email_result.get("messages", [])
        if emails:
            lines.append(f"\n📧 관련 이메일 ({len(emails)}건):")
            for msg_ref in emails:
                msg = gmail.users().messages().get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                lines.append(
                    f"  - {headers.get('Subject', '?')} | {headers.get('From', '?')} | {headers.get('Date', '')[:16]}"
                )
        else:
            lines.append("\n📧 관련 이메일 없음")

        return "\n".join(lines)
    except Exception as e:
        logger.error("workflow_meeting_prep failed: %s", e, exc_info=True)
        return f"미팅 준비 실패: {e}"


@tool
def workflow_morning_briefing() -> str:
    """Generate a morning briefing: today's schedule + top unread emails.
    Use when user asks for a morning briefing or daily overview.
    """
    try:
        now = datetime.now(KST)
        lines = [f"☀️ 모닝 브리핑 — {now.strftime('%Y년 %m월 %d일 (%A)')}"]

        # 오늘 일정
        events = _get_today_events()
        lines.append(f"\n📅 오늘 일정 ({len(events)}건):")
        if events:
            lines.extend(_fmt_event(e) for e in events)
        else:
            lines.append("  오늘 일정이 없습니다. 여유로운 하루 되세요!")

        # 중요 이메일 (최근 3건)
        unread = _get_unread_email_summary(3)
        lines.append(f"\n📧 확인이 필요한 이메일 ({len(unread)}건):")
        if unread:
            lines.extend(unread)
        else:
            lines.append("  새로운 이메일이 없습니다.")

        # 내일 첫 번째 일정 미리보기
        tomorrow_events = []
        tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0)
        tomorrow_end = tomorrow_start + timedelta(days=1)
        service = _calendar_service()
        result = service.events().list(
            calendarId="primary",
            timeMin=tomorrow_start.isoformat(),
            timeMax=tomorrow_end.isoformat(),
            maxResults=3,
            singleEvents=True,
            orderBy="startTime",
            timeZone="Asia/Seoul",
        ).execute()
        tomorrow_events = result.get("items", [])
        if tomorrow_events:
            lines.append(f"\n📌 내일 미리보기 ({len(tomorrow_events)}건):")
            lines.extend(_fmt_event(e) for e in tomorrow_events)

        return "\n".join(lines)
    except Exception as e:
        logger.error("workflow_morning_briefing failed: %s", e, exc_info=True)
        return f"모닝 브리핑 생성 실패: {e}"


@tool
def workflow_email_to_task(message_id: str) -> str:
    """Convert a Gmail message into a memo/task note.
    Args:
        message_id: Gmail message ID (from gmail_search results)
    """
    try:
        service = _gmail_service()
        import base64
        msg = service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        subject = headers.get("Subject", "(제목 없음)")
        sender = headers.get("From", "?")
        date = headers.get("Date", "")[:16]

        # 본문 추출
        def extract_body(payload: dict) -> str:
            if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
            for part in payload.get("parts", []):
                text = extract_body(part)
                if text:
                    return text
            return ""

        body = extract_body(msg["payload"])[:1000]
        task_content = (
            f"[이메일 → 할 일]\n"
            f"제목: {subject}\n"
            f"발신: {sender}\n"
            f"날짜: {date}\n\n"
            f"내용 요약:\n{body}"
        )
        return task_content
    except Exception as e:
        logger.error("workflow_email_to_task failed: %s", e, exc_info=True)
        return f"이메일 → 할 일 변환 실패: {e}"


@tool
def workflow_file_announce(file_id: str, to: str, message: str = "") -> str:
    """Share a Google Drive file by sending its link via email.
    Args:
        file_id: Drive file ID
        to: Recipient email address
        message: Optional personal message to include
    """
    try:
        import base64
        from email.mime.text import MIMEText

        drive = _drive_service()
        meta = drive.files().get(fileId=file_id, fields="name,webViewLink").execute()
        name = meta.get("name", file_id)
        link = meta.get("webViewLink", f"https://drive.google.com/file/d/{file_id}")

        body_text = f"안녕하세요,\n\n아래 파일을 공유드립니다.\n\n📄 {name}\n🔗 {link}"
        if message:
            body_text = f"{message}\n\n{body_text}"

        gmail = _gmail_service()
        msg_obj = MIMEText(body_text)
        msg_obj["to"] = to
        msg_obj["subject"] = f"[파일 공유] {name}"
        raw = base64.urlsafe_b64encode(msg_obj.as_bytes()).decode()
        sent = gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
        return f"'{name}' 파일 링크를 {to}에게 이메일로 전송했습니다. (Message ID: {sent['id']})"
    except Exception as e:
        logger.error("workflow_file_announce failed: %s", e, exc_info=True)
        return f"파일 공유 이메일 전송 실패: {e}"


def get_tools() -> list:
    return [
        workflow_standup_report,
        workflow_weekly_digest,
        workflow_morning_briefing,
        workflow_meeting_prep,
        workflow_email_to_task,
        workflow_file_announce,
    ]
