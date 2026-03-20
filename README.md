Telegram · Slack · Discord · iMessage를 통해 명령을 받고, OpenAI / Anthropic / Gemini LLM으로 추론하며, Gmail · Google Calendar · Drive · Docs · Sheets · 웹 검색 · 날씨 · 메모를 통합 관리하는 개인 AI 비서입니다.
복잡한 다단계 작업은 Plan-and-Execute 엔진이 스스로 계획하고 실행하며, 스케줄러를 통해 능동적으로 알림을 보냅니다.

---

## 기능 요약

| 카테고리 | 기능 |
|----------|------|
| **이메일** | Gmail 검색 · 읽기 · 전송 |
| **캘린더** | 오늘/향후 일정 조회 · 생성 · 삭제 |
| **Drive** | Google Drive 파일 조회 · 검색 · 업로드 · 폴더 관리 |
| **Docs** | Google Docs 읽기 · 생성 · 내용 추가 |
| **Sheets** | Google Sheets 읽기 · 쓰기 · 행 추가 · 생성 |
| **Workflow** | 스탠드업 보고 · 주간 요약 · 미팅 준비 등 복합 업무 자동화 |
| **웹 검색** | DuckDuckGo 실시간 검색 (API 키 불필요) |
| **날씨** | 현재 날씨 · N일 예보 (Open-Meteo, 무료) |
| **메모** | SQLite 기반 메모 저장 · 조회 · 삭제 |
| **작업 큐** | 복잡한 작업 진행 상황 추적 |
| **Finance** | 주식 · 암호화폐 시세 및 기술적 분석 |
| **스케줄러** | 아침 브리핑 · 일정 리마인더 · 주간 브리핑 자동 전송 |
| **Plan-and-Execute** | 복잡한 요청을 단계별로 분해 · 자동 실행 |
| **대화 기억** | SQLite 기반 세션 간 대화 기록 유지 |
| **스킬 시스템** | SKILL.md 기반 동적 스킬 로딩 · 사용자 커스텀 스킬 추가 가능 |
| **다중 LLM** | OpenAI · Anthropic(Claude) · Gemini 중 선택 |
| **보안** | 허용된 사용자 ID만 접근 가능 |

---

## 저장소 구성

| 경로 | 용도 |
|------|------|
| **`landing/`** | 공개 **랜딩 페이지** (별도 도메인에 정적 배포) |
| **`local_ui/`** | PC에서 `server.py`로 띄우는 **로컬 온보딩 + 관리 화면** |
| **`static/`** | 랜딩과 로컬 UI가 공유하는 CSS · JS · 로고 |
| **`docs/quickstart.md`** | 설치 → 실행 단계 요약 |

---

## Quick Start

1. [설치 (uv tool install)](#설치-권장-uv-tool-install)
2. **`openchiken-setup`** — 초기 설정 위저드 실행
3. **`openchiken`** — 봇 실행 후 Telegram · Slack · Discord 등에서 대화

자세한 단계는 **[docs/quickstart.md](docs/quickstart.md)** 를 참고하세요.

---

## 설치 (권장: uv tool install)

> **사전 요구사항**: Python 3.11 이상, [uv](https://docs.astral.sh/uv/) 설치

```bash
# uv 설치 (아직 없다면)
curl -LsSf https://astral.sh/uv/install.sh | sh

# OpenChiken 설치 (git clone 불필요)
uv tool install git+https://github.com/YOUR_USERNAME/openchiken.git

# 설치 확인
openchiken --help
```

| 명령어 | 설명 |
|--------|------|
| `openchiken-setup` | 초기 설정 위저드 실행 |
| `openchiken` | AI 비서 봇 실행 |
| `openchiken-web` | 로컬 관리 웹 서버 실행 |

---

## 초기 설정

```bash
openchiken-setup
```

위저드는 **5단계**로 진행됩니다:

1. **페르소나 설정** — 비서 이름 · 말투 · 성격 설정
2. **LLM 설정** — OpenAI / Anthropic / Gemini 선택 및 API Key 입력
3. **채널 설정** — Telegram · Slack · Discord · iMessage 활성화 및 각 토큰 입력
   - Telegram: [@BotFather](https://t.me/BotFather)에서 `/newbot`으로 생성한 Bot Token
   - Slack: Bot Token (`xoxb-...`) + App-Level Token (`xapp-...`) 입력 (선택)
   - Discord: Bot Token 입력 (선택)
   - iMessage: macOS 전용, 별도 API 키 불필요 (선택)
4. **메모리 설정** — SQLite 저장 경로 설정
5. **앱 설정** — Google 연동 (Gmail · Calendar · Drive · Docs · Sheets) · 스케줄러 타이밍 · 스킬 선택
   - Google 연동은 이 단계에서 `credentials.json` 배치 + OAuth 인증까지 완료 가능
   - 아침 브리핑 시각 · 일정 리마인더 발송 시점 설정
   - 활성화할 스킬 선택 (기본: 전체 활성화)

설정 파일은 `~/.openchiken/.env`에 저장됩니다.

---

## LLM 공급자 설정

`.env`에서 LLM 공급자를 선택할 수 있습니다:

```env
# OpenAI (기본값)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Anthropic (Claude)
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest

# Google Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash
```

---

## Google API 설정 (Gmail + Calendar + Drive + Docs + Sheets)

> Gmail, Google Calendar, Drive, Docs, Sheets 기능을 사용하려면 GCP 계정에서 OAuth 클라이언트를 발급해야 합니다.
> **이 과정은 1회만 하면 됩니다.** `openchiken-setup` 위저드 Step 5에서 단계별로 안내합니다.
>
> `gcloud` CLI가 설치되어 있으면 프로젝트 생성과 API 활성화를 **자동**으로 진행합니다.

### G-1. Google Cloud 프로젝트 생성

[Google Cloud Console](https://console.cloud.google.com/projectcreate)에서 프로젝트 생성
(또는 `gcloud` CLI 설치 시 위저드가 자동으로 생성)

### G-2. API 5종 활성화

아래 API를 모두 활성화합니다 (`gcloud` 사용 시 자동 처리):

- [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
- [Google Calendar API](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
- [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
- [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
- [Google Docs API](https://console.cloud.google.com/apis/library/docs.googleapis.com)

### G-3. OAuth 동의 화면 구성 (수동 필수)

**OAuth & Permissions → 동의 화면** 에서:
1. User Type: **외부** → 만들기
2. 앱 이름: `OpenChiken`, 이메일: 본인 Gmail 입력 후 저장
3. **테스트 사용자 → + 사용자 추가 → 본인 Gmail 입력** (필수)

> **테스트 사용자 등록은 반드시 필요합니다.** 등록되지 않은 계정은 'Access blocked' 오류가 발생합니다.
> Google 앱 검증 전까지 최대 100개 계정까지 무료로 등록 가능합니다.

### G-4. OAuth 2.0 클라이언트 ID 생성 및 credentials.json 배치

1. **사용자 인증 정보 → + 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
2. 애플리케이션 유형: **데스크톱 앱**, 이름: `openchiken-desktop`
3. **JSON 다운로드** 클릭 → `~/Downloads`에 저장

> 위저드가 `~/Downloads` 폴더를 자동 감지하여 `~/.openchiken/credentials.json`으로 복사합니다.
> 자동 감지가 되지 않으면 직접 `~/.openchiken/credentials.json`에 파일을 배치하세요.

### G-5. Google 계정 인증 (token.json 저장)

위저드 Step 5에서 즉시 브라우저 로그인을 진행하거나, 나중에 첫 `openchiken` 실행 시 자동으로 브라우저가 열립니다.

> **"Google이 이 앱을 확인하지 않았습니다" 화면이 나오면:**
> **고급** 클릭 → **OpenChiken으로 이동(안전하지 않음)** 클릭
>
> 개인용 OAuth 앱의 정상적인 동작입니다. 테스트 사용자로 등록된 계정만 진행할 수 있습니다.

인증 완료 후 `~/.openchiken/token.json`이 자동 저장되며, 이후 재인증 없이 Google 스킬을 사용할 수 있습니다.

---

## 채널 설정 (ENABLED_CHANNELS)

`.env`에서 활성화할 채널을 선택합니다:

```env
# 기본값 (Telegram만 활성화)
ENABLED_CHANNELS=telegram

# 복수 채널 활성화
ENABLED_CHANNELS=telegram,slack,discord,imessage
```

| 채널 | 설명 |
|------|------|
| `telegram` | Telegram 봇 (기본) |
| `slack` | Slack DM · 채널 멘션 (Socket Mode) |
| `discord` | Discord DM · 서버 채널 멘션 |
| `imessage` | macOS iMessage (macOS 전용) |

---

## Slack 연동 설정

> **Socket Mode** 방식이므로 서버 공개 IP 없이도 동작합니다.

### 1. Slack App 생성

[https://api.slack.com/apps](https://api.slack.com/apps) → **"Create New App"** → **"From scratch"**

### 2. Bot Token Scopes 추가

**OAuth & Permissions → Bot Token Scopes** 에 아래 추가:

| Scope | 용도 |
|---|---|
| `app_mentions:read` | 채널 멘션 수신 |
| `chat:write` | 메시지 전송 |
| `im:history` | DM 읽기 |
| `im:read` | DM 수신 |
| `im:write` | DM 전송 |

### 3. Socket Mode 활성화 및 App-Level Token 발급

**Settings → Socket Mode** → **"Enable Socket Mode"** 토글 ON  
→ Token Name 입력 후 **"Generate"** → `xapp-...` 토큰 복사

### 4. Event Subscriptions 설정

**Event Subscriptions** → **"Enable Events"** ON  
→ **"Subscribe to bot events"** 에 추가: `message.im`, `app_mention`

### 5. 워크스페이스에 앱 설치

**OAuth & Permissions → "Install to Workspace"** → **Bot User OAuth Token** (`xoxb-...`) 복사

### 6. .env 설정

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

---

## Discord 연동 설정

### 1. Discord Application 생성

[https://discord.com/developers/applications](https://discord.com/developers/applications) → **"New Application"**

### 2. Bot 생성 및 설정

**Bot** 탭 → **"Add Bot"** → **"Reset Token"** → 토큰 복사

**Privileged Gateway Intents** → `Message Content Intent` 활성화

### 3. 서버 초대

**OAuth2 → URL Generator** → Scopes: `bot` → Bot Permissions: `Send Messages`, `Read Message History` → 생성된 URL로 서버 초대

### 4. .env 설정

```env
DISCORD_BOT_TOKEN=your-discord-bot-token
ALLOWED_USER_IDS=123456789,987654321
```

> **Discord User ID 확인**: 설정 → 고급 → 개발자 모드 활성화 후 프로필 우클릭 → **"ID 복사"**

---

## iMessage 연동 설정 (macOS 전용)

> macOS Messages.app + AppleScript 기반으로 iMessage를 통해 AI 비서를 사용할 수 있습니다.

**사전 조건:**
- macOS 12 Monterey 이상
- 시스템 설정 → 개인정보 보호 및 보안 → **전체 디스크 접근**에 Python(또는 터미널) 권한 부여
- Messages.app 로그인 상태 유지

```env
ENABLED_CHANNELS=telegram,imessage
IMESSAGE_ALLOWED_HANDLES=+821012345678,user@example.com  # 허용 핸들 (미설정 시 전체 허용)
IMESSAGE_POLL_INTERVAL=3                                 # 폴링 간격(초)
```

---

## 스킬 선택 (ENABLED_SKILLS)

`.env`에서 직접 설정할 수 있습니다:

```env
# 전체 활성화 (기본값)
ENABLED_SKILLS=all

# 특정 스킬만 활성화
ENABLED_SKILLS=gmail,calendar,weather
```

| 스킬 이름 | 설명 |
|---|---|
| `gmail` | Gmail 검색 · 읽기 · 전송 |
| `calendar` | Google Calendar 조회 · 생성 · 삭제 |
| `drive` | Google Drive 파일 조회 · 검색 · 업로드 · 폴더 관리 |
| `docs` | Google Docs 읽기 · 생성 · 내용 추가 |
| `sheets` | Google Sheets 읽기 · 쓰기 · 행 추가 · 생성 |
| `workflow` | 스탠드업 보고 · 주간 요약 · 미팅 준비 등 복합 업무 자동화 |
| `weather` | 현재 날씨 · N일 예보 |
| `web_search` | DuckDuckGo 실시간 검색 |
| `memo` | SQLite 메모 저장 · 조회 · 삭제 |
| `task` | 복잡한 작업 진행 상황 추적 |
| `finance` | 주식 · 암호화폐 시세 및 기술적 분석 |

---

## 실행

```bash
openchiken
```

정상 실행 시:

```
=== OpenChiken AI 비서 시작 ===
LLM provider : openai / model : gpt-4o
Enabled skills: all
Enabled channels: ['telegram', 'slack']
스케줄: 아침브리핑 08:00 / 리마인더 15분 전 / 주간브리핑 월 08:05
Slack bot (Socket Mode) starting in background thread...
⚡️ Bolt app is running!
Telegram bot polling started – press Ctrl+C to stop
```

---

## 스킬 시스템

OpenChiken은 **SKILL.md 기반 스킬 시스템**을 사용합니다.

### 스킬 구조

```
skills/
├── gmail/
│   ├── SKILL.md    ← AI 지시 + 메타데이터
│   └── tool.py     ← LangChain 도구 구현
├── calendar/
├── drive/
├── docs/
├── sheets/
├── workflow/
├── weather/
├── web_search/
├── memo/
├── task/
└── finance/
```

### 사용자 커스텀 스킬 추가

`~/.openchiken/skills/` 디렉토리에 스킬을 추가하면 자동으로 로드됩니다:

```bash
mkdir -p ~/.openchiken/skills/my_skill

cat > ~/.openchiken/skills/my_skill/SKILL.md << 'EOF'
---
name: my_skill
description: 나만의 커스텀 스킬
enabled: true
---

## My Skill

사용 가능한 도구 및 사용법 설명...
EOF

cat > ~/.openchiken/skills/my_skill/tool.py << 'EOF'
from langchain_core.tools import tool

@tool
def my_custom_tool(query: str) -> str:
    """커스텀 도구 설명"""
    return f"결과: {query}"

def get_tools():
    return [my_custom_tool]
EOF
```

---

## Telegram 명령어

| 명령어 | 설명 |
|--------|------|
| `/start` | 시작 메시지 및 기능 안내 |
| `/clear` | 대화 기록 초기화 |
| `/briefing` | 지금 바로 아침 브리핑 (오늘 일정 + 미읽은 이메일) |
| `/weekly` | 이번 주 일정 브리핑 |
| `/plan <요청>` | 복잡한 작업을 단계별로 계획·실행 |
| `/tasks` | 진행 중인 작업 목록 확인 |

---

## 사용 예시

| 입력 | 동작 |
|------|------|
| `오늘 일정 알려줘` | Google Calendar에서 오늘 일정 조회 |
| `안 읽은 이메일 확인해줘` | Gmail 미읽은 이메일 검색 |
| `홍길동에게 회의록 보내줘` | Gmail 이메일 전송 |
| `서울 지금 날씨 어때?` | 현재 날씨 조회 |
| `GPT-5 관련 최신 뉴스 알려줘` | 웹 검색 후 답변 |
| `내 Drive에서 기획서 찾아줘` | Google Drive 파일 검색 |
| `스탠드업 보고 준비해줘` | workflow_standup_report 실행 |
| `/plan 미팅 관련 이메일 찾아서 요약하고 각각 답장 초안 작성해줘` | Plan-and-Execute 다단계 실행 |

---

## 프로젝트 구조

```
openchiken/
├── main.py                   # 진입점 (봇 + 스케줄러 시작)
├── server.py                 # 로컬 웹 서버 (local_ui + /static + 온보딩 API)
├── landing/                  # 공개 랜딩 (정적 배포 전용)
├── local_ui/                 # 로컬 온보딩·대시보드 HTML
├── static/                   # 공유 자산 (CSS, JS, assets/logo 등)
├── docs/
│   └── quickstart.md
├── config/
│   └── settings.py           # 환경변수 및 설정
├── core/
│   ├── agent.py              # ReAct 에이전트 + SkillLoader 연동
│   ├── planner.py            # Plan-and-Execute LangGraph 그래프
│   ├── memory.py             # SQLite 대화 기록
│   ├── provider.py           # LLM 공급자 추상화 (OpenAI/Anthropic/Gemini)
│   └── google_auth.py        # Google OAuth2 인증
├── skills/                   # 스킬 시스템
│   ├── __init__.py           # SkillLoader (동적 스킬 로딩)
│   ├── gmail/
│   ├── calendar/
│   ├── drive/
│   ├── docs/
│   ├── sheets/
│   ├── workflow/
│   ├── weather/
│   ├── web_search/
│   ├── memo/
│   ├── task/
│   └── finance/
├── scheduler/
│   ├── jobs.py               # 스케줄 잡 (브리핑, 리마인더, 주간)
│   └── scheduler.py          # APScheduler 설정
├── channels/
│   ├── base.py               # 채널 어댑터 기반 클래스
│   ├── router.py             # 채널 동적 로딩
│   ├── telegram_bot.py
│   ├── slack_bot.py          # Socket Mode
│   ├── discord_bot.py
│   └── imessage_bot.py       # macOS 전용
├── setup_wizard.py           # 설정 위저드 (openchiken-setup)
└── pyproject.toml
```

사용자 설정 파일 (`~/.openchiken/`):

```
~/.openchiken/
├── .env                      # API 키 및 설정값
├── credentials.json          # Google OAuth 클라이언트 (직접 배치)
├── token.json                # Google 액세스 토큰 (자동 생성)
└── skills/                   # 사용자 설치 커스텀 스킬
```

---

## 아키텍처

```
Telegram  Slack(Socket)  Discord  iMessage(macOS)
    ↓           ↓           ↓           ↓
channels/router.py  (채널 동적 로딩 · 어댑터 패턴)
    ↓
  일반 메시지 → core/agent.py (ReAct + SkillLoader)  → 도구 호출 → 응답
  plan 명령   → core/planner.py (Plan-and-Execute LangGraph)

스킬 시스템 (SkillLoader)
  ENABLED_SKILLS=all           → 모든 스킬 로드 (기본값)
  ENABLED_SKILLS=gmail,weather → 선택된 스킬만 로드
  skills/{name}/SKILL.md       → AI 시스템 프롬프트에 지시 텍스트 주입
  skills/{name}/tool.py        → LangChain @tool 함수 동적 로딩
  ~/.openchiken/skills/        → 사용자 설치 외부 스킬

LLM 공급자 (core/provider.py)
  LLM_PROVIDER=openai      → ChatOpenAI (gpt-4o 기본)
  LLM_PROVIDER=anthropic   → ChatAnthropic (claude-3-5-sonnet 기본)
  LLM_PROVIDER=gemini      → ChatGoogleGenerativeAI (gemini-2.0-flash 기본)

자율 알림 (스케줄러)
  매일 08:00      → 아침 브리핑 (일정 + 이메일)
  매 5분          → 일정 리마인더 (15분 후 시작 일정)
  매주 월 08:05   → 주간 브리핑
```

---

## 향후 확장 계획

- 스킬 허브 — 커뮤니티 스킬 등록 및 다운로드
- Notion 연동 (회의록 자동 작성)
- Slack 스케줄러 브리핑 — 아침·주간 브리핑을 Slack 채널에도 자동 전송
- KakaoTalk · WhatsApp 채널 연동
- 파일 첨부 처리 (PDF · 이미지 요약)
- 음성 메시지 지원
