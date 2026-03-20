from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)


def _get_gmail_service():
    """Build and return an authenticated Gmail API service."""
    creds = get_google_credentials()
    return build("gmail", "v1", credentials=creds)


def _extract_body(payload: dict[str, Any]) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="replace"
        )

    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return "(본문을 추출할 수 없습니다)"


def _format_message_full(msg: dict[str, Any]) -> str:
    """Format a full Gmail message into a readable string."""
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    body = _extract_body(msg["payload"])
    return (
        f"Message ID: {msg['id']}\n"
        f"From: {headers.get('From', '?')}\n"
        f"To: {headers.get('To', '?')}\n"
        f"Subject: {headers.get('Subject', '(no subject)')}\n"
        f"Date: {headers.get('Date', '?')}\n\n"
        f"{body[:3000]}"
    )


@tool
def gmail_search(query: str, max_results: int = 5) -> str:
    """Search Gmail messages. Use Gmail search syntax (e.g. 'from:user@example.com', 'is:unread', 'subject:meeting').
    Returns a summary of matching emails with their message IDs."""
    try:
        service = _get_gmail_service()
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = results.get("messages", [])
        if not messages:
            return "검색 결과가 없습니다."

        summaries: list[str] = []
        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            summaries.append(
                f"- [ID: {msg_ref['id']}] "
                f"From: {headers.get('From', '?')} | "
                f"Subject: {headers.get('Subject', '(no subject)')} | "
                f"Date: {headers.get('Date', '?')}"
            )

        return f"검색 결과 ({len(summaries)}건):\n" + "\n".join(summaries)
    except Exception as e:
        logger.error("gmail_search failed: %s", e, exc_info=True)
        return f"이메일 검색 중 오류가 발생했습니다: {e}"


@tool
def gmail_read(message_id: str) -> str:
    """Read the full content of a Gmail message by its exact message ID.
    IMPORTANT: Always call gmail_search first to get the exact message ID.
    Args:
        message_id: The exact message ID from gmail_search results
    """
    try:
        service = _get_gmail_service()
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return _format_message_full(msg)
    except Exception as e:
        logger.error("gmail_read failed: %s", e, exc_info=True)
        return f"이메일 읽기 중 오류가 발생했습니다: {e}"


@tool
def gmail_read_latest(query: str = "", max_results: int = 1) -> str:
    """Search Gmail and return the full content of matching emails.
    Use this to read the latest emails without needing to know message IDs.
    Args:
        query: Gmail search query (e.g. 'is:unread', 'from:user@example.com'). Empty string returns the most recent emails.
        max_results: Number of emails to read (default: 1, max: 5)
    """
    try:
        service = _get_gmail_service()
        max_results = min(max_results, 5)

        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )

        messages = results.get("messages", [])
        if not messages:
            return "조건에 맞는 이메일이 없습니다."

        output_parts: list[str] = []
        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_ref["id"], format="full")
                .execute()
            )
            output_parts.append(_format_message_full(msg))

        separator = "\n" + "=" * 40 + "\n"
        return separator.join(output_parts)
    except Exception as e:
        logger.error("gmail_read_latest failed: %s", e, exc_info=True)
        return f"이메일 읽기 중 오류가 발생했습니다: {e}"


@tool
def gmail_send(to: str, subject: str, body: str) -> str:
    """Send an email via Gmail.
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text
    """
    try:
        service = _get_gmail_service()
        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )

        return f"이메일을 성공적으로 전송했습니다. (Message ID: {sent['id']})"
    except Exception as e:
        logger.error("gmail_send failed: %s", e, exc_info=True)
        return f"이메일 전송 중 오류가 발생했습니다: {e}"


@tool
def gmail_list(max_results: int = 10, query: str = "") -> str:
    """List recent emails from Gmail inbox.
    Args:
        max_results: Number of emails to return (default: 10)
        query: Optional Gmail search filter (e.g. 'is:unread', 'from:boss@example.com')
    """
    try:
        service = _get_gmail_service()
        q = query if query else "in:inbox"
        results = (
            service.users()
            .messages()
            .list(userId="me", q=q, maxResults=min(max_results, 30))
            .execute()
        )
        messages = results.get("messages", [])
        if not messages:
            return "이메일이 없습니다."
        summaries: list[str] = []
        for msg_ref in messages:
            msg = (
                service.users()
                .messages()
                .get(
                    userId="me",
                    id=msg_ref["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                )
                .execute()
            )
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            label_ids = msg.get("labelIds", [])
            unread = "🔵 " if "UNREAD" in label_ids else "   "
            summaries.append(
                f"{unread}[{headers.get('Date', '')[:16]}] "
                f"{headers.get('Subject', '(제목 없음)')} | "
                f"From: {headers.get('From', '?')} | ID: {msg_ref['id']}"
            )
        return f"이메일 목록 ({len(summaries)}건):\n" + "\n".join(summaries)
    except Exception as e:
        logger.error("gmail_list failed: %s", e, exc_info=True)
        return f"이메일 목록 조회 실패: {e}"


@tool
def gmail_reply(message_id: str, body: str) -> str:
    """Reply to an existing Gmail message (handles threading automatically).
    Args:
        message_id: The message ID to reply to (from gmail_search or gmail_list)
        body: Reply text content
    """
    try:
        import base64
        from email.mime.text import MIMEText

        service = _get_gmail_service()
        orig = service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["From", "Subject", "Message-ID", "References", "To"],
        ).execute()
        headers = {h["name"]: h["value"] for h in orig["payload"]["headers"]}
        thread_id = orig.get("threadId", "")

        to_addr = headers.get("From", "")
        subject = headers.get("Subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        msg_obj = MIMEText(body)
        msg_obj["To"] = to_addr
        msg_obj["Subject"] = subject
        orig_msg_id = headers.get("Message-ID", "")
        if orig_msg_id:
            msg_obj["In-Reply-To"] = orig_msg_id
            references = headers.get("References", "")
            msg_obj["References"] = f"{references} {orig_msg_id}".strip()

        raw = base64.urlsafe_b64encode(msg_obj.as_bytes()).decode()
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw, "threadId": thread_id})
            .execute()
        )
        return f"'{to_addr}'에게 답장 전송 완료. (Message ID: {sent['id']})"
    except Exception as e:
        logger.error("gmail_reply failed: %s", e, exc_info=True)
        return f"답장 전송 실패: {e}"


@tool
def gmail_mark_read(message_id: str) -> str:
    """Mark a Gmail message as read.
    Args:
        message_id: The message ID to mark as read
    """
    try:
        service = _get_gmail_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        return f"메시지(ID: {message_id})를 읽음 처리했습니다."
    except Exception as e:
        logger.error("gmail_mark_read failed: %s", e, exc_info=True)
        return f"읽음 처리 실패: {e}"


def get_gmail_tools() -> list:
    """Return all Gmail tools for agent binding."""
    return [gmail_search, gmail_read, gmail_read_latest, gmail_send, gmail_list, gmail_reply, gmail_mark_read]


def get_tools() -> list:
    return get_gmail_tools()
