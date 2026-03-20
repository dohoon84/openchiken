# OpenChiken 랜딩 (`landing/`)

공개 도메인(예: `openchiken.ai.kr`)에 올리는 **마케팅 페이지** 소스입니다.  
**온보딩·대시보드는 포함하지 않습니다.** (로컬에서는 `server.py` + `local_ui/` 를 사용합니다.)

## 정적 배포 시

이 폴더의 `index.html` 은 CSS/JS/로고를 **절대 경로** `/static/...` 로 읽습니다.  
호스팅 루트에 다음 구조가 되도록 **저장소 루트의 `static/` 디렉터리 전체**를 같이 올려 주세요.

```text
(사이트 루트)/
├── index.html          ← landing/index.html 내용
└── static/
    ├── shared.css
    ├── shared.js
    └── assets/
        └── logo.png
```

CDN이나 S3·Cloudflare Pages 등에서도 동일하게 `static` 을 그대로 두면 됩니다.

## 로컬에서 미리보기

`index.html` 이 `/static/...` 절대 경로를 쓰므로, **저장소 루트**에서 HTTP 서버를 띄운 뒤 아래처럼 접속합니다.

```bash
cd /path/to/openchiken
python -m http.server 8080
# 브라우저: http://localhost:8080/landing/index.html
```

배포 결과와 완전히 동일하게 보고 싶으면 임시 디렉터리에 `index.html` + `static/` 을 위의 [정적 배포 시](#정적-배포-시) 구조로 복사한 뒤 그폴더에서 `python -m http.server` 를 실행합니다.

## 링크

- 푸터의 GitHub URL 은 **`YOUR_USERNAME`** 을 실제 조직/사용자명으로 바꿉니다.
