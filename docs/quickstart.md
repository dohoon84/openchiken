# Quick Start — 단계별 안내

로컬 PC에서 OpenChiken을 처음 켤 때의 흐름입니다. 공개 랜딩(`landing/`)과는 별개로, **이 문서는 설치·실행·로컬 웹**에만 집중합니다.

## 1. 설치

- Python 3.11+, [uv](https://docs.astral.sh/uv/) 필요
- 저장소를 클론해 개발하거나, `uv tool install git+https://github.com/…` 로 도구만 설치할 수 있습니다.

```bash
uv tool install git+https://github.com/YOUR_USERNAME/openchiken.git
openchiken --help
```

## 2. 초기 설정 (택 1)

| 방법 | 명령 / 접속 | 비고 |
|------|-------------|------|
| **CLI 위저드** | `openchiken-setup` | 터미널에서 9단계 안내 |
| **로컬 웹 위저드** | 아래 3번에서 서버 실행 후 `/setup.html` | 브라우저 폼 + `~/.openchiken/.env` 저장 |

Google Gmail/Calendar를 쓰면 `credentials.json`을 `~/.openchiken/` 에 두는 과정이 필요합니다. 자세한 것은 루트 [README.md](../README.md) 의 Google API 절을 따릅니다.

## 3. 로컬 웹 서버 (온보딩 + 관리 UI)

저장소 루트에서:

```bash
uv run python server.py
```

기본 포트는 `8000` 입니다. 환경변수 `PORT`로 바꿀 수 있습니다.

- **`http://localhost:8000/`** → **`/setup.html`** 로 리다이렉트 (온보딩)
- 설정이 끝나면 **`/dashboard.html`** 등 **local_ui** 화면으로 이동합니다.

서빙되는 디렉터리 역할:

- **`local_ui/`** — setup, dashboard, tasks, skills, settings HTML
- **`static/`** — 공유 스타일·스크립트·로고 (`/static/...`)

## 4. 비서 실행 (채널)

```bash
openchiken
```

Telegram · Slack(설정 시) 등에서 메시지를 보내면 동작합니다.

## 폴더와 공개 사이트

| 경로 | 이 Quick Start와의 관계 |
|------|-------------------------|
| `landing/` | **포함되지 않음**. 공개 도메인 전용 정적 페이지 소스일 뿐입니다. |

랜딩만 배포할 때는 [landing/README.md](../landing/README.md) 를 참고하세요.
