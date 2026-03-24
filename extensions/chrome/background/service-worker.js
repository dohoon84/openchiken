/**
 * OpenChiken Extension — Background Service Worker
 *
 * 역할:
 *   1. Relay Server에 WebSocket으로 상시 연결 (NAT 통과)
 *   2. 외부 에이전트 호출 수신 → Policy Engine 판단
 *   3. 자동 승인: localhost:8000 에 즉시 전달
 *   4. 수동 승인 필요 시: chrome.storage.session 에 저장 → 팝업 열면 복원
 *   5. 결과를 Relay Server로 반환
 *   6. 설치 시 에이전트 전용 Ethereum 지갑 자동 생성
 *
 * MV3 서비스 워커 생명주기 대응:
 *   - 승인 대기 요청은 chrome.storage.session 에 영속화
 *   - 서비스 워커 재시작 시 session storage 에서 복원
 *   - badge 는 Chrome 이 직접 관리하므로 재시작 후에도 유지됨
 */

import { Wallet } from './ethers.min.js';

// ─────────────── 설정 기본값 ───────────────

const DEFAULTS = {
  relayUrl:  'wss://openchiken-relay-production.up.railway.app/ws',
  serverUrl: 'http://localhost:8000',
  policy: {
    trustLevels: {
      platform_verified:  'auto_approve',
      community_verified: 'auto_approve',
      unverified:         'reject',
    },
    costThreshold:      0.01,
    requireApprovalFor: ['financial_or_legal'],
  },
};

// ─────────────── 휘발성 상태 ───────────────

let ws             = null;
let agentId        = null;
let agentAddress   = null;  // 에이전트 Ethereum 지갑 주소 (공개)
let tokenId        = null;
let relayUrl       = DEFAULTS.relayUrl;
let serverUrl      = DEFAULTS.serverUrl;
let policy         = DEFAULTS.policy;
let reconnectTimer = null;

// ─────────────── session storage 헬퍼 (승인 대기 영속화) ───────────────

async function sessionGetPending() {
  const { pendingApprovals = {} } = await chrome.storage.session.get('pendingApprovals');
  return pendingApprovals;
}

async function sessionSavePending(requestId, payload, caller) {
  const stored = await sessionGetPending();
  stored[requestId] = { payload, caller, savedAt: Date.now() };
  await chrome.storage.session.set({ pendingApprovals: stored });
}

async function sessionRemovePending(requestId) {
  const stored = await sessionGetPending();
  delete stored[requestId];
  await chrome.storage.session.set({ pendingApprovals: stored });
}

async function sessionFirstPending() {
  const stored = await sessionGetPending();
  const keys = Object.keys(stored);
  if (!keys.length) return null;
  const requestId = keys[0];
  return { requestId, ...stored[requestId] };
}

// ─────────────── 초기화 ───────────────

async function init() {
  const cfg = await chrome.storage.local.get(['agentId', 'agentAddress', 'tokenId', 'relayUrl', 'serverUrl', 'policy']);

  if (!cfg.agentId) {
    agentId = `oc_ext_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    await chrome.storage.local.set({ agentId });
  } else {
    agentId = cfg.agentId;
  }

  if (cfg.agentAddress) agentAddress = cfg.agentAddress;
  if (cfg.tokenId)      tokenId      = cfg.tokenId;
  if (cfg.relayUrl)     relayUrl     = cfg.relayUrl;
  if (cfg.serverUrl)    serverUrl    = cfg.serverUrl;
  if (cfg.policy)       policy       = { ...DEFAULTS.policy, ...cfg.policy };

  // 서비스 워커 재시작 후 대기 중인 승인이 있으면 badge 복원
  const firstPending = await sessionFirstPending();
  if (firstPending) {
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#F97316' });
    console.log('[Init] 대기 중인 승인 복원:', firstPending.requestId);
  }

  connectRelay();
}

// ─────────────── WebSocket 연결 ───────────────

function connectRelay() {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

  console.log(`[Relay] 연결 시도: ${relayUrl}`);
  ws = new WebSocket(relayUrl);

  ws.onopen = async () => {
    console.log('[Relay] 연결됨');
    clearTimeout(reconnectTimer);
    const registerMsg = { type: 'REGISTER', agentId, capabilities: ['browser_context', 'local_agent'], version: '0.2.0' };
    if (tokenId)      registerMsg.tokenId      = tokenId;
    if (agentAddress) registerMsg.agentAddress = agentAddress;
    send(registerMsg);
    notifyPopup({ type: 'RELAY_STATUS', status: 'connected', agentId });

    // 대기 중인 승인이 없을 때만 badge 초기화
    const pending = await sessionFirstPending();
    if (!pending) chrome.action.setBadgeText({ text: '' });
  };

  ws.onmessage = ({ data }) => {
    try { handleRelayMessage(JSON.parse(data)); }
    catch (e) { console.error('[Relay] 메시지 파싱 오류:', e); }
  };

  ws.onclose = () => {
    console.warn('[Relay] 연결 끊김 — 5초 후 재연결');
    notifyPopup({ type: 'RELAY_STATUS', status: 'disconnected' });
    reconnectTimer = setTimeout(connectRelay, 5_000);
  };

  ws.onerror = (e) => console.error('[Relay] 오류:', e.message ?? e);
}

function send(msg) {
  if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// ─────────────── 릴레이 메시지 처리 ───────────────

async function handleRelayMessage(msg) {
  switch (msg.type) {
    case 'REGISTERED':
      console.log('[Relay] 등록 확인:', msg.agentId);
      break;

    case 'ONCHAIN_REGISTERED':
      // Relay 서버가 플랫폼 키로 on-chain 자동 등록 완료 — tokenId 저장
      tokenId = msg.tokenId;
      await chrome.storage.local.set({ tokenId: msg.tokenId });
      console.log(`[Relay] on-chain 자동 등록 완료 — tokenId: ${msg.tokenId} tx: ${msg.txHash}`);
      notifyPopup({ type: 'ONCHAIN_REGISTERED', tokenId: msg.tokenId, txHash: msg.txHash });
      break;

    case 'INVOKE':
      await handleInvoke(msg);
      break;

    case 'PING':
      send({ type: 'PONG' });
      break;

    default:
      console.warn('[Relay] 알 수 없는 타입:', msg.type);
  }
}

// ─────────────── INVOKE 처리 (Policy Engine) ───────────────

async function handleInvoke({ requestId, payload, caller }) {
  console.log(`[Invoke] ${requestId} | skill=${payload.skill} | caller=${caller.agentId} (${caller.trustLevel})`);
  logActivity({ requestId, payload, caller, receivedAt: Date.now() });

  const decision = evaluatePolicy(payload, caller);

  if (decision === 'auto_approve') {
    await executeAndRespond(requestId, payload, caller);

  } else if (decision === 'reject') {
    console.log(`[Policy] 자동 거절: ${requestId}`);
    send({ type: 'RESPONSE', requestId, decision: 'rejected', error: '정책에 의해 거절됨' });
    notifyPopup({ type: 'ACTIVITY', requestId, payload, caller, decision: 'rejected', auto: true });

  } else {
    // 수동 승인 필요 — session storage 에 영속화
    console.log(`[Policy] 수동 승인 필요: ${requestId}`);
    await sessionSavePending(requestId, payload, caller);

    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#F97316' });

    // 팝업이 열려 있으면 즉시 전달, 닫혀 있으면 팝업 열 때 GET_STATUS 로 복원됨
    notifyPopup({ type: 'APPROVAL_REQUEST', requestId, payload, caller });
  }
}

// ─────────────── Policy Engine ───────────────

function evaluatePolicy(payload, caller) {
  const trustLevel    = caller.trustLevel ?? 'unverified';
  const trustDecision = policy.trustLevels[trustLevel];

  if (trustDecision === 'reject') return 'reject';

  if (policy.requireApprovalFor.some((d) => payload.skill?.includes(d))) return 'require_approval';

  if (payload.cost != null && payload.cost > policy.costThreshold) return 'require_approval';

  if (trustDecision === 'auto_approve') return 'auto_approve';

  return 'require_approval';
}

// ─────────────── 실행 및 응답 ───────────────

async function executeAndRespond(requestId, payload, caller) {
  try {
    const res = await fetch(`${serverUrl}/api/chat`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        message:    `[${caller.agentId}] ${payload.skill}: ${JSON.stringify(payload.params)}`,
        session_id: `relay_${requestId.slice(0, 8)}`,
      }),
      signal: AbortSignal.timeout(55_000),
    });

    if (!res.ok) throw new Error(`OpenChiken 서버 오류: HTTP ${res.status}`);
    const data = await res.json();

    send({ type: 'RESPONSE', requestId, decision: 'approved', result: { reply: data.reply } });
    notifyPopup({ type: 'ACTIVITY', requestId, payload, caller, decision: 'approved', auto: true });
    console.log(`[Invoke] 완료: ${requestId}`);
  } catch (err) {
    console.error(`[Invoke] 실행 오류: ${err.message}`);
    send({ type: 'RESPONSE', requestId, decision: 'rejected', error: err.message });
    notifyPopup({ type: 'ACTIVITY', requestId, decision: 'error', error: err.message });
  }
}

// ─────────────── 팝업 메시지 통신 ───────────────

function notifyPopup(msg) {
  chrome.runtime.sendMessage(msg).catch(() => { /* 팝업 닫혀 있으면 무시 */ });
}

// ─────────────── 활동 로그 ───────────────

async function logActivity(entry) {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');
  activityLog.unshift({ id: crypto.randomUUID(), ...entry });
  if (activityLog.length > 100) activityLog.length = 100;
  await chrome.storage.local.set({ activityLog });
}

// ─────────────── 팝업 → Background 메시지 핸들러 ───────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.type) {

    // 팝업 열릴 때 현재 상태 + 대기 중인 승인 요청 반환
    case 'GET_STATUS':
      sessionFirstPending().then((firstPending) => {
        sendResponse({
          relayConnected:  ws?.readyState === WebSocket.OPEN,
          agentId,
          agentAddress,
          tokenId,
          relayUrl,
          pendingApproval: firstPending,  // null 이면 idle 상태
        });
      });
      return true; // 비동기 응답

    case 'USER_APPROVED':
      sessionGetPending().then(async (stored) => {
        const entry = stored[msg.requestId];
        if (!entry) { sendResponse({ ok: false, error: 'not found' }); return; }

        await sessionRemovePending(msg.requestId);

        // 남은 대기 요청 없으면 badge 제거
        const remaining = await sessionFirstPending();
        if (!remaining) chrome.action.setBadgeText({ text: '' });

        await executeAndRespond(msg.requestId, entry.payload, entry.caller);
        sendResponse({ ok: true });
      });
      return true;

    case 'USER_REJECTED':
      sessionGetPending().then(async (stored) => {
        const entry = stored[msg.requestId];
        if (!entry) { sendResponse({ ok: false, error: 'not found' }); return; }

        await sessionRemovePending(msg.requestId);

        const remaining = await sessionFirstPending();
        if (!remaining) chrome.action.setBadgeText({ text: '' });

        send({ type: 'RESPONSE', requestId: msg.requestId, decision: 'rejected', error: '사용자가 거절했습니다.' });
        notifyPopup({ type: 'ACTIVITY', requestId: msg.requestId, decision: 'rejected', auto: false });
        sendResponse({ ok: true });
      });
      return true;

    case 'UPDATE_SETTINGS':
      chrome.storage.local.set(msg.settings).then(() => {
        if (msg.settings.tokenId)   tokenId   = msg.settings.tokenId;
        if (msg.settings.relayUrl)  relayUrl  = msg.settings.relayUrl;
        if (msg.settings.serverUrl) serverUrl = msg.settings.serverUrl;
        if (msg.settings.policy)    policy    = { ...policy, ...msg.settings.policy };
        if (msg.settings.relayUrl)  { ws?.close(); connectRelay(); }
        sendResponse({ ok: true });
      });
      return true;

    default:
      sendResponse({ ok: false, error: 'unknown type' });
  }
  return false;
});

// ─────────────── 설치 이벤트 ───────────────

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason === 'install') {
    // 에이전트 전용 Ethereum 지갑 생성 (개인키는 chrome.storage에만 보관)
    const wallet = Wallet.createRandom();
    agentAddress = wallet.address;

    await chrome.storage.local.set({
      activityLog:      [],
      policy:           DEFAULTS.policy,
      agentAddress:     wallet.address,
      agentPrivateKey:  wallet.privateKey,  // 로컬에만 저장, 외부 노출 없음
    });
    await chrome.storage.session.set({ pendingApprovals: {} });
    console.log('[OpenChiken] Extension 설치됨 v0.2.0 | 지갑 생성:', wallet.address);
  }

  if (reason === 'update') {
    // 기존 설치에 지갑이 없으면 새로 생성
    const cfg = await chrome.storage.local.get(['relayUrl', 'agentAddress']);

    if (!cfg.agentAddress) {
      const wallet = Wallet.createRandom();
      agentAddress = wallet.address;
      await chrome.storage.local.set({
        agentAddress:    wallet.address,
        agentPrivateKey: wallet.privateKey,
      });
      console.log('[OpenChiken] 지갑 마이그레이션 완료:', wallet.address);
    }

    if (!cfg.relayUrl || cfg.relayUrl === 'ws://localhost:3000/ws') {
      await chrome.storage.local.set({ relayUrl: DEFAULTS.relayUrl });
      console.log('[OpenChiken] Relay URL 마이그레이션:', DEFAULTS.relayUrl);
    }
  }
});

// ─────────────── 시작 ───────────────

init();
