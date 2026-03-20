from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)


def _get_docs_service():
    return build("docs", "v1", credentials=get_google_credentials())


def _get_drive_service():
    return build("drive", "v3", credentials=get_google_credentials())


def _extract_text(doc: dict[str, Any]) -> str:
    """Google Docs body 구조에서 평문 텍스트 추출"""
    parts: list[str] = []
    for elem in doc.get("body", {}).get("content", []):
        para = elem.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements", []):
            tr = pe.get("textRun")
            if tr:
                parts.append(tr.get("content", ""))
    return "".join(parts)


@tool
def docs_read(document_id: str) -> str:
    """Read the full text content of a Google Docs document.
    Args:
        document_id: Document ID (from URL: /document/d/{ID}/edit)
    """
    try:
        service = _get_docs_service()
        doc = service.documents().get(documentId=document_id).execute()
        title = doc.get("title", "(제목 없음)")
        text = _extract_text(doc)
        return f"[{title}]\n\n{text[:10000]}"
    except Exception as e:
        logger.error("docs_read failed: %s", e, exc_info=True)
        return f"문서 읽기 실패: {e}"


@tool
def docs_create(title: str, content: str = "") -> str:
    """Create a new Google Docs document with optional initial content.
    Args:
        title: Document title
        content: Initial text content (optional)
    """
    try:
        docs_service = _get_docs_service()
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc.get("documentId")
        url = f"https://docs.google.com/document/d/{doc_id}/edit"

        if content:
            requests = [{"insertText": {"location": {"index": 1}, "text": content}}]
            docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()

        return f"문서 생성 완료!\n제목: {title}\nID: {doc_id}\n링크: {url}"
    except Exception as e:
        logger.error("docs_create failed: %s", e, exc_info=True)
        return f"문서 생성 실패: {e}"


@tool
def docs_append(document_id: str, text: str) -> str:
    """Append text to the end of a Google Docs document.
    Args:
        document_id: Document ID
        text: Text to append
    """
    try:
        service = _get_docs_service()
        doc = service.documents().get(documentId=document_id).execute()
        title = doc.get("title", document_id)

        # 문서 마지막 인덱스 계산
        content = doc.get("body", {}).get("content", [])
        end_index = max(
            (elem.get("endIndex", 1) for elem in content),
            default=1,
        ) - 1  # 마지막 줄바꿈 앞에 삽입

        if end_index < 1:
            end_index = 1

        requests = [{"insertText": {"location": {"index": end_index}, "text": "\n" + text}}]
        service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()
        return f"'{title}' 문서에 텍스트 추가 완료."
    except Exception as e:
        logger.error("docs_append failed: %s", e, exc_info=True)
        return f"텍스트 추가 실패: {e}"


@tool
def docs_replace(document_id: str, find_text: str, replace_text: str) -> str:
    """Find and replace text in a Google Docs document.
    Args:
        document_id: Document ID
        find_text: Text to find
        replace_text: Replacement text
    """
    try:
        service = _get_docs_service()
        doc = service.documents().get(documentId=document_id, fields="title").execute()
        title = doc.get("title", document_id)

        requests = [{
            "replaceAllText": {
                "containsText": {"text": find_text, "matchCase": True},
                "replaceText": replace_text,
            }
        }]
        result = service.documents().batchUpdate(
            documentId=document_id,
            body={"requests": requests},
        ).execute()
        count = (
            result.get("replies", [{}])[0]
            .get("replaceAllText", {})
            .get("occurrencesChanged", 0)
        )
        return f"'{title}' 에서 '{find_text}' → '{replace_text}' 로 {count}곳 교체 완료."
    except Exception as e:
        logger.error("docs_replace failed: %s", e, exc_info=True)
        return f"텍스트 교체 실패: {e}"


@tool
def docs_list(max_results: int = 10) -> str:
    """List recent Google Docs documents.
    Args:
        max_results: Number of documents to return (default: 10)
    """
    try:
        drive = _get_drive_service()
        result = drive.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            pageSize=min(max_results, 30),
            orderBy="modifiedTime desc",
            fields="files(id,name,modifiedTime)",
        ).execute()
        files = result.get("files", [])
        if not files:
            return "Google Docs 문서가 없습니다."
        lines = [f"최근 Docs 문서 ({len(files)}개):"]
        for f in files:
            modified = f.get("modifiedTime", "")[:10]
            lines.append(f"  - {f['name']} | ID: {f['id']} | 수정: {modified}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("docs_list failed: %s", e, exc_info=True)
        return f"문서 목록 조회 실패: {e}"


def get_tools() -> list:
    return [docs_read, docs_create, docs_append, docs_replace, docs_list]
