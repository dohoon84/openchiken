---
name: btc_daily_advisor
type: app
description: 매일 오전 BTC/NYSE 뉴스 분석 후 매수/매도 판단 및 텔레그램 알림
skills:
  - web_search
  - crypto_price
  - news_rss
  - finance
  - wallstreetbets
schedule: "0 8 * * *"
trigger_keywords: 비트코인,BTC,btc,코인 분석,crypto,암호화폐
output_channel: telegram
enabled: true
version: 2.0.0
author: openchiken
tags: finance, crypto, trading
---

## BTC 데일리 어드바이저

매일 오전 8시에 자동으로 실행되어 비트코인 투자 판단을 도와주는 앱입니다.
텔레그램으로 `/run btc_daily_advisor` 명령으로 즉시 실행할 수도 있습니다.

### 실행 단계

1. web_search 도구로 "Bitcoin BTC 오늘 뉴스 site:coindesk.com OR site:cointelegraph.com" 쿼리를 사용해 최신 비트코인 뉴스 5건을 수집하라. 각 기사의 제목과 핵심 내용을 한 줄씩 요약하라.
2. news_rss 도구로 비트코인 관련 RSS 피드에서 오늘 기사를 3건 이상 수집하고 요약하라.
3. crypto_price 도구로 BTC/USDT 현재가, 24시간 변동률, 거래량을 조회하라.
4. finance 도구로 BTC의 RSI(14일), MACD, 볼린저밴드 기술적 지표를 조회하라. 지표 해석(과매수/과매도 여부)을 포함하라.
5. wallstreetbets 도구로 Reddit r/wallstreetbets 및 r/CryptoCurrency의 오늘 BTC 관련 게시물 감성을 파악하라. 긍정/부정 비율을 수치로 표시하라.
6. 1~5단계에서 수집한 모든 데이터를 종합하여 다음 형식으로 최종 투자 판단 리포트를 작성하라:
   [BTC 데일리 어드바이저 리포트]
   📊 현재가: {가격} | 24H 변동: {변동률}%
   📰 뉴스 감성: {긍정/부정/중립}
   📈 기술적 지표: RSI {수치} ({과매수/과매도/중립}) | MACD {방향}
   💬 커뮤니티 심리: {긍정 비율}% 긍정
   🎯 판단: {매수/매도/홀드} — {근거 2~3줄}

### 분석 기준

- RSI 30 이하: 과매도 구간 → 매수 기회
- RSI 70 이상: 과매수 구간 → 매도 고려
- MACD 히스토그램 양수 증가: 상승 모멘텀
- 뉴스 + 커뮤니티 감성 80% 이상 긍정: 강세 신호
- 복합 신호 불일치 시: 홀드 권장
