#!/usr/bin/env python3
"""
OpenChiken Setup Wizard
───────────────────────
인터랙티브 TUI로 AI 비서를 처음부터 세팅합니다.
  uv run python setup_wizard.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# ── 의존성 자동 설치 ──────────────────────────────────────────
def _ensure_deps():
    missing = []
    for pkg in ("rich", "questionary"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"설치 중: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"],
            stdout=subprocess.DEVNULL,
        )

_ensure_deps()

import glob
import shutil
import subprocess
import webbrowser

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm
from rich import box

# ── 테마 ──────────────────────────────────────────────────────
console = Console()

Q_STYLE = Style(
    [
        ("qmark", "fg:#00daf3 bold"),
        ("question", "bold"),
        ("answer", "fg:#00daf3 bold"),
        ("pointer", "fg:#00daf3 bold"),
        ("highlighted", "fg:#00daf3 bold"),
        ("selected", "fg:#00daf3"),
        ("separator", "fg:#454652"),
        ("instruction", "fg:#908f9d"),
        ("text", ""),
        ("disabled", "fg:#454652 italic"),
    ]
)

ROOT = Path(__file__).parent
OPENCHIKEN_HOME = Path.home() / ".openchiken"

# uv tool install 환경(패키지 내부)이면 ~/.openchiken/.env 에 저장,
# git clone 개발 환경이면 프로젝트 루트에도 저장 (settings.py가 양쪽 모두 로드)
def _resolve_env_file() -> Path:
    try:
        OPENCHIKEN_HOME.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return OPENCHIKEN_HOME / ".env"

ENV_FILE = _resolve_env_file()
ENV_EXAMPLE = ROOT / ".env.example"

# ── 헬퍼 ──────────────────────────────────────────────────────
def step(n: int, total: int, title: str):
    console.print()
    console.print(Rule(f"[bold cyan]STEP {n}/{total}[/]  [bold]{title}[/]", style="cyan dim"))
    console.print()

def info(msg: str):
    console.print(f"  [dim]ℹ[/]  {msg}")

def ok(msg: str):
    console.print(f"  [bold green]✓[/]  {msg}")

def warn(msg: str):
    console.print(f"  [bold yellow]⚠[/]  {msg}")

def ask(prompt: str, default: str = "", password: bool = False, hint: str = "") -> str:
    if hint:
        console.print(f"  [dim]{hint}[/]")
    return questionary.text(
        f"  {prompt}",
        default=default,
        style=Q_STYLE,
        qmark="›",
    ).unsafe_ask() if not password else questionary.password(
        f"  {prompt}",
        style=Q_STYLE,
        qmark="›",
    ).unsafe_ask()

def select(prompt: str, choices: list, default: str = "") -> str:
    # default가 없으면 첫 번째 Choice의 value를 사용
    if not default:
        first = choices[0]
        default = first.value if hasattr(first, "value") else str(first)
    return questionary.select(
        f"  {prompt}",
        choices=choices,
        default=default,
        style=Q_STYLE,
        qmark="›",
        use_shortcuts=True,
    ).unsafe_ask()

def confirm(prompt: str, default: bool = True) -> bool:
    return questionary.confirm(
        f"  {prompt}",
        default=default,
        style=Q_STYLE,
        qmark="›",
    ).unsafe_ask()

TOTAL_STEPS = 6

# ── 섹션 헤더 출력 ────────────────────────────────────────────
def section(title: str, icon: str = "›"):
    """스텝 내 소항목 구분선."""
    console.print()
    console.print(f"  [bold cyan]{icon}[/] [bold]{title}[/]")
    console.print()

# ── 섹션별 설정 수집 ──────────────────────────────────────────
def collect_persona(cfg: dict):
    step(1, TOTAL_STEPS, "AI 비서 페르소나 설정")
    info("당신만의 AI 비서 캐릭터를 설정합니다. 이름, 말투, 성격을 지정하면")
    info("대화할 때 자연스럽게 그 캐릭터로 응답합니다.")
    console.print()

    # 비서 이름
    assistant_name = ask(
        "비서 이름을 정해주세요",
        default="치킨",
        hint="예) 민지, 알파, 아리아, 치킨 — 대화 중 이 이름으로 불립니다",
    )

    # 말투 선택
    _TONE_CASUAL = "캐주얼하고 친근한 존댓말로 대화합니다. '~요', '~해요' 형태로 답변하세요."
    tone = select(
        "어떤 말투로 대화할까요?",
        choices=[
            questionary.Choice("정중한 존댓말  (예: ~합니다, ~해드릴게요)", value="정중한 존댓말로 대화합니다. '~합니다', '~해드릴게요' 형태로 답변하세요."),
            questionary.Choice("친근한 반말    (예: ~해, ~할게, ~야)", value="친근하고 편안한 반말로 대화합니다. '~해', '~할게', '~야' 형태로 답변하세요."),
            questionary.Choice("캐주얼 존댓말  (예: ~요, ~해요, ~할게요)", value=_TONE_CASUAL),
            questionary.Choice("직접 입력", value="__custom__"),
        ],
        default=_TONE_CASUAL,
    )
    if tone == "__custom__":
        tone = ask("말투 지침을 직접 입력하세요", hint="예) 영어와 한국어를 섞어서 답변합니다")

    # 페르소나 선택
    console.print()
    info("성격·페르소나를 선택하세요.")
    persona = select(
        "비서의 성격을 골라주세요",
        choices=[
            questionary.Choice("🤝 친근하고 유머러스  — 가볍게 농담도 하고 편하게 대화", value="친근하고 유머러스한 성격입니다. 가끔 가벼운 농담을 섞고 사용자와 편하게 대화합니다."),
            questionary.Choice("💼 전문적이고 효율적  — 군더더기 없이 핵심만 빠르게", value="전문적이고 효율적인 성격입니다. 불필요한 말은 줄이고 핵심 정보를 빠르게 전달합니다."),
            questionary.Choice("🧘 차분하고 꼼꼼      — 세심하게 확인하며 안정감 있게", value="차분하고 꼼꼼한 성격입니다. 세심하게 확인하며 안정감 있게 대화합니다."),
            questionary.Choice("🎉 활발하고 긍정적    — 에너지 넘치게 응원하고 격려", value="활발하고 긍정적인 성격입니다. 에너지 넘치게 사용자를 응원하고 격려합니다."),
            questionary.Choice("✍️  직접 입력", value="__custom__"),
        ],
    )
    if persona == "__custom__":
        persona = ask("페르소나 설명을 직접 입력하세요", hint="예) 냉소적이고 솔직한 성격으로 직설적으로 말합니다")

    # 추가 자유 지침
    console.print()
    extra = ask(
        "추가로 주입할 지침이 있으면 입력하세요 (없으면 Enter)",
        default="",
        hint="예) 답변 끝에 항상 이모지를 붙입니다 / 영어로도 함께 답변합니다",
    )

    cfg["ASSISTANT_NAME"] = assistant_name
    cfg["ASSISTANT_TONE"] = tone
    cfg["ASSISTANT_PERSONA"] = persona
    cfg["ASSISTANT_EXTRA"] = extra

    console.print()
    console.print(
        Panel(
            Text.from_markup(
                f"\n"
                f"  [bold cyan]비서 이름[/]  {assistant_name}\n\n"
                f"  [bold cyan]말투[/]  {tone[:30]}{'...' if len(tone) > 30 else ''}\n\n"
                f"  [bold cyan]페르소나[/]  {persona[:40]}{'...' if len(persona) > 40 else ''}\n"
                + (f"\n  [bold cyan]추가 지침[/]  {extra[:40]}\n" if extra else "")
            ),
            title="[bold]페르소나 미리보기[/]",
            border_style="cyan dim",
            padding=(0, 2),
        )
    )
    ok(f"AI 비서 '{assistant_name}' 페르소나 설정 완료")


def collect_llm(cfg: dict):
    """Step 2 – LLM 공급자 선택 (웹 위저드 Step 2와 동일 구조)."""
    step(2, TOTAL_STEPS, "LLM 설정")
    info("AI 비서가 사용할 언어 모델 공급자와 API 키를 설정합니다.")
    console.print()

    provider = select(
        "LLM 공급자를 선택하세요",
        choices=[
            questionary.Choice("OpenAI          (GPT-4o 등)", value="openai"),
            questionary.Choice("Anthropic       (Claude 3.5 등)", value="anthropic"),
            questionary.Choice("Google Gemini   (Gemini 2.0 등)", value="gemini"),
        ],
        default="openai",
    )
    cfg["LLM_PROVIDER"] = provider
    console.print()

    if provider == "openai":
        info("API 키 발급: https://platform.openai.com/api-keys")
        key = ask("OpenAI API Key", password=True, hint="sk- 로 시작하는 문자열")
        if not key.startswith("sk-"):
            warn("키 형식이 올바르지 않습니다. 나중에 .env 에서 수정 가능합니다.")
        model = select(
            "사용할 모델",
            choices=[
                questionary.Choice("gpt-4o          (추천 · 최고 성능)", value="gpt-4o"),
                questionary.Choice("gpt-4o-mini     (빠르고 저렴)", value="gpt-4o-mini"),
                questionary.Choice("gpt-4-turbo", value="gpt-4-turbo"),
                questionary.Choice("직접 입력", value="__custom__"),
            ],
            default="gpt-4o",
        )
        if model == "__custom__":
            model = ask("모델 이름 입력")
        cfg["OPENAI_API_KEY"] = key
        cfg["OPENAI_MODEL"] = model
        ok(f"OpenAI 설정 완료 (모델: {model})")

    elif provider == "anthropic":
        info("API 키 발급: https://console.anthropic.com/settings/keys")
        key = ask("Anthropic API Key", password=True, hint="sk-ant- 로 시작하는 문자열")
        model = select(
            "사용할 모델",
            choices=[
                questionary.Choice("claude-3-5-sonnet-latest   (추천 · 균형)", value="claude-3-5-sonnet-latest"),
                questionary.Choice("claude-3-5-haiku-latest    (빠르고 저렴)", value="claude-3-5-haiku-latest"),
                questionary.Choice("claude-3-opus-latest       (최고 성능)", value="claude-3-opus-latest"),
                questionary.Choice("직접 입력", value="__custom__"),
            ],
            default="claude-3-5-sonnet-latest",
        )
        if model == "__custom__":
            model = ask("모델 이름 입력")
        cfg["ANTHROPIC_API_KEY"] = key
        cfg["ANTHROPIC_MODEL"] = model
        ok(f"Anthropic 설정 완료 (모델: {model})")

    elif provider == "gemini":
        info("API 키 발급: https://aistudio.google.com/app/apikey")
        key = ask("Google AI (Gemini) API Key", password=True)
        model = select(
            "사용할 모델",
            choices=[
                questionary.Choice("gemini-2.0-flash    (추천 · 빠름)", value="gemini-2.0-flash"),
                questionary.Choice("gemini-2.0-pro      (최고 성능)", value="gemini-2.0-pro"),
                questionary.Choice("gemini-1.5-flash", value="gemini-1.5-flash"),
                questionary.Choice("직접 입력", value="__custom__"),
            ],
            default="gemini-2.0-flash",
        )
        if model == "__custom__":
            model = ask("모델 이름 입력")
        cfg["GEMINI_API_KEY"] = key
        cfg["GEMINI_MODEL"] = model
        ok(f"Gemini 설정 완료 (모델: {model})")


def _setup_telegram(cfg: dict):
    """Telegram 설정 (collect_channels 내부에서 호출)."""
    section("Telegram 설정", "📱")
    info("@BotFather 에게 /newbot 명령을 보내 봇을 생성하고 토큰을 발급받으세요.")
    console.print()

    token = ask("Telegram Bot Token", hint="예) 123456789:AAH8_vXj...")
    if ":" not in token:
        warn("토큰 형식이 올바르지 않을 수 있습니다.")

    user_ids = ask(
        "허용할 User ID (비워두면 모든 사용자 허용 · 전 채널 공통)",
        default="",
        hint="@userinfobot 에게 메시지를 보내면 내 ID를 알 수 있습니다. 예) 123456789",
    )
    cfg["TELEGRAM_BOT_TOKEN"] = token
    cfg["ALLOWED_USER_IDS"] = user_ids
    ok("Telegram 설정 완료")


def _setup_slack(cfg: dict):
    """Slack 설정 (collect_channels 내부에서 호출)."""
    section("Slack 설정", "💬")
    console.print(
        Panel(
            Text.from_markup(
                "\n"
                "  [bold cyan]Slack App 설정 가이드[/]\n\n"
                "  1. https://api.slack.com/apps 에서 새 앱 생성\n"
                "  2. [bold]Socket Mode[/] 활성화 → App-Level Token 발급 (xapp-...)\n"
                "  3. [bold]OAuth & Permissions[/] → Bot Token Scopes 추가:\n"
                "     [dim]app_mentions:read  chat:write  im:history  im:read  im:write[/]\n"
                "  4. 앱을 워크스페이스에 설치 → Bot User OAuth Token 복사 (xoxb-...)\n"
            ),
            border_style="cyan dim",
            padding=(0, 2),
        )
    )
    console.print()
    bot_token = ask("Slack Bot Token (xoxb-...)")
    if not bot_token.startswith("xoxb-"):
        warn("토큰이 'xoxb-' 로 시작하지 않습니다.")
    app_token = ask("Slack App-Level Token (xapp-...)")
    if not app_token.startswith("xapp-"):
        warn("토큰이 'xapp-' 로 시작하지 않습니다.")
    cfg["SLACK_BOT_TOKEN"] = bot_token
    cfg["SLACK_APP_TOKEN"] = app_token
    ok("Slack 설정 완료")


def _setup_discord(cfg: dict):
    """Discord 설정 (collect_channels 내부에서 호출)."""
    section("Discord 설정", "🎮")
    console.print(
        Panel(
            Text.from_markup(
                "\n"
                "  [bold cyan]Discord Bot 설정 가이드[/]\n\n"
                "  1. https://discord.com/developers/applications → New Application\n"
                "  2. [bold]Bot[/] 탭 → Reset Token → 복사\n"
                "  3. Privileged Gateway Intents →\n"
                "     [bold yellow]Message Content Intent[/bold yellow]  반드시 ON\n"
                "  4. OAuth2 → URL Generator → 초대 URL로 서버에 초대\n"
            ),
            border_style="cyan dim",
            padding=(0, 2),
        )
    )
    console.print()
    token = ask("Discord Bot Token", hint="예) MTAw... (Bot 탭에서 복사)")
    allowed_ids = ask(
        "허용할 Discord User ID (비워두면 전체 허용)",
        default="",
        hint="Discord 설정 → 고급 → 개발자 모드 ON → 본인 이름 우클릭 → 사용자 ID 복사",
    )
    cfg["DISCORD_BOT_TOKEN"] = token
    if allowed_ids:
        existing = {x.strip() for x in cfg.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
        new_ids  = {x.strip() for x in allowed_ids.split(",") if x.strip()}
        cfg["ALLOWED_USER_IDS"] = ",".join(existing | new_ids)
    ok("Discord 설정 완료")


def _setup_imessage(cfg: dict):
    """iMessage 설정 (collect_channels 내부에서 호출, macOS 전용)."""
    section("iMessage 설정", "💬")
    info("macOS Messages.app 폴링 기반으로 동작합니다. 별도 API 키가 필요 없습니다.")
    console.print()

    console.print(
        Panel(
            Text.from_markup(
                "\n"
                "  [bold green]전체 디스크 접근 권한 안내[/]\n\n"
                "  iMessage 수신을 위해 [bold]~/Library/Messages/chat.db[/] 읽기 권한이 필요합니다.\n"
                "  macOS 보안 정책상 [bold yellow]사용자가 직접[/bold yellow] 부여해야 합니다:\n\n"
                "  [bold]1.[/] 아래에서 시스템 설정을 열고\n"
                "  [bold]2.[/] [cyan]개인정보 보호 및 보안 → 전체 디스크 접근[/cyan] 으로 이동\n"
                "  [bold]3.[/] [cyan]+[/cyan] 버튼 → Terminal.app 추가 후 토글 활성화\n"
            ),
            border_style="green dim",
            padding=(0, 2),
        )
    )
    console.print()

    if confirm("지금 시스템 설정을 여시겠습니까? (권장)", default=True):
        try:
            subprocess.Popen([
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            ])
            ok("시스템 설정이 열렸습니다.")
            console.print("  [dim]→ 개인정보 보호 및 보안 → 전체 디스크 접근 → + 버튼[/]")
            console.print()
            confirm("권한 추가 후 Enter를 눌러 계속하세요", default=True)
        except Exception as e:
            warn(f"자동으로 열지 못했습니다: {e}")

    handles = ask(
        "허용할 iMessage 핸들 (비워두면 전체 연락처 허용)",
        default="",
        hint="예) +821012345678,you@apple.com",
    )
    poll = select(
        "메시지 확인 간격",
        choices=[
            questionary.Choice("2초  (빠른 응답)", value="2"),
            questionary.Choice("3초  (기본값)", value="3"),
            questionary.Choice("5초  (배터리 절약)", value="5"),
            questionary.Choice("10초 (최소 부하)", value="10"),
        ],
        default="3",
    )
    cfg["IMESSAGE_ALLOWED_HANDLES"] = handles
    cfg["IMESSAGE_POLL_INTERVAL"] = poll
    ok(f"iMessage 설정 완료 (폴링: {poll}초)")


def collect_channels(cfg: dict):
    """Step 3 – 채널 설정 (웹 위저드 Step 3와 동일 구조)."""
    step(3, TOTAL_STEPS, "채널 설정")
    info("AI 비서와 대화할 채널을 선택하세요. 여러 채널을 동시에 활성화할 수 있습니다.")
    console.print()

    # 채널 체크박스 (복수 선택)
    channel_choices = [
        questionary.Choice("📱  Telegram    (기본 · 추천)", value="telegram", checked=True),
        questionary.Choice("💬  Slack       (팀 워크스페이스)", value="slack"),
        questionary.Choice("🎮  Discord     (서버 · DM)", value="discord"),
    ]
    if sys.platform == "darwin":
        channel_choices.append(
            questionary.Choice("💬  iMessage   (macOS 전용 · API 키 불필요)", value="imessage")
        )

    selected = questionary.checkbox(
        "  활성화할 채널을 선택하세요 (스페이스로 토글, Enter로 확인)",
        choices=channel_choices,
        style=Q_STYLE,
        qmark="›",
    ).unsafe_ask()

    if not selected:
        warn("채널을 선택하지 않았습니다. Telegram을 기본으로 사용합니다.")
        selected = ["telegram"]

    console.print()

    # 선택된 채널마다 세부 설정
    if "telegram" in selected:
        _setup_telegram(cfg)
    if "slack" in selected:
        _setup_slack(cfg)
    if "discord" in selected:
        _setup_discord(cfg)
    if "imessage" in selected:
        _setup_imessage(cfg)

    cfg["_selected_channels"] = selected
    ok(f"채널 설정 완료: {', '.join(selected)}")


# ── GCP 자동화 헬퍼 ──────────────────────────────────────────
_GCP_APIS = [
    "gmail.googleapis.com",
    "calendar-json.googleapis.com",
    "drive.googleapis.com",
    "sheets.googleapis.com",
    "docs.googleapis.com",
]


def _has_gcloud() -> bool:
    return shutil.which("gcloud") is not None


def _gcloud_auto_setup(project_id: str) -> bool:
    """gcloud CLI로 GCP 프로젝트 생성 + API 일괄 활성화"""
    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
            task = progress.add_task("GCP 프로젝트 생성 중...", total=None)
            r = subprocess.run(
                ["gcloud", "projects", "create", project_id, f"--name=OpenChiken", "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0 and "already exists" not in r.stderr.lower():
                logger.debug("gcloud projects create error: %s", r.stderr)
                return False

            progress.update(task, description="프로젝트 기본값 설정 중...")
            subprocess.run(
                ["gcloud", "config", "set", "project", project_id, "--quiet"],
                capture_output=True, timeout=15,
            )

            progress.update(task, description="Google API 활성화 중 (Gmail, Calendar, Drive, Sheets, Docs)...")
            r2 = subprocess.run(
                ["gcloud", "services", "enable"] + _GCP_APIS + [f"--project={project_id}", "--quiet"],
                capture_output=True, text=True, timeout=120,
            )
            if r2.returncode != 0:
                logger.debug("gcloud services enable error: %s", r2.stderr)
                return False
        return True
    except Exception as e:
        logger.debug("_gcloud_auto_setup failed: %s", e)
        return False


def _python_auto_setup(project_id: str) -> bool:
    """Python 라이브러리(ADC)로 GCP 프로젝트 생성 + API 활성화"""
    try:
        import google.auth
        import google.auth.transport.requests
        from googleapiclient.discovery import build as gdiscovery_build

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        req = google.auth.transport.requests.Request()
        if not creds.valid:
            creds.refresh(req)

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
            task = progress.add_task("GCP 프로젝트 생성 중 (Python ADC)...", total=None)

            rm = gdiscovery_build("cloudresourcemanager", "v3", credentials=creds)
            try:
                rm.projects().create(body={
                    "displayName": "OpenChiken",
                    "projectId": project_id,
                }).execute()
                time.sleep(5)  # 프로젝트 활성화 대기
            except Exception as e:
                if "already exists" not in str(e).lower():
                    raise

            progress.update(task, description="API 활성화 중...")
            su = gdiscovery_build("serviceusage", "v1", credentials=creds)
            su.services().batchEnable(
                parent=f"projects/{project_id}",
                body={"serviceIds": _GCP_APIS},
            ).execute()

        return True
    except Exception as e:
        logger.debug("_python_auto_setup failed: %s", e)
        return False


def _watch_downloads_for_credentials(dst: Path, timeout_sec: int = 180) -> bool:
    """~/Downloads 에서 Google OAuth client_secret_*.json 파일 자동 감지 → 복사"""
    downloads = Path.home() / "Downloads"
    # Windows 기본 다운로드 경로 폴백
    if not downloads.exists():
        downloads = Path.home() / "다운로드"

    deadline = time.time() + timeout_sec
    console.print(f"  [dim]자동 감지 경로: {downloads}[/dim]")
    console.print("  [dim]다운로드가 완료되면 자동으로 복사됩니다 (최대 {timeout_sec}초 대기)...[/dim]")

    while time.time() < deadline:
        patterns = [
            str(downloads / "client_secret_*.json"),
            str(downloads / "credentials*.json"),
        ]
        candidates = []
        for p in patterns:
            candidates.extend(glob.glob(p))

        if candidates:
            newest = max(candidates, key=lambda p: Path(p).stat().st_mtime)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(newest, dst)
            return True
        time.sleep(2)

    return False


def _run_oauth_inline() -> bool:
    """setup 완료 직후 Google OAuth 인증을 인라인으로 실행하여 token.json 저장"""
    try:
        from core.google_auth import get_google_credentials
        console.print()
        console.print("  [dim]브라우저가 열립니다. Google 계정으로 로그인하고 권한을 허용해주세요.[/dim]")
        console.print(
            Panel(
                Text.from_markup(
                    "\n"
                    "  [bold yellow]⚠  'Google이 이 앱을 확인하지 않았습니다' 화면이 나오면[/]\n\n"
                    "  [bold cyan]고급[/] 클릭 → [bold cyan]OpenChiken으로 이동(안전하지 않음)[/] 클릭\n\n"
                    "  이는 앱 검증을 받지 않은 개인용 OAuth 앱의 정상적인 동작입니다.\n"
                    "  테스트 사용자로 등록된 계정만 계속 진행할 수 있습니다."
                ),
                border_style="yellow",
                padding=(0, 2),
            )
        )
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
            progress.add_task("OAuth 인증 대기 중...", total=None)
            get_google_credentials()
        return True
    except Exception as e:
        warn(f"OAuth 인증 실패: {e}")
        return False


def _google_guide(cfg: dict):
    """Google OAuth 설정 가이드 (collect_app_settings 내부에서 호출)."""
    home_creds = Path.home() / ".openchiken" / "credentials.json"
    local_creds = ROOT / "credentials.json"

    # ── 자동화 경로 선택 ─────────────────────────────────────────────────
    console.print()
    has_gcloud = _has_gcloud()

    if has_gcloud:
        console.print(
            Panel(
                Text.from_markup(
                    "\n"
                    "  [bold green]✓  gcloud CLI 감지됨[/]\n\n"
                    "  GCP 프로젝트 생성과 API 활성화를 자동으로 진행할 수 있습니다.\n"
                    "  (Gmail, Calendar, Drive, Sheets, Docs API 일괄 활성화)\n"
                ),
                border_style="green dim",
                padding=(0, 2),
            )
        )
    else:
        # ADC 확인
        has_adc = False
        try:
            import google.auth
            google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            has_adc = True
        except Exception:
            pass

        if has_adc:
            console.print(
                Panel(
                    Text.from_markup(
                        "\n"
                        "  [bold green]✓  Application Default Credentials (ADC) 감지됨[/]\n\n"
                        "  Python 라이브러리로 GCP 프로젝트 생성과 API 활성화를 자동 진행합니다.\n"
                    ),
                    border_style="green dim",
                    padding=(0, 2),
                )
            )
        else:
            console.print(
                Panel(
                    Text.from_markup(
                        "\n"
                        "  [bold yellow]gcloud CLI 미감지 — 수동 안내 모드[/]\n\n"
                        "  브라우저를 통해 단계별로 설정을 진행합니다.\n"
                        "  (gcloud 설치 시 다음번에는 자동으로 진행됩니다)\n"
                    ),
                    border_style="yellow dim",
                    padding=(0, 2),
                )
            )

    # ── G-1: 프로젝트 생성 ────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]G-1[/]  Google Cloud 프로젝트 생성", style="dim"))
    console.print()

    project_id = ""
    if has_gcloud:
        project_id = ask(
            "GCP 프로젝트 ID (영문·숫자·하이픈, 6~30자)",
            default="openchiken",
            hint="예) openchiken-2025  ─  이미 있는 프로젝트 ID를 입력하면 재사용",
        )
        ok_flag = _gcloud_auto_setup(project_id)
        if ok_flag:
            ok(f"프로젝트 '{project_id}' 생성 + API 5종 활성화 완료!")
        else:
            warn("자동 설정 실패. 수동으로 진행합니다.")
            project_id = ""
    elif has_adc:
        project_id = ask(
            "GCP 프로젝트 ID (영문·숫자·하이픈, 6~30자)",
            default="openchiken",
        )
        ok_flag = _python_auto_setup(project_id)
        if ok_flag:
            ok(f"프로젝트 '{project_id}' 생성 + API 활성화 완료! (Python ADC)")
        else:
            warn("자동 설정 실패. 수동으로 진행합니다.")
            project_id = ""

    if not project_id or not (has_gcloud or has_adc):
        # 수동: 브라우저 자동 오픈
        if confirm("  브라우저에서 GCP 프로젝트 생성 페이지를 여시겠습니까?", default=True):
            webbrowser.open("https://console.cloud.google.com/projectcreate")
        console.print()
        console.print("  [bold]1.[/] 프로젝트 이름: [cyan]OpenChiken[/cyan] → [bold cyan]만들기[/bold cyan]")
        console.print()
        if not confirm("  프로젝트를 만들었나요?", default=True):
            warn("G-1 완료 후 다시 실행하세요.")
            return

        # G-2: API 활성화 (수동)
        console.print()
        console.print(Rule("[bold]G-2[/]  API 활성화 (5종)", style="dim"))
        console.print()
        api_links = [
            ("Gmail API", "https://console.cloud.google.com/apis/library/gmail.googleapis.com"),
            ("Google Calendar API", "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com"),
            ("Google Drive API", "https://console.cloud.google.com/apis/library/drive.googleapis.com"),
            ("Google Sheets API", "https://console.cloud.google.com/apis/library/sheets.googleapis.com"),
            ("Google Docs API", "https://console.cloud.google.com/apis/library/docs.googleapis.com"),
        ]
        for name, link in api_links:
            console.print(f"  [bold cyan]{name}[/]")
            console.print(f"     [link={link}]{link}[/link]")
            console.print()
        if confirm("  모든 브라우저 링크를 한번에 열까요?", default=True):
            for _, link in api_links:
                webbrowser.open(link)
                time.sleep(0.5)
        if not confirm("  5개 API를 모두 활성화했나요?", default=True):
            warn("G-2 완료 후 다시 실행하세요.")
            return

    # ── G-3: OAuth 동의 화면 (항상 수동 — Google 보안 정책상 자동화 불가) ──
    console.print()
    console.print(Rule("[bold]G-3[/]  OAuth 동의 화면 구성 (수동 필수)", style="dim"))
    console.print()
    consent_url = (
        f"https://console.cloud.google.com/apis/credentials/consent?project={project_id}"
        if project_id
        else "https://console.cloud.google.com/apis/credentials/consent"
    )
    if confirm("  OAuth 동의 화면 설정 페이지를 브라우저에서 열까요?", default=True):
        webbrowser.open(consent_url)
    console.print()
    console.print("  [bold]1.[/] User Type: [bold cyan]외부[/bold cyan] → [bold cyan]만들기[/bold cyan]")
    console.print("  [bold]2.[/] 앱 이름: [cyan]OpenChiken[/cyan], 이메일: 본인 Gmail")
    console.print("  [bold]3.[/] [bold cyan]저장 후 계속[/bold cyan] (범위 단계도 저장 후 계속)")
    console.print("  [bold]4.[/] [bold yellow]테스트 사용자[/bold yellow] → [bold cyan]+ 사용자 추가[/bold cyan] → 본인 Gmail 입력")
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "  [bold yellow]⚠  테스트 사용자 등록은 필수입니다 (본인 포함)[/]\n\n"
                "  Google 앱 검증 전까지 최대 100개 계정을 무료로 등록 가능합니다.\n"
                "  등록되지 않은 계정은 'Access blocked' 오류가 발생합니다."
            ),
            border_style="yellow",
            padding=(0, 2),
        )
    )
    console.print()
    if not confirm("  OAuth 동의 화면 구성 및 테스트 사용자 추가 완료?", default=True):
        warn("G-3 완료 후 다시 실행하세요.")
        return

    # ── G-4: OAuth 클라이언트 생성 + credentials.json 자동 감지 ───────────
    console.print()
    console.print(Rule("[bold]G-4[/]  OAuth 2.0 클라이언트 ID 생성 + 자동 감지", style="dim"))
    console.print()
    creds_url = (
        f"https://console.cloud.google.com/apis/credentials?project={project_id}"
        if project_id
        else "https://console.cloud.google.com/apis/credentials"
    )
    if confirm("  사용자 인증 정보 페이지를 브라우저에서 열까요?", default=True):
        webbrowser.open(creds_url)
    console.print()
    console.print("  [bold]1.[/] [bold cyan]+ 사용자 인증 정보 만들기[/bold cyan] → [bold cyan]OAuth 클라이언트 ID[/bold cyan]")
    console.print("  [bold]2.[/] 애플리케이션 유형: [bold cyan]데스크톱 앱[/bold cyan]  이름: [cyan]openchiken-desktop[/cyan]")
    console.print("  [bold]3.[/] [bold cyan]JSON 다운로드[/bold cyan] 클릭 → 파일이 다운로드 폴더에 저장됩니다")
    console.print()

    # Downloads 폴더 자동 감지 시도
    if confirm("  다운로드 후 자동 감지를 시작할까요? (최대 3분 대기)", default=True):
        console.print()
        found = _watch_downloads_for_credentials(home_creds, timeout_sec=180)
        if found:
            ok(f"credentials.json 자동 감지 및 복사 완료 → {home_creds}")
        else:
            warn("자동 감지 시간이 초과되었습니다. 수동으로 파일을 복사해주세요.")
            console.print(f"  저장 경로: [bold cyan]{home_creds}[/bold cyan]")
            console.print(f"  또는:      [dim]{local_creds}[/dim]")
            console.print()
            if not confirm("  파일을 배치했나요?", default=True):
                warn("credentials.json 없이 계속합니다. Google 스킬 사용 불가.")
                return
    else:
        # 수동 배치
        console.print(f"  저장 경로: [bold cyan]{home_creds}[/bold cyan]")
        console.print(f"  또는:      [dim]{local_creds}[/dim]")
        console.print()
        for _ in range(5):
            if home_creds.exists() or local_creds.exists():
                found_path = home_creds if home_creds.exists() else local_creds
                ok(f"credentials.json 확인: {found_path}")
                break
            if not confirm("  파일을 배치하고 계신가요? 다시 확인할까요?", default=True):
                warn("credentials.json 없이 계속합니다.")
                return

    # ── G-5: 인라인 OAuth 인증 ─────────────────────────────────────────────
    if (home_creds.exists() or local_creds.exists()):
        console.print()
        console.print(Rule("[bold]G-5[/]  Google 계정 인증 (브라우저 로그인)", style="dim"))
        console.print()
        if confirm("  지금 바로 Google 계정 인증을 완료할까요? (권장)", default=True):
            success = _run_oauth_inline()
            if success:
                ok("Google 인증 완료! token.json이 저장되었습니다. 모든 스킬을 즉시 사용할 수 있습니다.")
            else:
                warn("인증을 나중에 진행합니다. 봇 첫 실행 시 브라우저가 열립니다.")
        else:
            ok("Google 설정 완료 — 봇 첫 실행 시 브라우저가 열려 Google 계정 인증을 진행합니다.")


def collect_memory(cfg: dict):
    """Step 4 – 메모리 설정 (웹 위저드 Step 4와 동일 구조)."""
    step(4, TOTAL_STEPS, "메모리 설정")
    info("대화 기록, 메모, 할 일을 어디에 저장할지 설정합니다.")
    console.print()

    storage = select(
        "저장 방식을 선택하세요",
        choices=[
            questionary.Choice(
                "로컬 파일 (SQLite)  — 별도 설치 없이 바로 사용 · 권장",
                value="local",
            ),
            questionary.Choice(
                "직접 지정           — PostgreSQL 등 외부 DB 사용 시",
                value="custom",
            ),
        ],
        default="local",
    )

    if storage == "local":
        cfg["DATABASE_URL"] = "sqlite:///openchiken.db"
        ok("로컬 SQLite 선택 완료")
    else:
        db_url = ask(
            "Database URL",
            hint="예) postgresql://user:pass@localhost/openchiken",
        )
        cfg["DATABASE_URL"] = db_url
        ok(f"데이터베이스 설정 완료 → {db_url}")


def collect_app_settings(cfg: dict):
    """Step 5 – 앱 설정 (웹 위저드 Step 5와 동일 구조: Google + 스케줄러 + 스킬)."""
    step(5, TOTAL_STEPS, "앱 설정")
    info("Google 연동, 알림 타이밍, 활성화할 기능을 설정합니다. 모두 선택 사항입니다.")

    # ── A. Google 연동 ────────────────────────────────────────────────────
    section("Google 연동 (Gmail · Calendar)", "📧")
    info("건너뛰면 이메일·일정 기능을 사용할 수 없습니다.")
    console.print()

    home_creds  = Path.home() / ".openchiken" / "credentials.json"
    local_creds = ROOT / "credentials.json"

    if home_creds.exists() or local_creds.exists():
        found = home_creds if home_creds.exists() else local_creds
        ok(f"credentials.json 발견: {found}")
        ok("Google 연동 활성 — 첫 실행 시 브라우저로 계정 인증을 진행합니다.")
    elif confirm("지금 Google API를 설정하시겠습니까?", default=True):
        _google_guide(cfg)
    else:
        warn("Google 연동 건너뜀 — Gmail·Calendar 기능 사용 불가")

    # ── B. 스케줄러 ───────────────────────────────────────────────────────
    section("알림 타이밍", "⏰")

    hour_choices = [questionary.Choice(f"{h:02d}:00", value=str(h)) for h in range(5, 13)]
    briefing_hour = select("아침 브리핑 전송 시각 (KST)", choices=hour_choices, default="8")

    reminder = select(
        "일정 리마인더 발송 시점",
        choices=[
            questionary.Choice("5분 전", value="5"),
            questionary.Choice("10분 전", value="10"),
            questionary.Choice("15분 전 (기본)", value="15"),
            questionary.Choice("30분 전", value="30"),
            questionary.Choice("60분 전", value="60"),
        ],
        default="15",
    )
    cfg["MORNING_BRIEFING_HOUR"] = briefing_hour
    cfg["REMINDER_MINUTES_BEFORE"] = reminder
    ok(f"스케줄러 설정 완료 (브리핑: {briefing_hour}:00, 리마인더: {reminder}분 전)")

    # ── C. 스킬 ───────────────────────────────────────────────────────────
    section("활성화할 스킬", "🔌")
    info("스킬별 외부 자격증명(Google OAuth 등)이 없으면 자동으로 건너뜁니다.")
    console.print()

    use_all = confirm("모든 스킬을 활성화하시겠습니까? (권장)", default=True)
    if use_all:
        cfg["ENABLED_SKILLS"] = "all"
        ok("모든 스킬 활성화")
    else:
        selected = questionary.checkbox(
            "  활성화할 스킬을 선택하세요 (스페이스로 토글, Enter로 확인)",
            choices=[
                questionary.Choice("📧  gmail      — Gmail 검색 · 읽기 · 전송", value="gmail"),
                questionary.Choice("📅  calendar   — Google Calendar 조회 · 생성 · 삭제", value="calendar"),
                questionary.Choice("📁  drive      — Google Drive 파일 조회 · 검색 · 업로드 · 폴더 관리", value="drive"),
                questionary.Choice("📊  sheets     — Google Sheets 스프레드시트 읽기 · 쓰기 · 생성", value="sheets"),
                questionary.Choice("📄  docs       — Google Docs 문서 읽기 · 생성 · 내용 추가", value="docs"),
                questionary.Choice("⚙️   workflow   — 스탠드업 보고 · 주간 요약 · 미팅 준비 복합 자동화", value="workflow"),
                questionary.Choice("🌤  weather    — 현재 날씨 · N일 예보", value="weather"),
                questionary.Choice("🔍  web_search — DuckDuckGo 실시간 웹 검색", value="web_search"),
                questionary.Choice("📝  memo       — SQLite 기반 메모 저장 · 조회 · 삭제", value="memo"),
                questionary.Choice("📋  task       — 복잡한 작업 진행 상황 추적", value="task"),
                questionary.Choice("💹  finance    — 주식 · 암호화폐 시세 및 기술적 분석", value="finance"),
            ],
            style=Q_STYLE,
            qmark="›",
        ).unsafe_ask()

        if not selected:
            warn("선택 없음 — 모든 스킬을 활성화합니다.")
            cfg["ENABLED_SKILLS"] = "all"
        else:
            cfg["ENABLED_SKILLS"] = ",".join(selected)
            ok(f"선택된 스킬: {', '.join(selected)}")


# ── Chrome Extension 설치 ─────────────────────────────────
CHROME_PATHS = {
    "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "linux": "google-chrome",
    "win32": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
}

RELAY_HEALTH_URL = "https://openchiken-relay-production.up.railway.app/api/agents"


def _find_chrome() -> str | None:
    path = CHROME_PATHS.get(sys.platform)
    if path and Path(path).exists():
        return path
    return shutil.which("google-chrome") or shutil.which("chrome") or shutil.which("chromium")


def _check_relay_connection(timeout_sec: int = 30) -> str | None:
    """Relay 서버에서 Extension 연결을 폴링. 연결된 agentId 반환."""
    import urllib.request
    import json

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            req = urllib.request.Request(RELAY_HEALTH_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                agents = data.get("agents", [])
                if agents:
                    return agents[0].get("agentId")
        except Exception:
            pass
        time.sleep(2)
    return None


def collect_extension(cfg: dict):
    """Step 6 – Chrome Extension 설치."""
    step(6, TOTAL_STEPS, "Chrome Extension 설치")
    info("외부 에이전트 연동을 위한 Chrome Extension을 설치합니다.")
    info("Extension은 브라우저와 Relay 서버를 연결하는 채널 역할을 합니다.")
    console.print()

    if not confirm("Chrome Extension을 설치하시겠습니까?", default=True):
        warn("Extension 설치 건너뜀 — 외부 에이전트 연동 기능을 사용할 수 없습니다.")
        return

    ext_path = ROOT / "extensions" / "chrome"
    if not (ext_path / "manifest.json").exists():
        warn(f"Extension 파일을 찾을 수 없습니다: {ext_path}")
        warn("openchiken/extensions/chrome/ 디렉토리를 확인하세요.")
        return

    # 아이콘이 없으면 생성
    icons_dir = ext_path / "icons"
    if not (icons_dir / "icon48.png").exists():
        gen_script = ext_path / "scripts" / "generate-icons.js"
        if gen_script.exists() and shutil.which("node"):
            info("아이콘 생성 중...")
            subprocess.run(["node", str(gen_script)], capture_output=True)

    console.print()
    ok(f"Extension 경로: {ext_path}")
    console.print()

    chrome_bin = _find_chrome()
    if not chrome_bin:
        warn("Chrome 브라우저를 찾을 수 없습니다.")
        console.print(f"  수동으로 chrome://extensions 에서 아래 폴더를 로드하세요:")
        console.print(f"  [cyan]{ext_path}[/]")
        return

    # Chrome이 실행 중인지 확인
    chrome_running = False
    try:
        result = subprocess.run(["pgrep", "-x", "Google Chrome"], capture_output=True)
        chrome_running = result.returncode == 0
    except FileNotFoundError:
        pass

    if chrome_running:
        console.print(
            Panel(
                Text.from_markup(
                    "\n"
                    "  [bold yellow]Chrome이 실행 중입니다[/]\n\n"
                    "  자동 로드를 위해 Chrome을 잠시 종료해야 합니다.\n"
                    "  또는 수동으로 설치할 수 있습니다.\n"
                ),
                border_style="yellow dim",
                padding=(0, 2),
            )
        )
        choice = select(
            "설치 방법을 선택하세요",
            choices=[
                questionary.Choice("Chrome 종료 후 Extension과 함께 재시작 (권장)", value="restart"),
                questionary.Choice("수동 설치 안내 (chrome://extensions)", value="manual"),
                questionary.Choice("건너뛰기", value="skip"),
            ],
            default="restart",
        )

        if choice == "skip":
            warn("Extension 설치를 건너뜁니다.")
            return
        elif choice == "manual":
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Google Chrome", "chrome://extensions"])
            console.print()
            console.print("  [bold]1.[/] 우상단 [bold cyan]개발자 모드[/] 토글 ON")
            console.print(f"  [bold]2.[/] [bold cyan]압축해제된 확장 프로그램을 로드합니다[/] 클릭")
            console.print(f"  [bold]3.[/] 아래 경로 선택:")
            console.print(f"     [cyan]{ext_path}[/]")
            console.print()
            confirm("  Extension을 로드했나요?", default=True)
            ok("수동 설치 완료")
            return
        else:
            # Chrome 종료
            info("Chrome을 종료합니다...")
            if sys.platform == "darwin":
                subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to quit'], capture_output=True)
            else:
                subprocess.run(["pkill", "-f", "chrome"], capture_output=True)
            time.sleep(2)

    # Chrome을 --load-extension 과 함께 시작
    info("Chrome을 Extension과 함께 시작합니다...")
    console.print()

    if sys.platform == "darwin":
        subprocess.Popen(["open", "-a", "Google Chrome", "--args", f"--load-extension={ext_path}"])
    else:
        subprocess.Popen([chrome_bin, f"--load-extension={ext_path}"])

    time.sleep(3)

    # Relay 연결 확인
    console.print()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as progress:
        progress.add_task("Relay 서버 연결 확인 중...", total=None)
        agent_id = _check_relay_connection(timeout_sec=30)

    if agent_id:
        ok(f"Extension 연결 확인! agentId: {agent_id}")
        cfg["EXTENSION_AGENT_ID"] = agent_id
    else:
        warn("자동 연결 확인에 실패했습니다.")
        info("Chrome에서 Extension 아이콘이 보이면 정상 설치된 것입니다.")
        info("Relay 서버 연결은 Extension 팝업에서 확인할 수 있습니다.")


# ── .env 파일 작성 ──────────────────────────────────────────
def write_env(cfg: dict):
    console.print()
    console.print(Rule("[bold cyan]설정 요약[/]", style="cyan dim"))
    console.print()

    # ENABLED_CHANNELS 구성 (write 전에 확정)
    selected_channels = cfg.pop("_selected_channels", ["telegram"])
    cfg["ENABLED_CHANNELS"] = ",".join(selected_channels)

    # 요약 테이블 (내부 키 제외)
    table = Table(
        show_header=True,
        header_style="bold cyan",
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        pad_edge=False,
    )
    table.add_column("설정 키", style="dim", width=30)
    table.add_column("값", max_width=50)

    SENSITIVE = {"KEY", "TOKEN", "SECRET"}
    for k, v in cfg.items():
        if not str(v):
            continue
        is_secret = any(s in k for s in SENSITIVE)
        display_v = f"●●●●●●●● ...{str(v)[-4:]}" if is_secret else str(v)
        table.add_row(k, display_v)

    console.print(table)
    console.print()

    if ENV_FILE.exists():
        if not confirm(".env 파일이 이미 존재합니다. 덮어쓰시겠습니까?", default=False):
            console.print("  [yellow]취소되었습니다. 기존 .env 파일이 유지됩니다.[/]")
            return False

    provider = cfg.get("LLM_PROVIDER", "openai")

    lines = [
        "# OpenChiken 환경 설정 – setup_wizard.py 로 생성됨",
        f"# {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "# ── Persona ──────────────────────────────",
        f"ASSISTANT_NAME={cfg.get('ASSISTANT_NAME', '치킨')}",
        f"ASSISTANT_TONE={cfg.get('ASSISTANT_TONE', '')}",
        f"ASSISTANT_PERSONA={cfg.get('ASSISTANT_PERSONA', '')}",
        f"ASSISTANT_EXTRA={cfg.get('ASSISTANT_EXTRA', '')}",
        "",
        "# ── LLM ─────────────────────────────────",
        f"LLM_PROVIDER={provider}",
        f"OPENAI_API_KEY={cfg.get('OPENAI_API_KEY', '')}",
        f"OPENAI_MODEL={cfg.get('OPENAI_MODEL', 'gpt-4o')}",
        f"ANTHROPIC_API_KEY={cfg.get('ANTHROPIC_API_KEY', '')}",
        f"ANTHROPIC_MODEL={cfg.get('ANTHROPIC_MODEL', 'claude-3-5-sonnet-latest')}",
        f"GEMINI_API_KEY={cfg.get('GEMINI_API_KEY', '')}",
        f"GEMINI_MODEL={cfg.get('GEMINI_MODEL', 'gemini-2.0-flash')}",
        "",
        "# ── Channels ─────────────────────────────",
        f"ENABLED_CHANNELS={cfg['ENABLED_CHANNELS']}",
        "",
        "# ── Telegram ─────────────────────────────",
        f"TELEGRAM_BOT_TOKEN={cfg.get('TELEGRAM_BOT_TOKEN', '')}",
        f"ALLOWED_USER_IDS={cfg.get('ALLOWED_USER_IDS', '')}",
        "",
        "# ── Memory ───────────────────────────────",
        f"DATABASE_URL={cfg.get('DATABASE_URL', 'sqlite:///openchiken.db')}",
        "",
        "# ── Scheduler ────────────────────────────",
        f"MORNING_BRIEFING_HOUR={cfg.get('MORNING_BRIEFING_HOUR', '8')}",
        f"REMINDER_MINUTES_BEFORE={cfg.get('REMINDER_MINUTES_BEFORE', '15')}",
        "",
        "# ── Skills ───────────────────────────────",
        f"ENABLED_SKILLS={cfg.get('ENABLED_SKILLS', 'all')}",
    ]

    if cfg.get("SLACK_BOT_TOKEN"):
        lines += [
            "",
            "# ── Slack ────────────────────────────────",
            f"SLACK_BOT_TOKEN={cfg['SLACK_BOT_TOKEN']}",
            f"SLACK_APP_TOKEN={cfg.get('SLACK_APP_TOKEN', '')}",
        ]

    if cfg.get("DISCORD_BOT_TOKEN"):
        lines += [
            "",
            "# ── Discord ──────────────────────────────",
            f"DISCORD_BOT_TOKEN={cfg['DISCORD_BOT_TOKEN']}",
        ]

    if cfg.get("IMESSAGE_POLL_INTERVAL"):
        lines += [
            "",
            "# ── iMessage (macOS) ─────────────────────",
            f"IMESSAGE_ALLOWED_HANDLES={cfg.get('IMESSAGE_ALLOWED_HANDLES', '')}",
            f"IMESSAGE_POLL_INTERVAL={cfg['IMESSAGE_POLL_INTERVAL']}",
        ]

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok(f".env 파일 저장 완료 → {ENV_FILE}")
    return True


# ── 실행 검증 ──────────────────────────────────────────────
def verify_setup():
    console.print()
    console.print(Rule("[bold cyan]환경 검증[/]", style="cyan dim"))
    console.print()

    checks = [
        ("Python 버전", lambda: sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}"),
        (".env 파일", lambda: ENV_FILE.exists(), str(ENV_FILE)),
        (
            "credentials.json",
            lambda: (ROOT / "credentials.json").exists(),
            "Google OAuth용 (선택)",
        ),
    ]

    all_ok = True
    for label, check_fn, detail in checks:
        try:
            passed = check_fn()
        except Exception:
            passed = False
        status = "[bold green]✓[/]" if passed else "[bold yellow]–[/]"
        console.print(f"  {status}  [bold]{label}[/]  [dim]{detail}[/]")
        if not passed and label != "credentials.json":
            all_ok = False

    return all_ok


# ── 완료 화면 ──────────────────────────────────────────────
def print_done():
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "\n"
                "  [bold cyan]OpenChiken 세팅 완료!  🐔[/]\n\n"
                "  아래 명령으로 AI 비서를 시작하세요:\n\n"
                "  [bold]  openchiken[/]          (uv tool install 사용 시)\n"
                "  [bold]  uv run python main.py[/]  (git clone 개발 환경)\n\n"
                "  [dim]처음 실행 시 Google OAuth 인증을 위해 브라우저가 열립니다.[/]\n"
            ),
            border_style="cyan",
            padding=(0, 2),
        )
    )
    console.print()
    console.print("  [dim]문제가 생기면 .env 파일을 직접 수정하거나[/]")
    console.print("  [dim]  openchiken-setup  또는  uv run python setup_wizard.py  를 다시 실행하세요.[/]")
    console.print()


# ── 진입점 ──────────────────────────────────────────────────
def main():
    console.clear()

    # 타이틀 배너
    console.print()
    console.print(
        Panel(
            Text.from_markup(
                "\n"
                "  [bold cyan] ██████╗ ██████╗ ███████╗███╗   ██╗[/]\n"
                "  [bold cyan]██╔═══██╗██╔══██╗██╔════╝████╗  ██║[/]\n"
                "  [bold cyan]██║   ██║██████╔╝█████╗  ██╔██╗ ██║[/]\n"
                "  [bold cyan]██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║[/]\n"
                "  [bold cyan]╚██████╔╝██║     ███████╗██║ ╚████║[/]\n"
                "  [bold cyan] ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝[/]\n"
                "  [bold white]  C H I K E N  —  자율 AI 비서 에이전트[/]\n"
                "  [dim]  Setup Wizard  v0.1[/]\n"
            ),
            border_style="cyan dim",
            padding=(0, 1),
        )
    )

    console.print()
    console.print("  이 위저드는 [bold cyan]6단계[/]에 걸쳐 AI 비서를 세팅합니다.")
    console.print()
    _step_map = [
        ("1", "페르소나"),
        ("2", "LLM 설정"),
        ("3", "채널 설정"),
        ("4", "메모리"),
        ("5", "앱 설정"),
        ("6", "Chrome Extension"),
    ]
    for num, title in _step_map:
        console.print(f"  [dim]Step {num}[/]  {title}")
    console.print()
    console.print("  언제든 [bold]Ctrl+C[/] 로 중단할 수 있습니다.")
    console.print()

    if not confirm("시작하시겠습니까?", default=True):
        console.print("\n  [yellow]취소되었습니다.[/]\n")
        return

    cfg: dict = {}

    try:
        collect_persona(cfg)
        collect_llm(cfg)
        collect_channels(cfg)
        collect_memory(cfg)
        collect_app_settings(cfg)
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n  [yellow]설정이 중단되었습니다.[/]\n")
        return

    saved = write_env(cfg)
    if not saved:
        return

    # .env 저장 후 Extension 설치 (네트워크 연결 확인이 필요하므로 후반에 배치)
    try:
        collect_extension(cfg)
    except (KeyboardInterrupt, EOFError):
        warn("Extension 설치가 중단되었습니다. 나중에 수동 설치 가능합니다.")

    ok_all = verify_setup()
    print_done()

    if ok_all and confirm("지금 바로 OpenChiken을 시작하시겠습니까?", default=False):
        console.print()
        console.print(Rule("[bold cyan]OpenChiken 시작[/]", style="cyan dim"))
        console.print()
        if shutil.which("openchiken"):
            os.execvp("openchiken", ["openchiken"])
        elif (ROOT / "main.py").exists():
            os.execvp("uv", ["uv", "run", "python", str(ROOT / "main.py")])
        else:
            from main import main as run_main
            run_main()


if __name__ == "__main__":
    main()
