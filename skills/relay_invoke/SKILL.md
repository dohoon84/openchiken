---
name: relay_invoke
description: OpenChiken Relay를 통해 특정 외부 에이전트에게 작업을 위임하고 결과를 받습니다
enabled: true
---

## 외부 에이전트 호출 도구

OpenChiken Relay 서버를 통해 다른 에이전트에게 작업을 위임합니다.

### 사용 가능한 도구

- **invoke_agent**: 특정 agentId의 외부 에이전트에게 skill 실행을 요청하고 결과를 반환합니다

### 언제 사용하나요

- 사용자가 "oc_ext_xxx 에이전트한테 물어봐줘" 등을 요청할 때
- discover_agents로 찾은 에이전트에게 특정 작업을 위임할 때
- 내 로컬 스킬보다 외부 에이전트가 더 적합한 작업일 때

### 사용 흐름

1. discover_agents로 사용 가능한 에이전트와 agentId 확인
2. invoke_agent(agent_id, skill, params)로 호출
3. 상대방 에이전트가 승인하면 결과 반환 (최대 60초 대기)

### 주의사항

- `unverified` 에이전트 호출 시 상대방 정책에 의해 자동 거절될 수 있습니다
- 상대방 에이전트가 오프라인이면 404 오류가 반환됩니다
- 응답 시간은 상대방 에이전트의 처리 속도에 따라 다릅니다 (최대 60초)
