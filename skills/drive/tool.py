from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)

_MIME_LABELS = {
    "application/vnd.google-apps.document": "Google Docs",
    "application/vnd.google-apps.spreadsheet": "Google Sheets",
    "application/vnd.google-apps.presentation": "Google Slides",
    "application/vnd.google-apps.folder": "폴더",
    "application/pdf": "PDF",
    "text/plain": "텍스트",
}


def _get_drive_service():
    return build("drive", "v3", credentials=get_google_credentials())


def _fmt_file(f: dict[str, Any]) -> str:
    mime = f.get("mimeType", "")
    label = _MIME_LABELS.get(mime, mime.split("/")[-1])
    size = f.get("size", "")
    size_str = f" ({int(size):,} bytes)" if size else ""
    modified = f.get("modifiedTime", "")[:10] if f.get("modifiedTime") else ""
    return f"- [{label}] {f.get('name', '(이름 없음)')} | ID: {f['id']}{size_str} | 수정: {modified}"


@tool
def drive_list(max_results: int = 20, folder_id: str = "") -> str:
    """List recent files in Google Drive.
    Args:
        max_results: Number of files to return (default: 20, max: 50)
        folder_id: Folder ID to list files in. Empty = root/all files.
    """
    try:
        service = _get_drive_service()
        max_results = min(max_results, 50)
        query = f"'{folder_id}' in parents and trashed=false" if folder_id else "trashed=false"
        result = service.files().list(
            q=query,
            pageSize=max_results,
            orderBy="modifiedTime desc",
            fields="files(id,name,mimeType,size,modifiedTime)",
        ).execute()
        files = result.get("files", [])
        if not files:
            return "파일이 없습니다."
        lines = [f"Drive 파일 목록 ({len(files)}개):"] + [_fmt_file(f) for f in files]
        return "\n".join(lines)
    except Exception as e:
        logger.error("drive_list failed: %s", e, exc_info=True)
        return f"파일 목록 조회 실패: {e}"


@tool
def drive_search(query: str, max_results: int = 10) -> str:
    """Search files in Google Drive by name, content, or MIME type.
    Args:
        query: Search query. Examples:
               - 'name contains "보고서"'
               - 'fullText contains "프로젝트"'
               - 'mimeType="application/vnd.google-apps.document"'
               - 'name contains "예산" and mimeType="application/vnd.google-apps.spreadsheet"'
        max_results: Number of results (default: 10)
    """
    try:
        service = _get_drive_service()
        full_query = f"({query}) and trashed=false"
        result = service.files().list(
            q=full_query,
            pageSize=min(max_results, 30),
            fields="files(id,name,mimeType,size,modifiedTime)",
        ).execute()
        files = result.get("files", [])
        if not files:
            return f"'{query}' 검색 결과가 없습니다."
        lines = [f"검색 결과 ({len(files)}개):"] + [_fmt_file(f) for f in files]
        return "\n".join(lines)
    except Exception as e:
        logger.error("drive_search failed: %s", e, exc_info=True)
        return f"파일 검색 실패: {e}"


@tool
def drive_get(file_id: str) -> str:
    """Read the text content of a Google Drive file (Google Docs, Sheets, plain text).
    Args:
        file_id: The file ID from drive_list or drive_search results
    """
    try:
        service = _get_drive_service()
        meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
        mime = meta.get("mimeType", "")
        name = meta.get("name", file_id)

        # Google Workspace 파일 → export
        export_map = {
            "application/vnd.google-apps.document": "text/plain",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "text/plain",
        }
        if mime in export_map:
            content = service.files().export(
                fileId=file_id, mimeType=export_map[mime]
            ).execute()
            text = content.decode("utf-8") if isinstance(content, bytes) else str(content)
            return f"[{name}]\n\n{text[:8000]}"

        # 일반 텍스트 파일
        if mime.startswith("text/"):
            content = service.files().get_media(fileId=file_id).execute()
            text = content.decode("utf-8") if isinstance(content, bytes) else str(content)
            return f"[{name}]\n\n{text[:8000]}"

        return f"'{name}' (타입: {mime}) 은 텍스트로 읽을 수 없습니다."
    except Exception as e:
        logger.error("drive_get failed: %s", e, exc_info=True)
        return f"파일 읽기 실패: {e}"


@tool
def drive_create_folder(name: str, parent_id: str = "") -> str:
    """Create a new folder in Google Drive.
    Args:
        name: Folder name
        parent_id: Parent folder ID. Empty = My Drive root.
    """
    try:
        service = _get_drive_service()
        body: dict[str, Any] = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            body["parents"] = [parent_id]
        folder = service.files().create(body=body, fields="id,name").execute()
        return f"폴더 생성 완료: '{folder['name']}' (ID: {folder['id']})"
    except Exception as e:
        logger.error("drive_create_folder failed: %s", e, exc_info=True)
        return f"폴더 생성 실패: {e}"


@tool
def drive_upload_text(name: str, content: str, folder_id: str = "", as_google_doc: bool = True) -> str:
    """Create a new Google Docs file with the given text content.
    Args:
        name: File name (without extension)
        content: Text content to write
        folder_id: Destination folder ID. Empty = My Drive root.
        as_google_doc: If True, creates as Google Docs format (default: True)
    """
    try:
        from googleapiclient.http import MediaInMemoryUpload
        service = _get_drive_service()
        body: dict[str, Any] = {"name": name}
        if as_google_doc:
            body["mimeType"] = "application/vnd.google-apps.document"
        if folder_id:
            body["parents"] = [folder_id]
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
        file = service.files().create(body=body, media_body=media, fields="id,name,webViewLink").execute()
        return (
            f"파일 생성 완료!\n"
            f"이름: {file.get('name')}\n"
            f"ID: {file.get('id')}\n"
            f"링크: {file.get('webViewLink', '(링크 없음)')}"
        )
    except Exception as e:
        logger.error("drive_upload_text failed: %s", e, exc_info=True)
        return f"파일 생성 실패: {e}"


@tool
def drive_delete(file_id: str) -> str:
    """Delete a file or folder from Google Drive by ID.
    IMPORTANT: Always confirm with the user before deleting.
    Args:
        file_id: The file/folder ID to delete
    """
    try:
        service = _get_drive_service()
        meta = service.files().get(fileId=file_id, fields="name").execute()
        name = meta.get("name", file_id)
        service.files().delete(fileId=file_id).execute()
        return f"'{name}' (ID: {file_id}) 삭제 완료."
    except Exception as e:
        logger.error("drive_delete failed: %s", e, exc_info=True)
        return f"파일 삭제 실패: {e}"


@tool
def drive_move(file_id: str, target_folder_id: str) -> str:
    """Move a file to a different folder in Google Drive.
    Args:
        file_id: The file ID to move
        target_folder_id: Destination folder ID
    """
    try:
        service = _get_drive_service()
        meta = service.files().get(fileId=file_id, fields="name,parents").execute()
        name = meta.get("name", file_id)
        current_parents = ",".join(meta.get("parents", []))
        updated = service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=current_parents,
            fields="id,name,parents",
        ).execute()
        return f"'{name}' 이동 완료 → 폴더 ID: {target_folder_id}"
    except Exception as e:
        logger.error("drive_move failed: %s", e, exc_info=True)
        return f"파일 이동 실패: {e}"


def get_tools() -> list:
    return [drive_list, drive_search, drive_get, drive_create_folder, drive_upload_text, drive_delete, drive_move]
