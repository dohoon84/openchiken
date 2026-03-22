---
name: real_estate_scout
type: app
description: 부동산 매물 탐색, 지역 분석, 삶의 질 점수 리포트 생성
skills:
  - geocoding
  - quality_of_life
  - web_search
  - weather
  - quickchart
enabled: true
version: 1.0.0
tags: realestate, analysis, report
---

## 부동산 스카우트

관심 지역의 부동산 정보를 종합 분석하여 리포트를 생성하는 앱입니다.

### 실행 흐름

1. **지역 정보** (`geocoding`): 관심 지역의 좌표 및 행정구역 정보 조회
2. **삶의 질** (`quality_of_life`): 도시별 삶의 질 점수 (비용, 교통, 안전, 교육 등)
3. **매물 탐색** (`web_search`): 해당 지역 부동산 매물 및 시세 정보 검색
4. **날씨/환경** (`weather`): 지역 기후 데이터
5. **시각화** (`quickchart`): 분석 결과를 차트로 시각화

### 분석 항목

- 지역 기본 정보 (인구, 면적, 행정구역)
- 평균 매매가 / 전세가 / 월세
- 삶의 질 지수 (Teleport API 기반)
- 교통 접근성
- 기후 특성
- 종합 투자 매력도 점수
