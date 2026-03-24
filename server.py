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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

# ── 릴레이 송신 활동 인메모리 로그 (최대 200건) ──────────────────────────────
_relay_activity_log: list[dict] = []

# ── 경로 설정 ──────────────────────────────────────────────────
ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
LOCAL_UI_DIR = ROOT / "local_ui"
OPENCHIKEN_HOME = Path.home() / ".openchiken"
ENV_FILE = OPENCHIKEN_HOME / ".env"
CREDENTIALS_DST = OPENCHIKEN_HOME / "credentials.json"

# main.py 서브프로세스 핸들 (단일 인스턴스 관리)
_main_proc: subprocess.Popen | None = None


def _init_db() -> None:
    """서버 시작 시 DB 테이블이 없으면 생성 (main.py 없이 web만 실행할 때도 동작)."""
    try:
        from config.settings import settings

        db_path = settings.database_url.replace("sqlite:///", "")
        if not db_path.startswith("/"):
            db_path = str(ROOT / db_path)

        with sqlite3.connect(db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS message_store (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message    TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memo_store (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT UNIQUE NOT NULL,
                    content    TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS task_store (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status      TEXT DEFAULT 'pending',
                    result      TEXT DEFAULT '',
                    created_at  TEXT,
                    updated_at  TEXT
                );
            """)
        logger.info("DB 테이블 초기화 완료: %s", db_path)
    except Exception as e:
        logger.warning("DB 초기화 실패 (온보딩 전 정상): %s", e)


def _try_start_main() -> None:
    """main.py를 백그라운드 서브프로세스로 실행. 이미 실행 중이면 스킵."""
    global _main_proc
    if _main_proc is not None and _main_proc.poll() is None:
        return
    try:
        _main_proc = subprocess.Popen(
            ["uv", "run", "python", "main.py"],
            cwd=str(ROOT),
            stdout=open(ROOT / "openchiken.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        logger.info("main.py 자동 시작 완료 (pid=%d)", _main_proc.pid)
    except FileNotFoundError:
        _main_proc = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=str(ROOT),
            stdout=open(ROOT / "openchiken.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
        )
        logger.info("main.py 자동 시작 완료 (pid=%d)", _main_proc.pid)
    except Exception as e:
        logger.warning("main.py 자동 시작 실패: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작 시 DB 초기화 후, 온보딩 완료 상태면 main.py 자동 구동."""
    _init_db()
    if ENV_FILE.exists():
        logger.info("온보딩 완료 상태 확인 — main.py 자동 시작")
        _try_start_main()
    else:
        logger.info("온보딩 미완료 — main.py 자동 시작 건너뜀")
    yield


app = FastAPI(title="OpenChiken Web Server", docs_url=None, redoc_url=None, lifespan=lifespan)  # v2.0

# Chrome Extension (chrome-extension://*) 및 localhost UI 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


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
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
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

# ── Browser Channel (Chrome Extension) ────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "extension"


class ChatResponse(BaseModel):
    ok: bool
    reply: str = ""
    error: str = ""


class RelayActivityEntry(BaseModel):
    direction: str   # "sent" | "received"
    agentId: str
    skill: str
    status: str      # "approved" | "rejected" | "error"
    summary: str = ""


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    """Chrome Extension 등 브라우저 채널에서 에이전트에게 메시지를 전송합니다."""
    try:
        from core.agent import chat as agent_chat

        reply = await agent_chat(req.session_id, req.message)
        return ChatResponse(ok=True, reply=reply)
    except EnvironmentError as e:
        raise HTTPException(
            status_code=503,
            detail=f"LLM 공급자 설정이 필요합니다: {e}",
        )
    except Exception as e:
        logger.error("api_chat failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/history")
def api_chat_history(session_id: str = "extension", limit: int = 20):
    """브라우저 채널 대화 기록 조회."""
    try:
        conn = sqlite3.connect(_db_path())
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, message FROM message_store "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()

        messages = []
        for row_id, msg_json in reversed(rows):
            try:
                data = json.loads(msg_json)
                content = data.get("data", {}).get("content", "")
                msg_type = data.get("type", "")
                if content.strip():
                    messages.append({"id": row_id, "type": msg_type, "content": content})
            except (json.JSONDecodeError, KeyError):
                continue
        return {"ok": True, "messages": messages}
    except Exception as e:
        logger.warning("api_chat_history failed: %s", e)
        return {"ok": False, "messages": [], "error": str(e)}


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
        f"OLLAMA_BASE_URL={config.OLLAMA_BASE_URL}",
        f"OLLAMA_MODEL={config.OLLAMA_MODEL}",
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


class ModelFetchRequest(BaseModel):
    key: str


def _fetch_openai_models(api_key: str) -> list[dict]:
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"OpenAI API 오류: {body[:300]}")

    INCLUDE_PREFIXES = ("gpt-4", "gpt-3.5", "o1", "o3", "o4", "chatgpt")
    EXCLUDE_TOKENS = ("instruct", "embedding", "whisper", "tts", "dall-e",
                      "babbage", "davinci", "curie", "ada", "moderation",
                      "realtime", "audio", "search", "ft:")
    models = [
        m for m in data.get("data", [])
        if any(m["id"].startswith(p) for p in INCLUDE_PREFIXES)
        and not any(x in m["id"] for x in EXCLUDE_TOKENS)
    ]
    models.sort(key=lambda m: m.get("created", 0), reverse=True)
    return [{"id": m["id"], "name": m["id"]} for m in models[:10]]


def _fetch_anthropic_models(api_key: str) -> list[dict]:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"Anthropic API 오류: {body[:300]}")

    models = data.get("data", [])
    models.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return [{"id": m["id"], "name": m.get("display_name", m["id"])} for m in models[:10]]


def _fetch_gemini_models(api_key: str) -> list[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={urllib.parse.quote(api_key)}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise HTTPException(status_code=e.code, detail=f"Gemini API 오류: {body[:300]}")

    models = [
        m for m in data.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
        and "gemini" in m.get("name", "")
        and "embedding" not in m.get("name", "")
        and "aqa" not in m.get("name", "")
    ]
    models.sort(key=lambda m: m.get("name", ""), reverse=True)
    return [
        {"id": m["name"].replace("models/", ""), "name": m.get("displayName", m["name"].replace("models/", ""))}
        for m in models[:10]
    ]


@app.post("/api/models/{provider}")
def fetch_provider_models(provider: str, body: ModelFetchRequest):
    """각 LLM 공급자의 최신 모델 목록을 프록시로 가져옵니다."""
    if provider not in ("openai", "anthropic", "gemini"):
        raise HTTPException(status_code=400, detail="지원하지 않는 공급자입니다")
    if not body.key or len(body.key) < 5:
        raise HTTPException(status_code=400, detail="API 키가 필요합니다")
    try:
        if provider == "openai":
            return _fetch_openai_models(body.key)
        elif provider == "anthropic":
            return _fetch_anthropic_models(body.key)
        else:
            return _fetch_gemini_models(body.key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


def _prepare_extension() -> Path | None:
    """Extension 파일을 ~/.openchiken/extensions/chrome/ 에 __init__.py 없이 복사.
    Chrome은 _ 접두사 파일을 허용하지 않으므로 site-packages 직접 로드 불가."""
    import shutil

    src = ROOT / "extensions" / "chrome"
    if not (src / "manifest.json").exists():
        return None

    dst = OPENCHIKEN_HOME / "extensions" / "chrome"
    needs_copy = not (dst / "manifest.json").exists()

    if not needs_copy:
        src_mtime = max(f.stat().st_mtime for f in src.rglob("*") if f.is_file() and f.name != "__init__.py")
        dst_mtime = (dst / "manifest.json").stat().st_mtime
        needs_copy = src_mtime > dst_mtime

    if needs_copy:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns("__init__.py", "__pycache__", "*.pyc"),
        )
    return dst


@app.get("/api/extension/info")
def extension_info():
    """Chrome Extension 경로와 설치 가능 여부를 반환합니다."""
    ext_path = _prepare_extension()
    if ext_path and (ext_path / "manifest.json").exists():
        return {"exists": True, "path": str(ext_path)}
    return {"exists": False, "path": str(OPENCHIKEN_HOME / "extensions" / "chrome")}


_CHROME_PATHS = {
    "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "linux": "google-chrome",
    "win32": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}
_RELAY_HEALTH_URL = "https://openchiken-relay-production.up.railway.app/api/agents"


def _find_chrome() -> str | None:
    import shutil as _shutil
    p = _CHROME_PATHS.get(sys.platform)
    if p and Path(p).exists():
        return p
    return _shutil.which("google-chrome") or _shutil.which("chrome") or _shutil.which("chromium")


def _poll_relay(timeout_sec: int = 30) -> str | None:
    """Relay 서버에서 Extension 연결을 폴링. 연결된 agentId 반환."""
    import urllib.request as _ureq
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            req = _ureq.Request(_RELAY_HEALTH_URL, headers={"Accept": "application/json"})
            with _ureq.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                agents = data.get("agents", [])
                if agents:
                    return agents[0].get("agentId")
        except Exception:
            pass
        time.sleep(2)
    return None


@app.post("/api/extension/install")
def extension_install():
    """Chrome Extension 반자동 설치: 파일 준비 → Chrome 종료 → 재시작 → Relay 폴링."""
    ext_path = _prepare_extension()
    if not ext_path or not (ext_path / "manifest.json").exists():
        return {"ok": False, "status": "no_extension", "path": None}

    chrome_bin = _find_chrome()
    if not chrome_bin:
        return {"ok": False, "status": "no_chrome", "path": str(ext_path)}

    # Chrome 종료
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "Google Chrome" to quit'],
                capture_output=True, timeout=5,
            )
        else:
            subprocess.run(["pkill", "-f", "chrome"], capture_output=True, timeout=5)
        time.sleep(2)
    except Exception:
        pass

    # --load-extension 으로 Chrome 재시작
    try:
        if sys.platform == "darwin":
            subprocess.Popen([
                "open", "-a", "Google Chrome", "--args",
                f"--load-extension={ext_path}",
            ])
        else:
            subprocess.Popen([chrome_bin, f"--load-extension={ext_path}"])
    except Exception as e:
        return {"ok": False, "status": "launch_failed", "error": str(e), "path": str(ext_path)}

    time.sleep(3)

    # Relay 폴링
    agent_id = _poll_relay(timeout_sec=30)
    if agent_id:
        return {"ok": True, "status": "connected", "agentId": agent_id, "path": str(ext_path)}
    return {"ok": True, "status": "timeout", "path": str(ext_path)}


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


class EnvKeyRequest(BaseModel):
    env_key: str
    env_value: str


def _update_env_file(env_path: Path, key: str, value: str) -> None:
    """~/.openchiken/.env 파일에서 key를 업데이트하거나 새로 추가합니다."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    updated = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                lines.append(f"{key}={value}")
                updated = True
            else:
                lines.append(line)
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.post("/api/skills/{skill_id}/env")
def save_skill_env(skill_id: str, req: EnvKeyRequest):
    """스킬에 필요한 API 키(환경변수)를 ~/.openchiken/.env에 저장하고 즉시 적용합니다."""
    key = req.env_key.strip()
    value = req.env_value.strip()

    if not key or not key.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="유효하지 않은 환경변수 이름입니다.")
    if not value:
        raise HTTPException(status_code=400, detail="값이 비어있습니다.")

    try:
        _update_env_file(ENV_FILE, key, value)
        os.environ[key] = value

        # 스킬 캐시 리로드 (새 환경변수 반영)
        try:
            import core.agent as ag
            import skills as sk
            ag._tools_cache = None
            ag._skill_instructions_cache = None
            ag._agent = None
            ag._plan_graph = None
            sk._loader = None
        except ImportError:
            pass

        logger.info("Skill env saved: skill=%s, key=%s", skill_id, key)
        return {
            "ok": True,
            "message": f"{key} 가 저장되었습니다. 스킬 '{skill_id}'이(가) 활성화됩니다.",
            "skill_id": skill_id,
            "env_key": key,
        }
    except Exception as e:
        logger.error("save_skill_env failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/start")
def start_main():
    """setup 완료 후 main.py를 백그라운드 서브프로세스로 실행합니다."""
    global _main_proc
    if _main_proc is not None and _main_proc.poll() is None:
        return {"ok": True, "status": "already_running", "pid": _main_proc.pid}
    try:
        _try_start_main()
        return {"ok": True, "status": "started", "pid": _main_proc.pid if _main_proc else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/system/stop")
def stop_main():
    """실행 중인 main.py 서브프로세스를 종료합니다."""
    global _main_proc
    if _main_proc is None or _main_proc.poll() is not None:
        return {"ok": True, "status": "not_running"}
    try:
        _main_proc.terminate()
        try:
            _main_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _main_proc.kill()
        pid = _main_proc.pid
        _main_proc = None
        return {"ok": True, "status": "stopped", "pid": pid}
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
    """에이전트/모델 상태 정보 — .env를 직접 파싱해 서버 재시작 없이 최신값 반영"""
    # load_dotenv()는 서버 시작 시 1회만 실행되므로, 셋업 이후 저장된 .env를
    # os.environ에서 읽으면 이전 값이 반환될 수 있다. 파일 직접 파싱으로 해결.
    env: dict[str, str] = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

    def ev(key: str, default: str = "") -> str:
        """env 파일 → os.environ → 기본값 순으로 조회"""
        return env.get(key) or os.getenv(key, default)

    provider = ev("LLM_PROVIDER", "openai").lower()
    model_key = {
        "openai":    "OPENAI_MODEL",
        "anthropic": "ANTHROPIC_MODEL",
        "gemini":    "GEMINI_MODEL",
    }.get(provider, "OPENAI_MODEL")
    model = ev(model_key, "gpt-4o")

    channels_raw = ev("ENABLED_CHANNELS", "telegram")
    channels = [ch.strip() for ch in channels_raw.split(",") if ch.strip()]

    return {
        "provider": provider,
        "model": model,
        "assistant_name": ev("ASSISTANT_NAME", "치킨"),
        "status": "active",
        "enabled_skills": ev("ENABLED_SKILLS", "all"),
        "enabled_channels": channels,
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


@app.post("/api/relay/activity")
def api_relay_activity_add(entry: RelayActivityEntry):
    """릴레이 송신 활동 로그 기록 (relay_invoke 스킬이 호출)"""
    import uuid as _uuid
    _relay_activity_log.insert(0, {
        "id": str(_uuid.uuid4())[:8],
        "direction": entry.direction,
        "agentId": entry.agentId,
        "skill": entry.skill,
        "status": entry.status,
        "summary": entry.summary[:300],
        "at": datetime.now(KST).isoformat(),
    })
    if len(_relay_activity_log) > 200:
        _relay_activity_log[:] = _relay_activity_log[:200]
    return {"ok": True}


@app.get("/api/relay/activity")
def api_relay_activity_list(limit: int = 50):
    """릴레이 송신 활동 로그 조회"""
    return {"activities": _relay_activity_log[:limit]}


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


# ── Hub & Apps API ────────────────────────────────────────────


class HubInstallRequest(BaseModel):
    name: str


class AppGenerateRequest(BaseModel):
    query: str


@app.get("/api/hub/skills")
def api_hub_skills():
    """GitHub skill-hub 레포에서 스킬 목록 조회"""
    try:
        from core.hub import list_hub_skills
        return {"ok": True, "skills": list_hub_skills()}
    except Exception as e:
        return {"ok": False, "skills": [], "error": str(e)}


@app.get("/api/hub/apps")
def api_hub_apps():
    """GitHub skill-hub 레포에서 앱 목록 조회"""
    try:
        from core.hub import list_hub_apps
        return {"ok": True, "apps": list_hub_apps()}
    except Exception as e:
        return {"ok": False, "apps": [], "error": str(e)}


@app.post("/api/hub/install")
def api_hub_install(req: HubInstallRequest):
    """허브에서 스킬을 다운로드하여 로컬에 설치"""
    try:
        from core.hub import download_skill
        path = download_skill(req.name)
        reload_skills()
        return {"ok": True, "message": f"스킬 '{req.name}' 설치 완료", "path": str(path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/hub/install-app")
def api_hub_install_app(req: HubInstallRequest):
    """허브에서 앱을 다운로드하고 의존 스킬도 자동 설치합니다."""
    try:
        from core.hub import install_app_with_deps
        result = install_app_with_deps(req.name)
        reload_skills()
        return {
            "ok": True,
            "message": f"앱 '{req.name}' 설치 완료",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/apps")
def api_apps_list():
    """설치된 앱(스킬셋) 목록 조회"""
    try:
        from skills import get_skill_loader

        loader = get_skill_loader()
        apps = loader.load_apps()

        # 설치된 앱 이름 집합 (내장 + 사용자)
        bundled_names = set()
        user_names = set()
        bundled_apps_dir = ROOT / "skills" / "apps"
        user_apps_dir = OPENCHIKEN_HOME / "apps"
        if bundled_apps_dir.exists():
            bundled_names = {d.name for d in bundled_apps_dir.iterdir() if d.is_dir() and (d / "APP.md").exists()}
        if user_apps_dir.exists():
            user_names = {d.name for d in user_apps_dir.iterdir() if d.is_dir() and (d / "APP.md").exists()}

        def _source(app_name: str) -> str:
            if app_name in user_names:
                return "hub_installed"
            return "bundled"

        return {
            "ok": True,
            "apps": [
                {
                    "name": a.name,
                    "description": a.description,
                    "sub_skills": a.sub_skills,
                    "steps": a.steps,
                    "trigger_keywords": a.trigger_keywords,
                    "output_channel": a.output_channel,
                    "schedule": a.schedule,
                    "enabled": a.enabled,
                    "version": a.version,
                    "source": _source(a.name),
                }
                for a in apps
            ],
        }
    except Exception as e:
        return {"ok": False, "apps": [], "error": str(e)}


class AppRunRequest(BaseModel):
    context: str = ""   # 추가 컨텍스트 (예: 조회 지역, 파라미터)


@app.post("/api/apps/{app_name}/run")
async def api_app_run(app_name: str, req: AppRunRequest):
    """설치된 앱을 APP.md steps 기반으로 결정론적으로 실행합니다."""
    try:
        from core.orchestrator import run_app
        result = await run_app(app_name, session_id=f"app_run_{app_name}", extra_context=req.context)
        return {"ok": True, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/apps/{app_name}")
def api_app_delete(app_name: str, delete_skills: bool = True):
    """설치된 앱 삭제. delete_skills=True이면 해당 앱 전용 의존 스킬도 함께 삭제."""
    import shutil

    user_apps_dir = OPENCHIKEN_HOME / "apps"
    app_dir = user_apps_dir / app_name

    # 허브 설치 앱만 삭제 가능 (내장 앱은 보호)
    bundled_app = ROOT / "skills" / "apps" / app_name
    if bundled_app.exists() and not app_dir.exists():
        raise HTTPException(status_code=403, detail=f"내장 앱 '{app_name}'은 삭제할 수 없습니다.")
    if not app_dir.exists():
        raise HTTPException(status_code=404, detail=f"앱 '{app_name}'을 찾을 수 없습니다.")

    deleted_skills: list[str] = []

    if delete_skills:
        # 앱 manifest에서 의존 스킬 파악
        app_md = app_dir / "APP.md"
        app_skills: list[str] = []
        if app_md.exists():
            content = app_md.read_text(encoding="utf-8")
            in_skills = False
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped == "skills:":
                    in_skills = True
                    continue
                if in_skills:
                    if stripped.startswith("- "):
                        app_skills.append(stripped[2:].strip())
                    elif stripped and not stripped.startswith("#"):
                        in_skills = False

        # 다른 앱들이 사용하는 스킬 수집
        other_used: set[str] = set()
        if user_apps_dir.exists():
            for other_dir in user_apps_dir.iterdir():
                if not other_dir.is_dir() or other_dir.name == app_name:
                    continue
                other_md = other_dir / "APP.md"
                if not other_md.exists():
                    continue
                in_s = False
                for line in other_md.read_text(encoding="utf-8").split("\n"):
                    s = line.strip()
                    if s == "skills:":
                        in_s = True
                        continue
                    if in_s:
                        if s.startswith("- "):
                            other_used.add(s[2:].strip())
                        elif s and not s.startswith("#"):
                            in_s = False

        # 이 앱에만 사용되는 스킬(내장이 아닌 것) 삭제
        user_skills_dir = OPENCHIKEN_HOME / "skills"
        bundled_skill_dir = ROOT / "skills"
        for skill in app_skills:
            if skill in other_used:
                continue
            # 내장 스킬은 보호
            if (bundled_skill_dir / skill).exists():
                continue
            skill_dir = user_skills_dir / skill
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
                deleted_skills.append(skill)

    shutil.rmtree(app_dir)
    return {"ok": True, "deleted_app": app_name, "deleted_skills": deleted_skills}


@app.delete("/api/skills/{skill_id}")
def api_skill_delete(skill_id: str):
    """허브에서 설치된 스킬 삭제 (내장 스킬은 삭제 불가)."""
    import shutil

    bundled_dir = ROOT / "skills" / skill_id
    user_dir = OPENCHIKEN_HOME / "skills" / skill_id

    if bundled_dir.exists() and not user_dir.exists():
        raise HTTPException(status_code=403, detail=f"내장 스킬 '{skill_id}'은 삭제할 수 없습니다.")
    if not user_dir.exists():
        raise HTTPException(status_code=404, detail=f"스킬 '{skill_id}'을 찾을 수 없습니다.")

    shutil.rmtree(user_dir)
    return {"ok": True, "deleted_skill": skill_id}


@app.post("/api/apps/plan")
async def api_apps_plan(req: AppGenerateRequest):
    """쿼리를 분석하여 필요한 스킬 플랜만 반환 (실행하지 않음)"""
    try:
        from core.orchestrator import get_orchestration_plan
        plan = await get_orchestration_plan(req.query)
        return {"ok": True, **plan}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/apps/generate")
async def api_apps_generate(req: AppGenerateRequest):
    """자율 앱 생성: 쿼리 분석 → 스킬 확보 → 실행"""
    try:
        from core.orchestrator import run_autonomous
        result = await run_autonomous(req.query, session_id="app_gen")
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/skills")
def api_skills_list():
    """설치된 스킬 목록 (내장 + 허브 설치 스킬 통합, SKILL.md 메타데이터 파싱)"""
    from config.settings import settings

    enabled_raw = settings.enabled_skills
    has_google = CREDENTIALS_DST.exists() or (ROOT / "credentials.json").exists()
    has_google_token = (OPENCHIKEN_HOME / "token.json").exists()

    # 도메인 영역 매핑 — SKILL.md에 domain: 필드가 없을 때 기본값으로 사용
    domain_map = {
        "gmail":             "Email Management",
        "calendar":          "Calendar Management",
        "drive":             "File Management",
        "sheets":            "Spreadsheet Management",
        "docs":              "Document Management",
        "finance":           "Financial Analysis",
        "crypto_price":      "Cryptocurrency Analysis",
        "exchange_rate":     "Currency Exchange",
        "news_rss":          "News & Media",
        "web_search":        "Web Research",
        "wikipedia_search":  "Knowledge Research",
        "hacker_news":       "Tech News",
        "weather":           "Weather & Environment",
        "memo":              "Knowledge Management",
        "task":              "Task Management",
        "geocoding":         "Location Services",
        "quality_of_life":   "Location Services",
        "quickchart":        "Data Visualization",
        "workflow":          "Workflow Automation",
        "relay_discover":    "Agent Networking",
        "relay_invoke":      "Agent Networking",
    }

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
        "crypto_price": "currency_bitcoin",
        "exchange_rate": "currency_exchange",
        "news_rss": "newspaper",
        "geocoding": "pin_drop",
        "quality_of_life": "location_city",
        "hacker_news": "terminal",
        "wikipedia_search": "menu_book",
        "quickchart": "bar_chart",
        "sec_edgar": "gavel",
        "world_bank": "public",
        "wallstreetbets": "forum",
        "air_quality": "air",
        "earthquake": "crisis_alert",
        "arxiv": "science",
        "public_holidays": "event",
    }

    import json as _json

    # 내장 스킬 디렉토리 + 사용자 스킬 디렉토리 (허브 설치 / AI 자동생성 혼재)
    skill_roots = [
        (ROOT / "skills", "bundled"),
        (OPENCHIKEN_HOME / "skills", "user"),
    ]

    skills = []
    seen: set[str] = set()

    for skills_dir, base_source in skill_roots:
        if not skills_dir.exists():
            continue

        for entry in sorted(skills_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_") or entry.name == "apps":
                continue
            if not (entry / "SKILL.md").exists() and not (entry / "tool.py").exists():
                continue

            skill_id = entry.name
            if skill_id in seen:
                continue
            seen.add(skill_id)

            md_path = entry / "SKILL.md"
            name = skill_id
            description = ""
            domain = domain_map.get(skill_id, "")
            requires_google = False

            if md_path.exists():
                content = md_path.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("domain:"):
                        domain = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip()
                    elif "requires_google_auth: true" in line:
                        requires_google = True

            # source.json 에서 실제 출처를 읽음
            source_file = entry / "source.json"
            if base_source == "user" and source_file.exists():
                try:
                    source_data = _json.loads(source_file.read_text(encoding="utf-8"))
                    source = source_data.get("source", "hub_installed")
                except Exception:
                    source = "hub_installed"
            else:
                source = base_source  # bundled

            is_enabled = enabled_raw == "all" or skill_id in enabled_raw.split(",")

            # requires_env 파싱
            requires_env: list[str] = []
            if md_path.exists():
                for line in md_path.read_text(encoding="utf-8").split("\n"):
                    line = line.strip()
                    if line.startswith("requires_env:"):
                        raw_env = line.split(":", 1)[1].strip()
                        requires_env = [e.strip() for e in raw_env.split(",") if e.strip()]
                        break

            env_status = {env: bool(os.getenv(env, "").strip()) for env in requires_env}
            has_missing_env = requires_env and not all(env_status.values())

            if requires_google:
                status = "connected" if (has_google and has_google_token) else "auth_required"
            elif has_missing_env:
                status = "env_required"
            elif source == "hub":
                status = "hub_installed"
            elif source == "ai_generated":
                status = "ai_generated"
            else:
                status = "connected" if is_enabled else "disabled"

            skills.append({
                "id":             skill_id,
                "name":           name,
                "description":    description,
                "domain":         domain,
                "icon":           icon_map.get(skill_id, "extension"),
                "enabled":        is_enabled,
                "status":         status,
                "source":         source,
                "requires_google": requires_google,
                "requires_env":   requires_env,
                "env_status":     env_status,
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
