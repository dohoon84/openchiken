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

import { Wallet, JsonRpcProvider, formatEther } from './ethers.min.js';

// ─────────────── 설정 기본값 ───────────────

const DEFAULTS = {
  relayUrl:   'wss://openchiken-relay-production.up.railway.app/ws',
  serverUrl:  'http://localhost:8000',
  rpcUrl:     'https://ethereum-sepolia-rpc.publicnode.com',
  chainName:  'Sepolia Testnet',
  chainId:    11155111,
  agentEnabled: false,
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

let ws                   = null;
let agentId              = null;
let agentAddress         = null;
let tokenId              = null;
let agentEnabled         = false;
let relayUrl             = DEFAULTS.relayUrl;
let serverUrl            = DEFAULTS.serverUrl;
let policy               = DEFAULTS.policy;
let reconnectTimer       = null;
let cachedCapabilities   = null;

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
  const cfg = await chrome.storage.local.get(['agentId', 'agentAddress', 'tokenId', 'relayUrl', 'serverUrl', 'policy', 'agentEnabled', 'cachedCapabilities']);

  if (!cfg.agentId) {
    agentId = `oc_ext_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    await chrome.storage.local.set({ agentId });
  } else {
    agentId = cfg.agentId;
  }

  if (cfg.agentAddress)         agentAddress         = cfg.agentAddress;
  if (cfg.tokenId)              tokenId              = cfg.tokenId;
  if (cfg.relayUrl)             relayUrl             = cfg.relayUrl;
  if (cfg.serverUrl)            serverUrl            = cfg.serverUrl;
  if (cfg.policy)               policy               = { ...DEFAULTS.policy, ...cfg.policy };
  if (cfg.cachedCapabilities)   cachedCapabilities   = cfg.cachedCapabilities;
  agentEnabled = cfg.agentEnabled === true;

  const firstPending = await sessionFirstPending();
  if (firstPending) {
    chrome.action.setBadgeText({ text: '!' });
    chrome.action.setBadgeBackgroundColor({ color: '#F97316' });
    console.log('[Init] 대기 중인 승인 복원:', firstPending.requestId);
  }

  if (agentEnabled) {
    connectRelay();
  } else {
    console.log('[Init] 에이전트 비활성 — 릴레이 연결 건너뜀');
  }
}

// ─────────────── WebSocket 연결 ───────────────

function connectRelay() {
  if (!agentEnabled) return;
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) return;

  console.log(`[Relay] 연결 시도: ${relayUrl}`);
  ws = new WebSocket(relayUrl);

  ws.onopen = async () => {
    console.log('[Relay] 연결됨');
    clearTimeout(reconnectTimer);
    const capabilities = await fetchCapabilities();
    const registerMsg = { type: 'REGISTER', agentId, capabilities, version: '0.2.0' };
    if (tokenId)      registerMsg.tokenId      = tokenId;
    if (agentAddress) registerMsg.agentAddress = agentAddress;
    send(registerMsg);
    console.log(`[Relay] 등록 capabilities: ${capabilities.join(', ')}`);
    notifyPopup({ type: 'RELAY_STATUS', status: 'connected', agentId });

    const pending = await sessionFirstPending();
    if (!pending) chrome.action.setBadgeText({ text: '' });
  };

  ws.onmessage = ({ data }) => {
    try { handleRelayMessage(JSON.parse(data)); }
    catch (e) { console.error('[Relay] 메시지 파싱 오류:', e); }
  };

  ws.onclose = (e) => {
    if (!agentEnabled) return;
    const reason = e.reason ? ` (${e.reason})` : '';
    console.warn(`[Relay] 연결 끊김 code=${e.code}${reason} — 5초 후 재연결`);
    notifyPopup({ type: 'RELAY_STATUS', status: 'disconnected' });
    reconnectTimer = setTimeout(connectRelay, 5_000);
  };

  ws.onerror = (e) => {
    // WebSocket ErrorEvent는 .message가 없으므로 type으로 표시
    console.error('[Relay] WebSocket 오류 — 연결 실패 또는 끊김 (type:', e?.type ?? 'unknown', ')');
  };
}

/**
 * 로컬 서버의 /api/skills 에서 활성화된 스킬의 도메인 영역을 가져옵니다.
 * 성공하면 chrome.storage.local에 캐시합니다.
 * 실패 시 이전 캐시 → 기본값 순으로 폴백합니다.
 */
async function fetchCapabilities() {
  try {
    const res = await fetch(`${serverUrl}/api/skills`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const domains = [...new Set(
      (data.skills || [])
        .filter(s => s.enabled && (s.status === 'connected' || s.status === 'hub_installed' || s.status === 'ai_generated'))
        .map(s => s.domain || s.name)
        .filter(Boolean)
    )];

    const result = domains.length ? domains : ['browser_context', 'local_agent'];

    // 성공 시 캐시 갱신
    cachedCapabilities = result;
    await chrome.storage.local.set({ cachedCapabilities: result });
    console.log(`[Relay] capabilities 캐시 갱신: ${result.join(', ')}`);
    return result;
  } catch (e) {
    console.warn('[Relay] capabilities 조회 실패:', e.message);

    // 이전 캐시가 있으면 캐시 사용
    if (cachedCapabilities && cachedCapabilities.length > 0) {
      console.log(`[Relay] 캐시된 capabilities 사용: ${cachedCapabilities.join(', ')}`);
      return cachedCapabilities;
    }

    // 캐시도 없으면 기본값
    console.warn('[Relay] 캐시 없음 — 기본 capabilities 사용');
    return ['browser_context', 'local_agent'];
  }
}

function disconnectRelay() {
  agentEnabled = false;
  clearTimeout(reconnectTimer);
  if (ws) {
    ws.onclose = null;
    ws.close();
    ws = null;
  }
  notifyPopup({ type: 'RELAY_STATUS', status: 'disabled' });
  console.log('[Relay] 에이전트 비활성화 — 연결 해제');
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

    case 'TX_RECORDED':
      // Relay가 on-chain 평판 기록 완료 후 txHash 알림
      if (msg.requestId) {
        await upsertActivityLog(msg.requestId, { txHash: msg.txHash, score: msg.score });
      }
      notifyPopup({ type: 'TX_RECORDED', requestId: msg.requestId, txHash: msg.txHash, score: msg.score });
      console.log(`[Relay] TX_RECORDED — requestId: ${msg.requestId} txHash: ${msg.txHash}`);
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
    await upsertActivityLog(requestId, { decision: 'rejected' });
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

    await upsertActivityLog(requestId, { decision: 'approved' });
    send({ type: 'RESPONSE', requestId, decision: 'approved', result: { reply: data.reply } });
    notifyPopup({ type: 'ACTIVITY', requestId, payload, caller, decision: 'approved', auto: true });
    console.log(`[Invoke] 완료: ${requestId}`);
  } catch (err) {
    console.error(`[Invoke] 실행 오류: ${err.message}`);
    await upsertActivityLog(requestId, { decision: 'error', error: err.message });
    send({ type: 'RESPONSE', requestId, decision: 'rejected', error: err.message });
    notifyPopup({ type: 'ACTIVITY', requestId, decision: 'error', error: err.message });
  }
}

// ─────────────── 팝업 메시지 통신 ───────────────

function notifyPopup(msg) {
  chrome.runtime.sendMessage(msg).catch(() => { /* 팝업 닫혀 있으면 무시 */ });
}

// ─────────────── 지갑 잔액 조회 ───────────────

async function getWalletBalance() {
  if (!agentAddress) return { balance: '0', chainName: DEFAULTS.chainName, chainId: DEFAULTS.chainId };
  try {
    const provider = new JsonRpcProvider(DEFAULTS.rpcUrl);
    const raw = await provider.getBalance(agentAddress);
    const balance = formatEther(raw);
    return { balance, chainName: DEFAULTS.chainName, chainId: DEFAULTS.chainId };
  } catch (e) {
    console.error('[Wallet] 잔액 조회 실패:', e.message);
    return { balance: '—', chainName: DEFAULTS.chainName, chainId: DEFAULTS.chainId, error: e.message };
  }
}

// ─────────────── 활동 로그 ───────────────

async function logActivity(entry) {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');
  activityLog.unshift({ id: crypto.randomUUID(), ...entry });
  if (activityLog.length > 100) activityLog.length = 100;
  await chrome.storage.local.set({ activityLog });
}

/** requestId로 기존 로그 항목을 찾아 부분 업데이트 */
async function upsertActivityLog(requestId, updates) {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');
  const idx = activityLog.findIndex(e => e.requestId === requestId);
  if (idx !== -1) {
    activityLog[idx] = { ...activityLog[idx], ...updates };
    await chrome.storage.local.set({ activityLog });
  }
}

// ─────────────── 팝업 → Background 메시지 핸들러 ───────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  switch (msg.type) {

    case 'GET_STATUS':
      sessionFirstPending().then((firstPending) => {
        sendResponse({
          relayConnected:  ws?.readyState === WebSocket.OPEN,
          agentEnabled,
          agentId,
          agentAddress,
          tokenId,
          relayUrl,
          pendingApproval: firstPending,
        });
      });
      return true;

    case 'TOGGLE_AGENT':
      (async () => {
        agentEnabled = msg.enabled === true;
        await chrome.storage.local.set({ agentEnabled });
        if (agentEnabled) {
          connectRelay();
        } else {
          disconnectRelay();
        }
        sendResponse({ ok: true, agentEnabled });
      })();
      return true;

    case 'GET_BALANCE':
      getWalletBalance().then((info) => sendResponse(info));
      return true;

    case 'EXPORT_IDENTITY':
      chrome.storage.local.get(['agentId', 'agentAddress', 'agentPrivateKey', 'tokenId']).then((cfg) => {
        sendResponse({
          ok: true,
          identity: {
            agentId:      cfg.agentId      || null,
            agentAddress: cfg.agentAddress  || null,
            privateKey:   cfg.agentPrivateKey || null,
            tokenId:      cfg.tokenId       || null,
            exportedAt:   new Date().toISOString(),
            version:      '0.2.0',
          },
        });
      });
      return true;

    case 'IMPORT_IDENTITY':
      (async () => {
        try {
          const { privateKey: pk, agentId: importedId, tokenId: importedToken } = msg.identity;
          if (!pk) { sendResponse({ ok: false, error: '프라이빗 키가 없습니다' }); return; }

          const wallet = new Wallet(pk);
          agentId      = importedId || agentId;
          agentAddress = wallet.address;
          tokenId      = importedToken || null;

          await chrome.storage.local.set({
            agentId,
            agentAddress:    wallet.address,
            agentPrivateKey: wallet.privateKey,
            ...(tokenId ? { tokenId } : {}),
          });

          if (agentEnabled && ws) {
            ws.onclose = null;
            ws.close();
            ws = null;
            connectRelay();
          }

          sendResponse({ ok: true, agentId, agentAddress: wallet.address });
        } catch (e) {
          sendResponse({ ok: false, error: `Import 실패: ${e.message}` });
        }
      })();
      return true;

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
        if (msg.settings.policy)    policy    = { ...policy, ...msg.settings.policy };
        if (msg.settings.serverUrl) {
          // serverUrl 변경 시 capabilities 캐시 초기화 (새 서버에서 다시 조회)
          serverUrl = msg.settings.serverUrl;
          cachedCapabilities = null;
          chrome.storage.local.remove('cachedCapabilities');
        }
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
      agentEnabled:     false,
      agentAddress:     wallet.address,
      agentPrivateKey:  wallet.privateKey,
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
