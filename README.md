# OpenChiken — 자율 AI 비서 에이전트

Telegram · Slack · Discord를 통해 명령을 받고, OpenAI GPT-4o로 추론하며, Gmail · Google Calendar · 웹 검색 · 날씨 · 메모를 통합 관리하는 개인 AI 비서입니다.
복잡한 다단계 작업은 Plan-and-Execute 엔진이 스스로 계획하고 실행하며, 스케줄러를 통해 능동적으로 알림을 보냅니다.

---

## 기능 요약

| 카테고리 | 기능 |
|----------|------|
| **이메일** | Gmail 검색 · 읽기 · 전송 |
| **캘린더** | 오늘/향후 일정 조회 · 생성 · 삭제 |
| **웹 검색** | DuckDuckGo 실시간 검색 (API 키 불필요) |
| **날씨** | 현재 날씨 · N일 예보 (Open-Meteo, 무료) |
| **메모** | SQLite 기반 메모 저장 · 조회 · 삭제 |
| **작업 큐** | 복잡한 작업 진행 상황 추적 |
| **스케줄러** | 아침 브리핑 · 일정 리마인더 · 주간 브리핑 자동 전송 |
| **Plan-and-Execute** | 복잡한 요청을 단계별로 분해 · 자동 실행 |
| **대화 기억** | SQLite 기반 세션 간 대화 기록 유지 |
| **스킬 시스템** | SKILL.md 기반 동적 스킬 로딩 · 사용자 커스텀 스킬 추가 가능 |
| **Slack 연동** | Slack DM · 채널 멘션으로 AI 비서 사용 (Socket Mode) |
| **Discord 연동** | Discord DM · 서버 채널 멘션으로 AI 비서 사용 |
| **스킬 선택** | 위저드에서 사용할 스킬 선택 가능 (기본: 전체 활성화) |
| **보안** | 허용된 사용자 ID만 접근 가능 |

---

## 저장소 구성 (역할)

| 경로 | 용도 |
|------|------|
| **`landing/`** | 공개 **랜딩 페이지**만 (별도 도메인에 정적 배포). 온보딩·대시보드 없음. |
| **`local-ui/`** | PC에서 `server.py`로 띄울 때 제공하는 **로컬 온보딩 + 관리 화면** (setup, dashboard 등). |
| **`static/`** | 랜딩과 로컬 UI가 공유하는 **CSS · JS · 로고** (`/static/...` 로 서빙). |
| **`docs/quickstart.md`** | 처음 쓰는 사람·기여자용 **설치 → 실행 → 로컬 웹** 단계 요약. |

브라우저로 **공개 사이트**만 볼 때는 `landing/`만 호스팅하면 되고, **`uv run python server.py`**(또는 `openchiken-web`)로 뜨는 주소는 `local-ui/` + `static/`만 사용합니다.

---

## Quick Start

1. [설치 (uv tool install)](#설치-권장-uv-tool-install) — 아래 절차대로 `openchiken` 설치  
2. **`openchiken-setup`** (CLI) 또는 로컬 웹 위저드 — [`docs/quickstart.md`](docs/quickstart.md) 참고  
3. **`uv run python server.py`** — 브라우저에서 `http://localhost:8000` → 온보딩(`setup.html`)으로 연결  
4. 설정 완료 후 같은 주소에서 대시보드 등 **로컬 관리 UI** 사용  
5. **`openchiken`** 실행 후 Telegram · Slack · Discord 등에서 대화  

자세한 단계와 폴더 역할은 **[docs/quickstart.md](docs/quickstart.md)** 를 봅니다.

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

설치 후 두 개의 명령어가 전역으로 사용 가능해집니다:

| 명령어 | 설명 |
|--------|------|
| `openchiken-setup` | 초기 설정 위저드 실행 |
| `openchiken` | AI 비서 봇 실행 |

---

## 초기 설정

```bash
openchiken-setup
```

위저드가 다음 9단계를 안내합니다:

1. **AI 비서 페르소나** — 이름 · 말투 · 성격 설정
2. **OpenAI API Key** — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)에서 발급
3. **Telegram Bot Token** — [@BotFather](https://t.me/BotFather)에서 `/newbot`으로 생성
4. **Google API 설정** — Gmail · Calendar 연동 (아래 상세 안내 참고)
5. **데이터베이스** — SQLite 저장 경로 설정
6. **스케줄러** — 아침 브리핑 시각, 리마인더 타이밍 설정
7. **스킬 선택** — 사용할 스킬 선택 (기본: 전체 활성화)
8. **Slack 연동** — Slack Bot Token · App-Level Token 입력 (선택)
9. **Discord 연동** — Discord Bot Token 입력 (선택)
10. **추가 채널** — 설정 완료 안내

설정 파일은 `~/.openchiken/.env`에 저장됩니다.

---

## Google API 설정 (Gmail + Calendar)

> Gmail과 Google Calendar 기능을 사용하려면 본인의 GCP 계정에서 OAuth 클라이언트를 발급해야 합니다.
> **이 과정은 1회만 하면 됩니다.** `openchiken-setup` 위저드가 단계별로 안내합니다.

### 설정 개요

1. [Google Cloud Console](https://console.cloud.google.com/projectcreate)에서 프로젝트 생성
2. Gmail API + Google Calendar API 활성화
3. OAuth 동의 화면 구성 → **테스트 사용자에 본인(및 사용하게 할 사람) Gmail 추가**
4. OAuth 2.0 클라이언트 ID (데스크톱 앱) 생성 → `credentials.json` 다운로드
5. 파일을 `~/.openchiken/credentials.json`에 배치
6. 첫 `openchiken` 실행 시 브라우저가 열려 Google 계정 로그인 → 자동으로 `token.json` 저장

### 테스트 사용자 제한

Google OAuth 동의 화면이 **테스트 모드**인 경우, 등록된 테스트 사용자만 Gmail/Calendar 기능을 사용할 수 있습니다.

- 본인 계정은 반드시 테스트 사용자로 추가해야 합니다.
- 다른 사람에게 공유하려면 GCP Console → OAuth 동의 화면 → 테스트 사용자에 이메일 추가
- 최대 100개 계정까지 무료로 추가 가능
- 불특정 다수에게 공개하려면 [Google 앱 검증](https://support.google.com/cloud/answer/9110914) 필요

> 위저드 실행 중 GCP 링크를 하나씩 열어 따라 하면 됩니다.

---

## Slack 연동 설정

> Slack DM 또는 채널 멘션으로 AI 비서를 사용할 수 있습니다. **Socket Mode** 방식이므로 서버 공개 IP 없이도 동작합니다.

### 1. Slack App 생성

[https://api.slack.com/apps](https://api.slack.com/apps) → **"Create New App"** → **"From scratch"**

- App Name: `OpenChiken` (원하는 이름)
- Workspace: 연동할 워크스페이스 선택

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
→ **"Subscribe to bot events"** 에 아래 두 개 추가:

- `message.im` — DM 메시지 수신
- `app_mention` — 채널 멘션 수신

### 5. App Home 설정

**App Home → Messages Tab** → **"Allow users to send Slash commands and messages from the messages tab"** 체크

### 6. 워크스페이스에 앱 설치

**OAuth & Permissions → "Install to Workspace"**  
→ 설치 완료 후 **Bot User OAuth Token** (`xoxb-...`) 복사

### 7. .env 설정

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

또는 `openchiken-setup` 위저드 **STEP 8**에서 입력하면 자동 저장됩니다.

### Slack 사용법

**DM**: 왼쪽 사이드바 **"Direct messages → +"** → 봇 이름 검색 → 메시지 전송

**채널**: `/invite @봇이름` 으로 초대 후 `@봇이름 안녕` 형식으로 멘션

| 입력 | 동작 |
|---|---|
| 일반 메시지 | AI 비서 응답 |
| `plan <요청>` | Plan-and-Execute 다단계 실행 |
| `clear` / `대화 초기화` | 대화 기록 초기화 |

---

## Discord 연동 설정

> Discord DM 또는 서버 채널 멘션으로 AI 비서를 사용할 수 있습니다.

### 1. Discord Application 생성

[https://discord.com/developers/applications](https://discord.com/developers/applications) → **"New Application"**

- Application Name: `OpenChiken` (원하는 이름)

### 2. Bot 생성 및 Token 복사

**Bot** 탭 → **"Add Bot"** → **"Reset Token"** → 토큰 복사

> Token은 한 번만 표시됩니다. 반드시 복사해 두세요.

### 3. Privileged Gateway Intents 설정

**Bot** 탭 → **"Privileged Gateway Intents"** 에서 아래 항목 활성화:

| Intent | 용도 |
|---|---|
| `Message Content Intent` | 메시지 본문 읽기 (필수) |

### 4. OAuth2 초대 URL 생성 및 서버 초대

**OAuth2 → URL Generator** 에서:

1. **Scopes**: `bot` 선택
2. **Bot Permissions** 에서 아래 권한 선택:

| 권한 | 용도 |
|---|---|
| `Send Messages` | 메시지 전송 |
| `Read Message History` | 메시지 읽기 |

3. 생성된 URL로 접속 → 봇을 원하는 서버에 초대

### 5. .env 설정

```env
DISCORD_BOT_TOKEN=your-discord-bot-token
ALLOWED_USER_IDS=123456789,987654321   # Discord User ID 추가 (기존 Telegram ID와 동일 필드)
```

또는 `openchiken-setup` 위저드 **STEP 9**에서 입력하면 자동 저장됩니다.

> **Discord User ID 확인 방법**: Discord 설정 → **고급** → **개발자 모드** 활성화 후, 자신의 프로필 우클릭 → **"ID 복사"**

### Discord 사용법

**DM**: 봇의 프로필 → **메시지 보내기** → 메시지 전송

**서버 채널**: `/invite @봇이름` 으로 초대 후 `@봇이름 안녕` 형식으로 멘션

| 입력 | 동작 |
|---|---|
| 일반 메시지 | AI 비서 응답 |
| `plan <요청>` | Plan-and-Execute 다단계 실행 |
| `clear` / `대화 초기화` | 대화 기록 초기화 |

---

## 스킬 선택 (ENABLED_SKILLS)

위저드 STEP 7에서 사용할 스킬을 선택할 수 있습니다. 기본값은 **전체 활성화**(`all`)입니다.

`.env`에서 직접 설정할 수도 있습니다:

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
Model : gpt-4o
Enabled skills: all
스케줄: 아침브리핑 08:00 / 리마인더 15분 전 / 주간브리핑 월 08:05
Slack bot (Socket Mode) starting in background thread...   ← Slack 설정 시
⚡️ Bolt app is running!                                    ← Slack 연결 완료
Discord bot starting...                                    ← Discord 설정 시
Discord bot online: OpenChiken#1234 (id=...)               ← Discord 연결 완료
Telegram bot polling started – press Ctrl+C to stop
```

---

## 스킬 시스템

OpenChiken은 **SKILL.md 기반 스킬 시스템**을 사용합니다 (OpenClaw/AgentSkills 호환).

### 스킬 구조

```
skills/
├── gmail/
│   ├── SKILL.md    ← AI 지시 + 메타데이터
│   └── tool.py     ← LangChain 도구 구현
├── calendar/
├── weather/
├── web_search/
├── memo/
└── task/
```

### 사용자 커스텀 스킬 추가

`~/.openchiken/skills/` 디렉토리에 스킬을 추가하면 자동으로 로드됩니다:

```bash
mkdir -p ~/.openchiken/skills/my_skill

# SKILL.md 작성
cat > ~/.openchiken/skills/my_skill/SKILL.md << 'EOF'
---
name: my_skill
description: 나만의 커스텀 스킬
enabled: true
---

## My Skill

사용 가능한 도구 및 사용법 설명...
EOF

# tool.py 작성 (선택사항 - LangChain 도구가 필요한 경우)
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

다음 번 `openchiken` 실행 시 자동으로 스킬이 로드됩니다.

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
| `이번 주 일정 보여줘` | 향후 7일 일정 조회 |
| `내일 오후 2시에 팀 회의 잡아줘` | 새 일정 생성 |
| `안 읽은 이메일 확인해줘` | Gmail 미읽은 이메일 검색 |
| `홍길동에게 회의록 보내줘` | Gmail 이메일 전송 |
| `서울 지금 날씨 어때?` | 현재 날씨 조회 |
| `이번 주 제주도 날씨 알려줘` | 5일 예보 조회 |
| `GPT-5 관련 최신 뉴스 알려줘` | 웹 검색 후 답변 |
| `내 이메일 서명 기억해줘` | 메모로 저장 |
| `/plan 미팅 관련 이메일 찾아서 요약하고 각각 답장 초안 작성해줘` | Plan-and-Execute 다단계 실행 |

---

## 프로젝트 구조

```
openchiken/
├── main.py                   # 진입점 (봇 + 스케줄러 시작)
├── server.py                 # 로컬 웹 서버 (local-ui + /static + 온보딩 API)
├── landing/                  # 공개 랜딩 (정적 배포 전용, 이 레포에서 소스 관리)
├── local-ui/                 # 로컬 온보딩·대시보드 HTML (FastAPI가 서빙)
├── static/                   # 공유 자산 (CSS, JS, assets/logo 등)
├── docs/
│   └── quickstart.md         # Quick Start 단계별 안내
├── config/
│   └── settings.py           # 환경변수 및 설정 (~/.openchiken 지원)
├── core/
│   ├── agent.py              # ReAct 에이전트 + SkillLoader 연동
│   ├── planner.py            # Plan-and-Execute LangGraph 그래프
│   ├── memory.py             # SQLite 대화 기록
│   └── google_auth.py        # Google OAuth2 인증
├── skills/                   # 스킬 시스템
│   ├── __init__.py           # SkillLoader (동적 스킬 로딩)
│   ├── gmail/
│   │   ├── SKILL.md          # AI 지시 + 메타데이터
│   │   └── tool.py           # LangChain 도구
│   ├── calendar/
│   ├── weather/
│   ├── web_search/
│   ├── memo/
│   └── task/
├── scheduler/
│   ├── jobs.py               # 스케줄 잡 (브리핑, 리마인더, 주간)
│   └── scheduler.py          # APScheduler 설정
├── channels/
│   ├── telegram_bot.py       # Telegram 봇 핸들러
│   ├── slack_bot.py          # Slack 봇 핸들러 (Socket Mode)
│   └── discord_bot.py        # Discord 봇 핸들러
├── setup.py                  # 설치 위저드 (openchiken-setup)
└── pyproject.toml            # 프로젝트 설정 (uv)
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
Telegram 메시지        Slack DM / 멘션           Discord DM / 멘션
      ↓                      ↓                         ↓
channels/telegram_bot  channels/slack_bot        channels/discord_bot
                       (Socket Mode, 백그라운드)   (비동기 클라이언트)
      ↓                      ↓                         ↓
  ┌─────────────────────────────────────────────┐
  │  일반 메시지 → core/agent.py (ReAct + SkillLoader) → 도구 호출 → 응답  │
  │  plan 명령   → core/planner.py (Plan-and-Execute)                    │
  │                   Planner → Executor → Replanner → 최종 응답          │
  └─────────────────────────────────────────────┘

스킬 시스템 (SkillLoader)
  ENABLED_SKILLS=all           → 모든 스킬 로드 (기본값)
  ENABLED_SKILLS=gmail,weather → 선택된 스킬만 로드
  skills/{name}/SKILL.md       → AI 시스템 프롬프트에 지시 텍스트 주입
  skills/{name}/tool.py        → LangChain @tool 함수 동적 로딩
  ~/.openchiken/skills/        → 사용자 설치 외부 스킬

자율 알림 (스케줄러)
  매일 08:00      → 아침 브리핑 (일정 + 이메일)
  매 5분          → 일정 리마인더 (15분 후 시작 일정)
  매주 월 08:05   → 주간 브리핑
```

---

## 향후 확장 계획

- 스킬 허브(ClawHub 유사) — 커뮤니티 스킬 등록 및 다운로드
- OpenClaw 스킬 호환 레이어 — 기존 OpenClaw SKILL.md 바로 사용
- Notion 연동 (회의록 자동 작성)
- Slack 스케줄러 브리핑 — 아침·주간 브리핑을 Slack 채널에도 자동 전송
- KakaoTalk · WhatsApp 채널 연동
- 파일 첨부 처리 (PDF · 이미지 요약)
- 음성 메시지 지원
