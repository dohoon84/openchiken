#!/usr/bin/env python3
"""
OpenChiken Web Server
─────────────────────
FastAPI — 로컬 전용 온보딩(/setup) · 관리 UI(local_ui/) + /static 자산
  uv run python server.py

공개 랜딩(landing/)은 별도 도메인 정적 배포. 이 서버 루트(/)는 온보딩으로 연결됩니다.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

# ── 경로 설정 ──────────────────────────────────────────────────
ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
LOCAL_UI_DIR = ROOT / "local_ui"
OPENCHIKEN_HOME = Path.home() / ".openchiken"
ENV_FILE = OPENCHIKEN_HOME / ".env"
CREDENTIALS_DST = OPENCHIKEN_HOME / "credentials.json"

app = FastAPI(title="OpenChiken Web Server", docs_url=None, redoc_url=None)

# main.py 서브프로세스 핸들 (단일 인스턴스 관리)
_main_proc: subprocess.Popen | None = None


# ── Pydantic 모델 ──────────────────────────────────────────────
class SetupConfig(BaseModel):
    # Step 1 — Persona
    ASSISTANT_NAME: str = "치킨"
    ASSISTANT_TONE: str = ""
    ASSISTANT_PERSONA: str = ""
    ASSISTANT_EXTRA: str = ""
    # Step 2 — LLM
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    # Step 3 — Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    ALLOWED_USER_IDS: str = ""
    # Step 5 — Database
    DATABASE_URL: str = "sqlite:///openchiken.db"
    # Step 6 — Scheduler
    MORNING_BRIEFING_HOUR: str = "8"
    REMINDER_MINUTES_BEFORE: str = "15"
    # Step 7 — Skills (all | comma-separated skill ids)
    ENABLED_SKILLS: str = "all"
    # Step 8 — Channels
    SLACK_BOT_TOKEN: str = ""
    SLACK_APP_TOKEN: str = ""
    DISCORD_BOT_TOKEN: str = ""
    IMESSAGE_ALLOWED_HANDLES: str = ""
    IMESSAGE_POLL_INTERVAL: str = "3"
    ENABLED_CHANNELS: str = "telegram"


# ── API 라우터 ─────────────────────────────────────────────────

@app.get("/")
def root_redirect():
    """셋업 완료(.env 존재) 시 대시보드로, 미완료 시 온보딩으로 이동."""
    if ENV_FILE.exists():
        return RedirectResponse(url="/dashboard.html", status_code=302)
    return RedirectResponse(url="/setup.html", status_code=302)


@app.get("/api/setup/status")
def get_setup_status():
    """셋업 완료 여부 확인"""
    env_exists = ENV_FILE.exists()
    credentials_exists = CREDENTIALS_DST.exists() or (ROOT / "credentials.json").exists()
    return {
        "completed": env_exists,
        "env_file": str(ENV_FILE),
        "has_credentials": credentials_exists,
    }


@app.post("/api/setup/save")
def save_setup(config: SetupConfig):
    """설정을 .env 파일로 저장"""
    try:
        OPENCHIKEN_HOME.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"홈 디렉토리 생성 실패: {e}")

    def keep(new: str, env_key: str) -> str:
        """빈 값이면 기존 환경변수를 유지 (API 키 보호)."""
        return new if new else os.getenv(env_key, "")

    lines = [
        "# OpenChiken 환경 설정 – web setup wizard 로 생성됨",
        f"# {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# ── Persona ──────────────────────────────",
        f"ASSISTANT_NAME={config.ASSISTANT_NAME}",
        f"ASSISTANT_TONE={config.ASSISTANT_TONE}",
        f"ASSISTANT_PERSONA={config.ASSISTANT_PERSONA}",
        f"ASSISTANT_EXTRA={config.ASSISTANT_EXTRA}",
        "",
        "# ── LLM ─────────────────────────────────",
        f"LLM_PROVIDER={config.LLM_PROVIDER}",
        f"OPENAI_API_KEY={keep(config.OPENAI_API_KEY, 'OPENAI_API_KEY')}",
        f"OPENAI_MODEL={config.OPENAI_MODEL}",
        f"ANTHROPIC_API_KEY={keep(config.ANTHROPIC_API_KEY, 'ANTHROPIC_API_KEY')}",
        f"ANTHROPIC_MODEL={config.ANTHROPIC_MODEL}",
        f"GEMINI_API_KEY={keep(config.GEMINI_API_KEY, 'GEMINI_API_KEY')}",
        f"GEMINI_MODEL={config.GEMINI_MODEL}",
        "",
        "# ── Telegram ─────────────────────────────",
        f"TELEGRAM_BOT_TOKEN={keep(config.TELEGRAM_BOT_TOKEN, 'TELEGRAM_BOT_TOKEN')}",
        "",
        "# ── 허용 사용자 (전 채널 공통: Telegram · Discord · Slack) ──",
        f"ALLOWED_USER_IDS={config.ALLOWED_USER_IDS}",
        "",
        "# ── Database ─────────────────────────────",
        f"DATABASE_URL={config.DATABASE_URL}",
        "",
        "# ── Scheduler ────────────────────────────",
        f"MORNING_BRIEFING_HOUR={config.MORNING_BRIEFING_HOUR}",
        f"REMINDER_MINUTES_BEFORE={config.REMINDER_MINUTES_BEFORE}",
        "",
        "# ── Skills ───────────────────────────────",
        f"ENABLED_SKILLS={config.ENABLED_SKILLS}",
        "",
        "# ── Channels ─────────────────────────────",
        f"ENABLED_CHANNELS={config.ENABLED_CHANNELS}",
    ]

    slack_bot = keep(config.SLACK_BOT_TOKEN, "SLACK_BOT_TOKEN")
    slack_app = keep(config.SLACK_APP_TOKEN, "SLACK_APP_TOKEN")
    if slack_bot:
        lines += [
            "",
            "# ── Slack ────────────────────────────────",
            f"SLACK_BOT_TOKEN={slack_bot}",
            f"SLACK_APP_TOKEN={slack_app}",
        ]

    discord_token = keep(config.DISCORD_BOT_TOKEN, "DISCORD_BOT_TOKEN")
    if discord_token:
        lines += [
            "",
            "# ── Discord ──────────────────────────────",
            f"DISCORD_BOT_TOKEN={discord_token}",
        ]

    if config.ENABLED_CHANNELS and "imessage" in config.ENABLED_CHANNELS:
        lines += [
            "",
            "# ── iMessage (macOS) ─────────────────────",
            f"IMESSAGE_ALLOWED_HANDLES={config.IMESSAGE_ALLOWED_HANDLES}",
            f"IMESSAGE_POLL_INTERVAL={config.IMESSAGE_POLL_INTERVAL}",
        ]

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"ok": True, "path": str(ENV_FILE)}


@app.post("/api/setup/credentials")
async def upload_credentials(file: UploadFile = File(...)):
    """credentials.json 업로드"""
    if file.filename and not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON 파일만 업로드 가능합니다.")
    try:
        OPENCHIKEN_HOME.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        CREDENTIALS_DST.write_bytes(content)
        return {"ok": True, "path": str(CREDENTIALS_DST)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/open-privacy-prefs")
def open_privacy_prefs():
    """macOS 전체 디스크 접근 시스템 설정 패널을 엽니다."""
    import subprocess, sys
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="macOS 전용 기능입니다.")
    try:
        subprocess.Popen([
            "open",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
        ])
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/skills/reload")
def reload_skills():
    """런타임 스킬 캐시를 무효화합니다. 다음 채팅 요청 시 SKILL.md를 재스캔합니다."""
    try:
        import core.agent as ag
        import skills as sk
        ag._tools_cache = None
        ag._skill_instructions_cache = None
        ag._agent = None
        ag._plan_graph = None
        sk._loader = None
        return {"ok": True, "message": "스킬 캐시가 초기화되었습니다. 다음 요청부터 새 스킬이 반영됩니다."}
    except ImportError:
        return {"ok": True, "message": "main.py 미실행 상태 — 재시작 시 자동 반영됩니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/start")
def start_main():
    """setup 완료 후 main.py를 백그라운드 서브프로세스로 실행합니다."""
    global _main_proc

    # 이미 실행 중이면 재시작하지 않음
    if _main_proc is not None and _main_proc.poll() is None:
        return {"ok": True, "status": "already_running", "pid": _main_proc.pid}

    try:
        uv = "uv"
        _main_proc = subprocess.Popen(
            [uv, "run", "python", "main.py"],
            cwd=str(ROOT),
            stdout=open(ROOT / "openchiken.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        return {"ok": True, "status": "started", "pid": _main_proc.pid}
    except FileNotFoundError:
        # uv 없으면 python 직접 실행 시도
        _main_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(ROOT),
            stdout=open(ROOT / "openchiken.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        return {"ok": True, "status": "started", "pid": _main_proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/system/status")
def system_status():
    """main.py 실행 상태를 반환합니다."""
    global _main_proc
    if _main_proc is None:
        return {"running": False, "pid": None}
    if _main_proc.poll() is None:
        return {"running": True, "pid": _main_proc.pid}
    return {"running": False, "pid": None, "exit_code": _main_proc.returncode}


@app.get("/api/setup/credentials/status")
def credentials_status():
    """credentials.json 존재 여부"""
    home_exists = CREDENTIALS_DST.exists()
    local_exists = (ROOT / "credentials.json").exists()
    return {
        "exists": home_exists or local_exists,
        "path": str(CREDENTIALS_DST) if home_exists else (str(ROOT / "credentials.json") if local_exists else None),
    }


# ── Dashboard API ─────────────────────────────────────────────

_WEATHER_ICONS: dict[int, str] = {
    0: "clear_day", 1: "partly_cloudy_day", 2: "partly_cloudy_day", 3: "cloud",
    45: "foggy", 48: "foggy",
    51: "rainy", 53: "rainy", 55: "rainy",
    61: "rainy", 63: "rainy", 65: "rainy",
    71: "weather_snowy", 73: "weather_snowy", 75: "weather_snowy", 77: "weather_snowy",
    80: "rainy", 81: "rainy", 82: "rainy",
    85: "weather_snowy", 86: "weather_snowy",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


@app.get("/api/dashboard/agent-status")
def dashboard_agent_status():
    """에이전트/모델 상태 정보"""
    from config.settings import settings

    provider = settings.llm_provider
    model_map = {
        "openai": lambda: settings.openai_model,
        "anthropic": lambda: settings.anthropic_model,
        "gemini": lambda: settings.gemini_model,
    }
    try:
        model = model_map.get(provider, lambda: "unknown")()
    except EnvironmentError:
        model = os.getenv(f"{provider.upper()}_MODEL", "unknown")

    return {
        "provider": provider,
        "model": model,
        "assistant_name": settings.assistant_name,
        "status": "active",
        "enabled_skills": settings.enabled_skills,
        "enabled_channels": settings.enabled_channels,
    }


@app.get("/api/dashboard/weather")
def dashboard_weather(city: str = "Seoul"):
    """실시간 날씨 데이터 (Open-Meteo, 무료)"""
    from skills.weather.tool import _geocode, _WMO_CODES

    try:
        lat, lon, resolved = _geocode(city)

        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,apparent_temperature,weathercode,windspeed_10m,relativehumidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "Asia/Seoul",
            "forecast_days": 1,
        })
        url = f"https://api.open-meteo.com/v1/forecast?{params}"

        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())

        cur = data["current"]
        daily = data.get("daily", {})
        code = cur.get("weathercode", 0)

        return {
            "city": resolved,
            "condition": _WMO_CODES.get(code, f"코드 {code}"),
            "icon": _WEATHER_ICONS.get(code, "cloud_queue"),
            "temp": cur["temperature_2m"],
            "feels_like": cur["apparent_temperature"],
            "temp_max": daily.get("temperature_2m_max", [None])[0],
            "temp_min": daily.get("temperature_2m_min", [None])[0],
            "humidity": cur["relativehumidity_2m"],
            "windspeed": cur["windspeed_10m"],
        }
    except Exception as e:
        logger.warning("Weather API failed: %s", e)
        return JSONResponse(
            status_code=502,
            content={"error": f"날씨 조회 실패: {e}"},
        )


@app.get("/api/dashboard/calendar")
def dashboard_calendar():
    """오늘 Google Calendar 일정"""
    try:
        from skills.calendar.tool import _get_calendar_service

        service = _get_calendar_service()
        now = datetime.now(KST)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start,
                timeMax=end,
                singleEvents=True,
                orderBy="startTime",
                timeZone="Asia/Seoul",
            )
            .execute()
        )

        events = []
        for e in result.get("items", []):
            start_dt = e["start"].get("dateTime", e["start"].get("date", ""))
            time_str = start_dt.split("T")[1][:5] if "T" in start_dt else "종일"
            events.append({
                "time": time_str,
                "title": e.get("summary", "(제목 없음)"),
                "description": e.get("location") or (e.get("description", "") or "")[:50],
            })

        return {"events": events}
    except Exception as e:
        logger.warning("Calendar API unavailable: %s", e)
        return {"events": [], "error": str(e)}


@app.get("/api/dashboard/gmail")
def dashboard_gmail(max_results: int = 5):
    """읽지 않은 Gmail 메시지"""
    try:
        from skills.gmail.tool import _get_gmail_service

        service = _get_gmail_service()
        results = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=min(max_results, 10))
            .execute()
        )

        messages_refs = results.get("messages", [])
        unread_count = results.get("resultSizeEstimate", len(messages_refs))

        messages = []
        for msg_ref in messages_refs:
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

            from_raw = headers.get("From", "Unknown")
            from_name = from_raw.split("<")[0].strip().strip('"') if "<" in from_raw else from_raw

            messages.append({
                "from": from_name,
                "subject": headers.get("Subject", "(제목 없음)"),
                "date": headers.get("Date", ""),
            })

        return {"messages": messages, "unread_count": unread_count}
    except Exception as e:
        logger.warning("Gmail API unavailable: %s", e)
        return {"messages": [], "unread_count": 0, "error": str(e)}


@app.get("/api/dashboard/memory")
def dashboard_memory(limit: int = 6):
    """최근 대화 기록 + 메모"""
    try:
        from config.settings import settings

        db_url = settings.database_url
        db_path = db_url.replace("sqlite:///", "")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, session_id, message FROM message_store ORDER BY id DESC LIMIT ?",
            (limit * 3,),
        )
        rows = cursor.fetchall()

        cursor.execute(
            "SELECT id, title, content, created_at FROM memo_store ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        memo_rows = cursor.fetchall()
        conn.close()

        messages = []
        for row in rows:
            msg_id, session_id, msg_json = row
            try:
                msg_data = json.loads(msg_json)
                content = msg_data.get("data", {}).get("content", "")
                msg_type = msg_data.get("type", "")
                if content.strip():
                    messages.append({
                        "id": msg_id,
                        "content": content[:200],
                        "type": msg_type,
                        "source": "conversation",
                    })
                if len(messages) >= limit:
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        memos = [
            {
                "id": r[0],
                "title": r[1],
                "content": (r[2] or "")[:200],
                "created_at": r[3],
                "source": "memo",
            }
            for r in memo_rows
        ]

        return {"messages": messages, "memos": memos}
    except Exception as e:
        logger.warning("Memory query failed: %s", e)
        return {"messages": [], "memos": [], "error": str(e)}


# ── Tasks API ─────────────────────────────────────────────────

def _db_path() -> str:
    from config.settings import settings
    return settings.database_url.replace("sqlite:///", "")


class TaskCreate(BaseModel):
    title: str
    description: str = ""


class TaskUpdate(BaseModel):
    result: str = ""


@app.get("/api/tasks")
def api_tasks_list(status: str = "all"):
    """태스크 목록 조회"""
    try:
        with sqlite3.connect(_db_path()) as conn:
            if status == "all":
                rows = conn.execute(
                    "SELECT id, title, description, status, result, created_at, updated_at "
                    "FROM task_store ORDER BY updated_at DESC LIMIT 50"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, title, description, status, result, created_at, updated_at "
                    "FROM task_store WHERE status = ? ORDER BY updated_at DESC LIMIT 50",
                    (status,),
                ).fetchall()

        tasks = [
            {
                "id": r[0], "title": r[1], "description": r[2],
                "status": r[3], "result": r[4],
                "created_at": r[5], "updated_at": r[6],
            }
            for r in rows
        ]
        counts = {}
        with sqlite3.connect(_db_path()) as conn:
            for row in conn.execute("SELECT status, COUNT(*) FROM task_store GROUP BY status"):
                counts[row[0]] = row[1]

        return {"tasks": tasks, "counts": counts}
    except Exception as e:
        logger.warning("Tasks list failed: %s", e)
        return {"tasks": [], "counts": {}, "error": str(e)}


@app.post("/api/tasks")
def api_tasks_create(task: TaskCreate):
    """태스크 생성"""
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            cur = conn.execute(
                "INSERT INTO task_store (title, description, status, created_at, updated_at) "
                "VALUES (?, ?, 'pending', ?, ?)",
                (task.title, task.description, now, now),
            )
            task_id = cur.lastrowid
        return {"ok": True, "id": task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/tasks/{task_id}/complete")
def api_tasks_complete(task_id: int, body: TaskUpdate):
    """태스크 완료 처리"""
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "UPDATE task_store SET status='completed', result=?, updated_at=? WHERE id=?",
                (body.result, now, task_id),
            ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/tasks/{task_id}/fail")
def api_tasks_fail(task_id: int, body: TaskUpdate):
    """태스크 실패 처리"""
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "UPDATE task_store SET status='failed', result=?, updated_at=? WHERE id=?",
                (body.result, now, task_id),
            ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/tasks/{task_id}/running")
def api_tasks_running(task_id: int):
    """태스크 실행 중 처리"""
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "UPDATE task_store SET status='running', updated_at=? WHERE id=?",
                (now, task_id),
            ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/tasks/{task_id}")
def api_tasks_delete(task_id: int):
    """태스크 삭제"""
    try:
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "DELETE FROM task_store WHERE id=?", (task_id,),
            ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Logs / Memo API ──────────────────────────────────────────

@app.get("/api/logs")
def api_logs(limit: int = 50, offset: int = 0, session_id: str = ""):
    """대화 기록 조회 (페이지네이션)"""
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()

        if session_id:
            cursor.execute(
                "SELECT id, session_id, message FROM message_store "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (session_id, limit, offset),
            )
        else:
            cursor.execute(
                "SELECT id, session_id, message FROM message_store "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) FROM message_store")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT session_id FROM message_store ORDER BY session_id")
        sessions = [r[0] for r in cursor.fetchall()]
        conn.close()

        messages = []
        for row in rows:
            msg_id, sess_id, msg_json = row
            try:
                msg_data = json.loads(msg_json)
                content = msg_data.get("data", {}).get("content", "")
                msg_type = msg_data.get("type", "")
                messages.append({
                    "id": msg_id,
                    "session_id": sess_id,
                    "type": msg_type,
                    "content": content[:500],
                })
            except (json.JSONDecodeError, KeyError):
                continue

        return {"messages": messages, "total": total, "sessions": sessions}
    except Exception as e:
        logger.warning("Logs query failed: %s", e)
        return {"messages": [], "total": 0, "sessions": [], "error": str(e)}


@app.get("/api/memos")
def api_memos_list():
    """메모 전체 목록"""
    try:
        with sqlite3.connect(_db_path()) as conn:
            rows = conn.execute(
                "SELECT id, title, content, created_at, updated_at "
                "FROM memo_store ORDER BY updated_at DESC"
            ).fetchall()
        memos = [
            {"id": r[0], "title": r[1], "content": r[2], "created_at": r[3], "updated_at": r[4]}
            for r in rows
        ]
        return {"memos": memos}
    except Exception as e:
        logger.warning("Memos list failed: %s", e)
        return {"memos": [], "error": str(e)}


class MemoCreate(BaseModel):
    title: str
    content: str


@app.post("/api/memos")
def api_memos_save(memo: MemoCreate):
    """메모 저장/업데이트"""
    try:
        now = datetime.now(KST).isoformat()
        with sqlite3.connect(_db_path()) as conn:
            exists = conn.execute(
                "SELECT id FROM memo_store WHERE title = ?", (memo.title,)
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE memo_store SET content=?, updated_at=? WHERE title=?",
                    (memo.content, now, memo.title),
                )
                return {"ok": True, "action": "updated"}
            else:
                conn.execute(
                    "INSERT INTO memo_store (title, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (memo.title, memo.content, now, now),
                )
                return {"ok": True, "action": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/memos/{memo_id}")
def api_memos_delete(memo_id: int):
    """메모 삭제"""
    try:
        with sqlite3.connect(_db_path()) as conn:
            affected = conn.execute(
                "DELETE FROM memo_store WHERE id=?", (memo_id,),
            ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail="Memo not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Settings / Skills API ─────────────────────────────────────

def _mask_key(val: str, visible: int = 6) -> str:
    """API 키를 마스킹: 앞 visible 자만 표시."""
    if not val or len(val) <= visible:
        return val
    return val[:visible] + "•" * min(20, len(val) - visible)


@app.get("/api/settings")
def api_settings_read():
    """현재 설정값 읽기 (API 키 마스킹) — config.settings 기반"""
    from config.settings import settings

    provider = settings.llm_provider
    model_map = {
        "openai": lambda: settings.openai_model,
        "anthropic": lambda: settings.anthropic_model,
        "gemini": lambda: settings.gemini_model,
    }
    try:
        model = model_map.get(provider, lambda: "unknown")()
    except EnvironmentError:
        model = os.getenv(f"{provider.upper()}_MODEL", "unknown")

    return {
        "assistant_name": settings.assistant_name,
        "assistant_tone": settings.assistant_tone,
        "assistant_persona": settings.assistant_persona,
        "llm_provider": provider,
        "model": model,
        "openai_key_masked": _mask_key(os.getenv("OPENAI_API_KEY", "")),
        "anthropic_key_masked": _mask_key(os.getenv("ANTHROPIC_API_KEY", "")),
        "gemini_key_masked": _mask_key(os.getenv("GEMINI_API_KEY", "")),
        "telegram_token_masked": _mask_key(os.getenv("TELEGRAM_BOT_TOKEN", "")),
        "allowed_user_ids": os.getenv("ALLOWED_USER_IDS", ""),
        "database_url": settings.database_url,
        "morning_briefing_hour": settings.morning_briefing_hour,
        "reminder_minutes_before": settings.reminder_minutes_before,
        "enabled_skills": settings.enabled_skills,
        "enabled_channels": settings.enabled_channels,
        "slack_configured": settings.slack_enabled,
        "discord_configured": settings.discord_enabled,
        "google_credentials": CREDENTIALS_DST.exists() or (ROOT / "credentials.json").exists(),
        "google_token": (OPENCHIKEN_HOME / "token.json").exists(),
    }


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file into a dict (strips comments/blank lines)."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


_SENSITIVE_KEYS = {
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN",
    "DISCORD_BOT_TOKEN",
}


@app.get("/api/settings/env")
def api_settings_env():
    """~/.openchiken/.env 파일을 직접 파싱하여 반환 (민감 키 마스킹)"""
    env = _parse_env_file(ENV_FILE)
    if not env:
        env = _parse_env_file(ROOT / ".env")

    masked = {}
    for k in _SENSITIVE_KEYS:
        masked[k] = _mask_key(env.get(k, ""))

    safe = {k: v for k, v in env.items() if k not in _SENSITIVE_KEYS}

    return {
        **safe,
        "_masked": masked,
        "_env_path": str(ENV_FILE) if ENV_FILE.exists() else str(ROOT / ".env"),
        "_status": {
            "google_credentials": CREDENTIALS_DST.exists() or (ROOT / "credentials.json").exists(),
            "google_token": (OPENCHIKEN_HOME / "token.json").exists(),
        },
    }


@app.get("/api/skills")
def api_skills_list():
    """설치된 스킬 목록 (SKILL.md 메타데이터 파싱)"""
    from config.settings import settings

    skills_dir = ROOT / "skills"
    enabled_raw = settings.enabled_skills
    has_google = CREDENTIALS_DST.exists() or (ROOT / "credentials.json").exists()
    has_google_token = (OPENCHIKEN_HOME / "token.json").exists()

    skills = []
    icon_map = {
        "gmail": "mail",
        "calendar": "calendar_month",
        "drive": "folder",
        "sheets": "table_chart",
        "docs": "description",
        "workflow": "account_tree",
        "weather": "partly_cloudy_day",
        "web_search": "search",
        "memo": "database",
        "task": "checklist",
        "finance": "trending_up",
    }
    desc_map = {
        "gmail": "이메일 목록, 검색, 읽기, 전송, 답장",
        "calendar": "일정 조회, 생성, 삭제",
        "drive": "파일 목록, 검색, 읽기, 업로드, 폴더 관리",
        "sheets": "스프레드시트 읽기, 쓰기, 생성, 행 추가",
        "docs": "Google Docs 읽기, 생성, 내용 추가",
        "workflow": "스탠드업·주간·모닝 브리핑, 미팅 준비 등 복합 자동화",
        "weather": "전 세계 날씨 조회 (무료, 키 불필요)",
        "web_search": "DuckDuckGo 실시간 검색 (무료)",
        "memo": "영구 메모 저장/조회/삭제",
        "task": "태스크 생성 및 진행 추적",
        "finance": "주식/암호화폐 시세 조회 및 분석",
    }

    if not skills_dir.exists():
        return {"skills": []}

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("_"):
            continue
        if not (entry / "SKILL.md").exists() and not (entry / "tool.py").exists():
            continue
        skill_id = entry.name
        md_path = entry / "SKILL.md"

        name = skill_id
        description = desc_map.get(skill_id, "")
        requires_google = False

        if md_path.exists():
            content = md_path.read_text(encoding="utf-8")
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
                elif "requires_google_auth: true" in line:
                    requires_google = True

        is_enabled = enabled_raw == "all" or skill_id in enabled_raw.split(",")

        if requires_google:
            status = "connected" if (has_google and has_google_token) else "auth_required"
        else:
            status = "connected" if is_enabled else "disabled"

        skills.append({
            "id": skill_id,
            "name": name,
            "description": description,
            "icon": icon_map.get(skill_id, "extension"),
            "enabled": is_enabled,
            "status": status,
            "requires_google": requires_google,
        })

    return {"skills": skills}


# ── 정적 파일 서빙 ────────────────────────────────────────────
# setup.html 은 /setup 으로도 접근 가능
@app.get("/setup")
@app.get("/setup.html")
def setup_page():
    return FileResponse(LOCAL_UI_DIR / "setup.html")


# 정적 자산 → local_ui HTML (마운트 순서: 구체적인 경로를 먼저)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if LOCAL_UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(LOCAL_UI_DIR), html=True), name="local_ui")


# ── 진입점 ──────────────────────────────────────────────────
def run_server() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    print(f"\n  OpenChiken Web Server — http://localhost:{port}\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    run_server()
