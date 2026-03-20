from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build
from langchain_core.tools import tool

from core.google_auth import get_google_credentials

logger = logging.getLogger(__name__)


def _get_sheets_service():
    return build("sheets", "v4", credentials=get_google_credentials())


def _get_drive_service():
    return build("drive", "v3", credentials=get_google_credentials())


def _rows_to_text(values: list[list[Any]], range_name: str) -> str:
    if not values:
        return f"[{range_name}] 데이터가 없습니다."
    lines = [f"[{range_name}] ({len(values)}행 × {max(len(r) for r in values)}열):"]
    for i, row in enumerate(values):
        lines.append(f"  행{i+1}: {' | '.join(str(c) for c in row)}")
    return "\n".join(lines)


@tool
def sheets_read(spreadsheet_id: str, range_name: str = "A1:Z100") -> str:
    """Read data from a Google Sheets spreadsheet.
    Args:
        spreadsheet_id: Spreadsheet ID (from URL: /spreadsheets/d/{ID}/edit)
        range_name: Cell range in A1 notation (e.g. 'Sheet1!A1:C10' or 'A1:Z100')
    """
    try:
        service = _get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name,
        ).execute()
        values = result.get("values", [])
        return _rows_to_text(values, range_name)
    except Exception as e:
        logger.error("sheets_read failed: %s", e, exc_info=True)
        return f"스프레드시트 읽기 실패: {e}"


@tool
def sheets_write(spreadsheet_id: str, range_name: str, values: str) -> str:
    """Write data to a Google Sheets spreadsheet.
    Args:
        spreadsheet_id: Spreadsheet ID
        range_name: Starting cell in A1 notation (e.g. 'Sheet1!A1' or 'B2')
        values: Data to write as JSON-like string. Each inner list is a row.
                Example: '[["이름","나이"],["김철수",30],["이영희",25]]'
    """
    try:
        import json
        service = _get_sheets_service()
        try:
            data = json.loads(values)
        except json.JSONDecodeError:
            # 단일 행 문자열 처리 (쉼표 구분)
            data = [[v.strip() for v in values.split(",")]]

        body = {"values": data, "majorDimension": "ROWS"}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
        updated = result.get("updatedCells", 0)
        return f"{range_name}에 {updated}개 셀 데이터 입력 완료."
    except Exception as e:
        logger.error("sheets_write failed: %s", e, exc_info=True)
        return f"스프레드시트 쓰기 실패: {e}"


@tool
def sheets_append(spreadsheet_id: str, values: str, sheet_name: str = "Sheet1") -> str:
    """Append rows to the end of a Google Sheets sheet.
    Args:
        spreadsheet_id: Spreadsheet ID
        values: Rows to append as JSON string. Example: '[["홍길동","010-1234-5678"],["김철수","010-9876-5432"]]'
                Or a single row: '"홍길동,010-1234-5678"' (comma-separated)
        sheet_name: Sheet tab name (default: Sheet1)
    """
    try:
        import json
        service = _get_sheets_service()
        try:
            data = json.loads(values)
            if data and not isinstance(data[0], list):
                data = [data]
        except (json.JSONDecodeError, TypeError):
            data = [[v.strip() for v in values.split(",")]]

        body = {"values": data, "majorDimension": "ROWS"}
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()
        updated = result.get("updates", {}).get("updatedRows", len(data))
        return f"'{sheet_name}' 시트에 {updated}행 추가 완료."
    except Exception as e:
        logger.error("sheets_append failed: %s", e, exc_info=True)
        return f"행 추가 실패: {e}"


@tool
def sheets_create(title: str) -> str:
    """Create a new Google Sheets spreadsheet.
    Args:
        title: Spreadsheet title
    """
    try:
        service = _get_sheets_service()
        body = {"properties": {"title": title}}
        spreadsheet = service.spreadsheets().create(body=body, fields="spreadsheetId,spreadsheetUrl").execute()
        sid = spreadsheet.get("spreadsheetId")
        url = spreadsheet.get("spreadsheetUrl")
        return f"스프레드시트 생성 완료!\n제목: {title}\nID: {sid}\n링크: {url}"
    except Exception as e:
        logger.error("sheets_create failed: %s", e, exc_info=True)
        return f"스프레드시트 생성 실패: {e}"


@tool
def sheets_info(spreadsheet_id: str) -> str:
    """Get spreadsheet metadata: title, sheet list, and row/column counts.
    Args:
        spreadsheet_id: Spreadsheet ID
    """
    try:
        service = _get_sheets_service()
        result = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties,sheets(properties)",
        ).execute()
        title = result["properties"]["title"]
        sheets = result.get("sheets", [])
        lines = [f"스프레드시트: {title}", f"시트 수: {len(sheets)}"]
        for s in sheets:
            p = s["properties"]
            lines.append(
                f"  - {p['title']} (ID: {p['sheetId']}, "
                f"{p['gridProperties']['rowCount']}행 × {p['gridProperties']['columnCount']}열)"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error("sheets_info failed: %s", e, exc_info=True)
        return f"스프레드시트 정보 조회 실패: {e}"


@tool
def sheets_clear(spreadsheet_id: str, range_name: str) -> str:
    """Clear data in a specific cell range of a spreadsheet.
    IMPORTANT: Confirm with user before clearing.
    Args:
        spreadsheet_id: Spreadsheet ID
        range_name: Range to clear, e.g. 'Sheet1!A2:Z100'
    """
    try:
        service = _get_sheets_service()
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={},
        ).execute()
        return f"[{range_name}] 데이터 삭제 완료."
    except Exception as e:
        logger.error("sheets_clear failed: %s", e, exc_info=True)
        return f"데이터 삭제 실패: {e}"


def get_tools() -> list:
    return [sheets_read, sheets_write, sheets_append, sheets_create, sheets_info, sheets_clear]
