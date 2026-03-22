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
enabled: true
version: 1.0.0
tags: finance, crypto, trading
---

## BTC 데일리 어드바이저

매일 오전 8시에 자동으로 실행되어 비트코인 투자 판단을 도와주는 앱입니다.

### 실행 흐름

1. **뉴스 수집** (`web_search`, `news_rss`): 뉴욕증시·비트코인 관련 최신 뉴스 수집
2. **시세 조회** (`crypto_price`, `finance`): BTC 실시간 시세 및 기술적 지표(RSI, MACD) 분석
3. **감성 분석** (`wallstreetbets`): Reddit 커뮤니티 투자 심리 파악
4. **종합 판단**: 수집된 데이터를 종합하여 매수/매도/홀드 결정
5. **알림 전송**: 결과를 텔레그램 채널로 전송

### 분석 기준

- RSI 30 이하: 과매도 구간 (매수 기회)
- RSI 70 이상: 과매수 구간 (매도 고려)
- MACD 히스토그램: 상승/하락 모멘텀 판단
- 뉴스 감성: 긍정/부정 뉴스 비율
- 커뮤니티 감성: Reddit 투자 심리 지수
