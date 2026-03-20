from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# ~/.openchiken 이 존재하면 그곳의 .env도 로드 (uv tool install 배포 시 사용)
_OPENCHIKEN_HOME = Path.home() / ".openchiken"
if (_OPENCHIKEN_HOME / ".env").exists():
    load_dotenv(_OPENCHIKEN_HOME / ".env")
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Lazy-loaded settings that read env vars on first attribute access."""

    @property
    def openai_api_key(self) -> str:
        return self._require("OPENAI_API_KEY")

    @property
    def openai_model(self) -> str:
        return os.getenv("OPENAI_MODEL", "gpt-4o")

    @property
    def telegram_bot_token(self) -> str:
        return self._require("TELEGRAM_BOT_TOKEN")

    @property
    def allowed_user_ids(self) -> list[int]:
        raw = os.getenv("ALLOWED_USER_IDS", "")
        return [int(uid.strip()) for uid in raw.split(",") if uid.strip()]

    @property
    def database_url(self) -> str:
        return os.getenv("DATABASE_URL", "sqlite:///openchiken.db")

    @property
    def openchiken_home(self) -> Path:
        """~/.openchiken 디렉토리. uv tool install 환경에서 설정 파일을 저장합니다."""
        path = _OPENCHIKEN_HOME
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return path

    @property
    def user_skills_path(self) -> Path:
        """사용자가 설치한 외부 스킬 디렉토리 (~/.openchiken/skills/)."""
        path = self.openchiken_home / "skills"
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return path

    @property
    def google_credentials_path(self) -> Path:
        """credentials.json 경로. ~/.openchiken 우선, 없으면 프로젝트 루트."""
        home_path = self.openchiken_home / "credentials.json"
        if home_path.exists():
            return home_path
        return BASE_DIR / "credentials.json"

    @property
    def google_token_path(self) -> Path:
        """token.json 경로. ~/.openchiken 우선, 없으면 프로젝트 루트."""
        home_path = self.openchiken_home / "token.json"
        if home_path.exists():
            return home_path
        # 저장 위치는 ~/.openchiken/token.json 으로 통일
        return self.openchiken_home / "token.json"

    @property
    def assistant_name(self) -> str:
        """AI 비서 이름. 기본값 '치킨'."""
        return os.getenv("ASSISTANT_NAME", "치킨")

    @property
    def assistant_tone(self) -> str:
        """AI 비서 말투 지침."""
        return os.getenv(
            "ASSISTANT_TONE",
            "캐주얼하고 친근한 존댓말로 대화합니다. '~요', '~해요' 형태로 답변하세요.",
        )

    @property
    def assistant_persona(self) -> str:
        """AI 비서 페르소나 설명."""
        return os.getenv(
            "ASSISTANT_PERSONA",
            "친근하고 유머러스한 성격입니다. 가끔 가벼운 농담을 섞고 사용자와 편하게 대화합니다.",
        )

    @property
    def assistant_extra(self) -> str:
        """AI 비서 추가 지침 (선택)."""
        return os.getenv("ASSISTANT_EXTRA", "")

    @property
    def morning_briefing_hour(self) -> int:
        """아침 브리핑 시각 (KST, 0–23). 기본값 8시."""
        return int(os.getenv("MORNING_BRIEFING_HOUR", "8"))

    @property
    def reminder_minutes_before(self) -> int:
        """일정 리마인더를 몇 분 전에 보낼지. 기본값 15분."""
        return int(os.getenv("REMINDER_MINUTES_BEFORE", "15"))

    @property
    def enabled_skills(self) -> str:
        """활성화된 스킬 목록. 'all' 또는 콤마 구분 스킬 이름 목록."""
        return os.getenv("ENABLED_SKILLS", "all")

    @property
    def slack_bot_token(self) -> str | None:
        """Slack Bot Token (xoxb-...). 미설정이면 None."""
        return os.getenv("SLACK_BOT_TOKEN") or None

    @property
    def slack_app_token(self) -> str | None:
        """Slack App-Level Token (xapp-...). Socket Mode에 필요. 미설정이면 None."""
        return os.getenv("SLACK_APP_TOKEN") or None

    @property
    def slack_enabled(self) -> bool:
        """Slack 봇을 활성화할지 여부."""
        return bool(self.slack_bot_token and self.slack_app_token)

    # ── LLM 공급자 ──────────────────────────────────────────────────────────

    @property
    def llm_provider(self) -> str:
        """LLM 공급자. 'openai' | 'anthropic' | 'gemini'. 기본값 'openai'."""
        return os.getenv("LLM_PROVIDER", "openai").strip().lower()

    @property
    def anthropic_api_key(self) -> str:
        return self._require("ANTHROPIC_API_KEY")

    @property
    def anthropic_model(self) -> str:
        return os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

    @property
    def gemini_api_key(self) -> str:
        return self._require("GEMINI_API_KEY")

    @property
    def gemini_model(self) -> str:
        return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # ── Discord ──────────────────────────────────────────────────────────────

    @property
    def discord_bot_token(self) -> str:
        return self._require("DISCORD_BOT_TOKEN")

    @property
    def discord_enabled(self) -> bool:
        return bool(os.getenv("DISCORD_BOT_TOKEN"))

    # ── iMessage (macOS 전용) ─────────────────────────────────────────────────

    @property
    def imessage_allowed_handles(self) -> list[str]:
        """허용할 iMessage 핸들 목록 (전화번호 또는 Apple ID). 미설정 시 전체 허용."""
        raw = os.getenv("IMESSAGE_ALLOWED_HANDLES", "")
        return [h.strip() for h in raw.split(",") if h.strip()]

    @property
    def imessage_poll_interval(self) -> int:
        """chat.db 폴링 간격(초). 기본값 3초."""
        return int(os.getenv("IMESSAGE_POLL_INTERVAL", "3"))

    @property
    def imessage_db_path(self) -> Path:
        """Messages chat.db 경로. 기본값 ~/Library/Messages/chat.db."""
        raw = os.getenv("IMESSAGE_DB_PATH", "")
        if raw:
            return Path(raw).expanduser()
        return Path.home() / "Library" / "Messages" / "chat.db"

    @property
    def imessage_enabled(self) -> bool:
        """iMessage 채널 활성화 여부 (macOS 에서만 동작)."""
        import sys
        return sys.platform == "darwin" and self.imessage_db_path.exists()

    # ── 채널 설정 ────────────────────────────────────────────────────────────

    @property
    def enabled_channels(self) -> list[str]:
        """활성화할 채널 목록. 기본값 'telegram'."""
        raw = os.getenv("ENABLED_CHANNELS", "telegram")
        return [ch.strip() for ch in raw.split(",") if ch.strip()]

    @staticmethod
    def _require(name: str) -> str:
        val = os.getenv(name)
        if not val:
            raise EnvironmentError(
                f"환경변수 '{name}'이(가) 설정되지 않았습니다. .env 파일을 확인하세요."
            )
        return val


settings = Settings()
