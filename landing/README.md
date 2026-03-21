# OpenChiken 랜딩페이지 (`landing/`)

공개 도메인(`openchiken.ai.kr`)에 호스팅하는 마케팅 페이지입니다.  
온보딩·대시보드는 포함하지 않으며, 로컬 실행은 `server.py` + `local_ui/`를 사용합니다.

---

## 파일 구조

```
landing/
├── index.html
└── static/
    ├── shared.css
    ├── shared.js
    └── assets/
        └── logo.png
```

> `index.html`은 CSS/이미지를 `/static/...` 절대 경로로 참조합니다.  
> S3 업로드 시 **버킷 루트에 직접** 올려야 경로가 맞습니다. 서브폴더에 넣으면 CSS/이미지가 깨집니다.

---

## 로컬 미리보기

```bash
cd landing/
python3 -m http.server 8080
# 브라우저: http://localhost:8080
```

---

## AWS S3 + CloudFront 호스팅 가이드

### 전체 흐름

```
사용자 → Route 53 (DNS) → CloudFront (HTTPS + CDN) → S3 (파일)
                                    ↑
                              ACM (SSL 인증서)
```

---

### Step 1 — S3 버킷 생성

1. S3 → 버킷 만들기
2. 버킷 이름: `openchiken-landing-bucket`
3. 리전: `us-east-1` (버지니아) 권장
4. **퍼블릭 액세스 차단 해제** (모든 체크 해제)
5. 버킷 생성 후 **속성 탭 → 정적 웹사이트 호스팅 활성화**
   - 인덱스 문서: `index.html`

---

### Step 2 — 파일 업로드

버킷 루트에 직접 업로드:

```
openchiken-landing-bucket/
├── index.html
└── static/
    ├── shared.css
    ├── shared.js
    └── assets/
        └── logo.png
```

**버킷 정책 (권한 탭 → 버킷 정책):**

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::openchiken-landing-bucket/*"
        }
    ]
}
```

---

### Step 3 — ACM SSL 인증서 발급

> **반드시 `us-east-1` 리전에서 발급** (CloudFront는 us-east-1 인증서만 지원)

1. 리전을 `us-east-1`로 변경
2. Certificate Manager → 인증서 요청 → 퍼블릭 인증서
3. 도메인: `openchiken.ai.kr`
4. 검증 방법: DNS 검증
5. 발급된 CNAME을 가비아 DNS에 등록

```
타입:  CNAME
호스트: _f0022d2ada6e1473a28e05b0c607b9da.openchiken
값:    _5b12ebc9a5ea04970215b14fd5003fc4.jkddzztszm.acm-validations.aws.
```

6. ACM 상태가 **발급됨(Issued)** 될 때까지 대기 (5~20분)

> 이 CNAME은 1년 후 자동 갱신에도 필요하므로 삭제하지 말 것

---

### Step 4 — CloudFront 배포 생성

| 항목 | 값 |
|------|-----|
| Origin domain | `openchiken-landing-bucket.s3-website-us-east-1.amazonaws.com` **(직접 입력)** |
| Origin protocol | HTTP only |
| Viewer protocol policy | **Redirect HTTP to HTTPS** |
| Default root object | `index.html` |
| Alternate domain names (CNAME) | `openchiken.ai.kr` |
| SSL certificate | Step 3에서 발급한 인증서 선택 |

> Origin domain은 드롭다운 선택 말고 **직접 타이핑** 필수  
> 드롭다운 선택 시 REST 엔드포인트(`s3.amazonaws.com`)가 입력되어 Access Denied 발생

---

### Step 5 — DNS 연결

#### 방법 A — Route 53 (루트 도메인 `openchiken.ai.kr` 사용)

1. Route 53 → 호스팅 영역 생성 → `openchiken.ai.kr`
2. A 레코드 생성
   - Alias: ON
   - 대상: CloudFront 배포 선택 (`ddzl5h5i5sgi2.cloudfront.net`)
3. Route 53이 발급하는 네임서버 4개를 가비아에 입력
   - 가비아 → 도메인 관리 → 네임서버 변경

**비용:** Route 53 호스팅 영역 $0.50/월 (약 700원)

#### 방법 B — 가비아만 사용 (`www.openchiken.ai.kr` 사용)

가비아 DNS 설정:

```
타입:  CNAME
호스트: www
값:    ddzl5h5i5sgi2.cloudfront.net
```

루트 도메인도 연결하려면 가비아 **URL 포워딩**으로  
`openchiken.ai.kr` → `www.openchiken.ai.kr` 301 리다이렉션 설정

---

### Step 6 — 전파 확인

```bash
# 네임서버 확인
nslookup -type=NS openchiken.ai.kr

# 도메인 → CloudFront 연결 확인
nslookup openchiken.ai.kr
```

`awsdns` 네임서버 또는 CloudFront IP가 나오면 완료.  
전 세계 전파 현황: https://www.whatsmydns.net/#NS/openchiken.ai.kr

---

## 파일 업데이트 (배포 후)

AWS CLI 설치 후 아래 명령으로 S3 동기화:

```bash
aws s3 sync landing/ s3://openchiken-landing-bucket \
  --exclude "README.md" \
  --delete
```

CloudFront 캐시 초기화 (변경사항 즉시 반영):

```bash
aws cloudfront create-invalidation \
  --distribution-id E2I8C50A9QUN8Q \
  --paths "/*"
```

---

## 현재 배포 정보

| 항목 | 값 |
|------|-----|
| S3 버킷 | `openchiken-landing-bucket` (us-east-1) |
| CloudFront 배포 ID | `E2I8C50A9QUN8Q` |
| CloudFront 도메인 | `ddzl5h5i5sgi2.cloudfront.net` |
| 커스텀 도메인 | `openchiken.ai.kr` |
| DNS | Route 53 |
