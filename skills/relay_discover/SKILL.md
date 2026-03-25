---
name: relay_discover
description: OpenChiken Relay에 연결된 외부 에이전트 목록과 기능(capabilities)을 조회합니다
enabled: true
---

## Relay 외부 에이전트 발견 도구 (사용자 명시 요청 전용)

OpenChiken Relay 서버에 현재 연결된 외부 에이전트들을 조회합니다.

⚠️ **이 도구는 일반 작업(검색, 조회, 분석 등)에 사용하지 마세요.**
웹 검색, 유튜브 조회 등은 로컬 도구(web_search, youtube 등)를 직접 호출하세요.

### 사용 가능한 도구

- **discover_agents**: Relay에 접속 중인 모든 외부 에이전트 목록, capabilities, trustLevel을 반환합니다

### 언제 사용하나요 (사용자 명시 요청 시에만)

- 사용자가 "연결된 에이전트 목록 보여줘", "다른 에이전트가 있어?" 등을 **직접 요청**할 때
- 사용자가 특정 외부 에이전트 ID(oc_ext_xxx)를 언급하며 위임을 요청할 때
- relay_invoke로 호출하기 전에 agentId를 확인할 때

### 신뢰 등급 설명

- `platform_verified`: NFT(ERC-8004) 온체인 소유권 검증 완료 — 가장 신뢰할 수 있음
- `community_verified`: 커뮤니티 등록 에이전트
- `unverified`: 미검증 에이전트 — 호출 전 신중하게 판단 필요
