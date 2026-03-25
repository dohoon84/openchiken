const $ = (id) => document.getElementById(id);

let currentRequestId = null;
let settingsServerUrl = 'http://localhost:8000';

// ─────────────── 초기화 ───────────────

async function init() {
  await loadStatus();
  await loadActivityLog();
  bindButtons();
  listenBackground();
}

// ─────────────── Agent ID → 아바타 색상 생성 ───────────────

function getAvatarGradient(agentId) {
  if (!agentId || agentId === '—') return 'background: linear-gradient(135deg, #333, #444)';
  const hash = agentId.split('').reduce((acc, c) => (acc * 31 + c.charCodeAt(0)) | 0, 0);
  const h1 = Math.abs(hash) % 360;
  const h2 = (h1 + 70) % 360;
  return `background: linear-gradient(135deg, hsl(${h1},65%,50%), hsl(${h2},65%,38%))`;
}

function updateAvatar(agentId) {
  const el = $('agentAvatar');
  if (!el) return;
  el.style.cssText = getAvatarGradient(agentId);
  if (agentId && agentId !== '—') {
    el.textContent = agentId.replace('oc_ext_', '').slice(0, 2).toUpperCase();
  } else {
    el.textContent = 'OC';
  }
}

// ─────────────── 뷰 전환 ───────────────

function showSettingsView() {
  $('mainView').classList.add('hidden');
  $('settingsView').classList.remove('hidden');
  loadSettingsData();
}

function showMainView() {
  $('settingsView').classList.add('hidden');
  $('mainView').classList.remove('hidden');
}

// ─────────────── 설정 데이터 로드 ───────────────

async function loadSettingsData() {
  const cfg = await chrome.storage.local.get(['serverUrl', 'tokenId', 'agentId', 'agentAddress']);
  if (cfg.serverUrl) settingsServerUrl = cfg.serverUrl;

  $('sServerUrl').value = settingsServerUrl;
  $('sDashboardLink').href = `${settingsServerUrl}/dashboard.html`;

  if (cfg.tokenId) $('sTokenIdInput').value = cfg.tokenId;

  $('sWalletAddr').textContent = cfg.agentAddress || '지갑 없음';
  $('sAgentId').textContent    = cfg.agentId || '—';

  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (res) {
      if (!res.agentEnabled) {
        $('sRelayStatus').textContent = '비활성';
        $('sRelayStatus').style.color = 'var(--text3)';
      } else {
        $('sRelayStatus').textContent = res.relayConnected ? '연결됨' : '연결 안됨';
        $('sRelayStatus').style.color = res.relayConnected ? 'var(--green)' : 'var(--red)';
      }
      if (res.tokenId) $('sTokenId').textContent = res.tokenId;
    }
  });

  chrome.runtime.sendMessage({ type: 'GET_BALANCE' }, (info) => {
    if (info) {
      const bal = parseFloat(info.balance);
      $('sBalance').textContent = isNaN(bal) ? info.balance : `${bal.toFixed(4)} ETH`;
      $('sChainName').textContent = info.chainName || '—';
    }
  });

  fetchSettingsProviderStatus();
}

async function fetchSettingsProviderStatus() {
  try {
    const res = await fetch(`${settingsServerUrl}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error('non-ok');
    const data = await res.json();
    $('sPvProvider').textContent = data.provider || '—';
    $('sPvModel').textContent    = data.model    || '—';
    $('sPvName').textContent     = data.assistant_name || '—';
  } catch {
    $('sPvProvider').textContent = '서버 미연결';
    $('sPvModel').textContent    = '—';
    $('sPvName').textContent     = '—';
  }
}

// ─────────────── 설정: 연결 테스트 ───────────────

async function testSettingsConnection() {
  const url = $('sServerUrl').value.trim();
  const result = $('sTestResult');
  result.className = 's-result';
  result.textContent = '연결 테스트 중...';

  try {
    const res = await fetch(`${url}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    result.classList.add('ok');
    result.textContent = `연결 성공 — ${data.provider} / ${data.model}`;
    $('sPvProvider').textContent = data.provider || '—';
    $('sPvModel').textContent    = data.model    || '—';
    $('sPvName').textContent     = data.assistant_name || '—';
    $('sDashboardLink').href     = `${url}/dashboard.html`;
  } catch (e) {
    result.classList.add('err');
    result.textContent = `연결 실패 — ${e.message}`;
  }
}

// ─────────────── 설정: 저장 ───────────────

async function savePopupSettings() {
  settingsServerUrl = $('sServerUrl').value.trim();
  const tokenIdVal = $('sTokenIdInput').value.trim();

  const settings = { serverUrl: settingsServerUrl };
  if (tokenIdVal) settings.tokenId = tokenIdVal;

  await chrome.storage.local.set(settings);
  chrome.runtime.sendMessage({ type: 'UPDATE_SETTINGS', settings });

  $('sSaveMsg').classList.remove('hidden');
  setTimeout(() => $('sSaveMsg').classList.add('hidden'), 2500);
}

// ─────────────── 설정: 지갑 주소 복사 ───────────────

async function copyWalletAddress() {
  const addr = $('sWalletAddr').textContent;
  if (!addr || addr.startsWith('지갑')) return;
  await navigator.clipboard.writeText(addr);
  $('sCopyMsg').classList.remove('hidden');
  setTimeout(() => $('sCopyMsg').classList.add('hidden'), 2000);
}

// ─────────────── 설정: Identity Export / Import ───────────────

function showIdentityMsg(text, type) {
  const el = $('sIdentityMsg');
  el.className = `s-identity-msg ${type}`;
  el.textContent = text;
  if (type === 'ok') setTimeout(() => el.classList.add('hidden'), 4000);
}

function exportIdentity() {
  chrome.runtime.sendMessage({ type: 'EXPORT_IDENTITY' }, (res) => {
    if (!res?.ok || !res.identity) {
      showIdentityMsg('Export 실패: 데이터를 가져올 수 없습니다', 'err');
      return;
    }
    const json = JSON.stringify(res.identity, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `openchiken-agent-${(res.identity.agentId || 'unknown').slice(0, 16)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showIdentityMsg('에이전트 키 파일이 다운로드되었습니다', 'ok');
  });
}

function importIdentity() {
  $('importFileInput').click();
}

function handleImportFile(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const identity = JSON.parse(ev.target.result);
      if (!identity.privateKey) {
        showIdentityMsg('유효하지 않은 파일: privateKey가 없습니다', 'err');
        return;
      }

      const confirmMsg = identity.agentId
        ? `에이전트 "${identity.agentId}"로 교체합니다. 기존 지갑이 덮어씌워집니다. 계속하시겠습니까?`
        : '프라이빗 키를 Import합니다. 기존 지갑이 덮어씌워집니다. 계속하시겠습니까?';

      if (!confirm(confirmMsg)) return;

      chrome.runtime.sendMessage({ type: 'IMPORT_IDENTITY', identity }, (res) => {
        if (res?.ok) {
          showIdentityMsg(`Import 완료 — ${res.agentAddress}`, 'ok');
          $('sWalletAddr').textContent  = res.agentAddress;
          $('sAgentId').textContent     = res.agentId;
          $('agentIdVal').textContent   = res.agentId;
          updateAvatar(res.agentId);
        } else {
          showIdentityMsg(res?.error || 'Import 실패', 'err');
        }
      });
    } catch {
      showIdentityMsg('JSON 파싱 실패: 올바른 파일인지 확인하세요', 'err');
    }
  };
  reader.readAsText(file);
  e.target.value = '';
}

// ─────────────── 상태 로드 ───────────────

async function loadStatus() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (!res) return;

    const toggle = $('agentToggle');
    toggle.checked = res.agentEnabled === true;

    if (!res.agentEnabled) {
      setRelayStatus('disabled');
    } else {
      setRelayStatus(res.relayConnected ? 'connected' : 'disconnected');
    }

    const agentId = res.agentId ?? '—';
    $('agentIdVal').textContent = agentId;
    updateAvatar(agentId);

    if (res.pendingApproval) {
      const { requestId, payload, caller } = res.pendingApproval;
      showApprovalPanel(requestId, payload, caller);
    }
  });
}

// ─────────────── Relay 상태 표시 ───────────────

function setRelayStatus(status) {
  const dot   = $('relayDot');
  const label = $('relayLabel');
  const badge = $('relayBadge');
  const idle  = $('idlePanel');

  badge.classList.remove('disabled');

  if (status === 'disabled') {
    dot.className = 'relay-dot';
    label.textContent = '비활성';
    badge.classList.add('disabled');
    if (idle) {
      idle.querySelector('.idle-title').textContent = '에이전트 비활성';
      idle.querySelector('.idle-sub').innerHTML = '토글을 켜면 릴레이에 연결되어<br/>외부 에이전트 요청을 수신합니다';
    }
  } else if (status === 'connected') {
    dot.className = 'relay-dot connected';
    label.textContent = '릴레이 연결됨';
    if (idle) {
      idle.querySelector('.idle-title').textContent = '에이전트 대기 중';
      idle.querySelector('.idle-sub').innerHTML = '외부 에이전트 요청을 수신하면<br/>정책 엔진이 자동으로 처리합니다';
    }
  } else {
    dot.className = 'relay-dot disconnected';
    label.textContent = '릴레이 오프라인';
    if (idle) {
      idle.querySelector('.idle-title').textContent = '에이전트 대기 중';
      idle.querySelector('.idle-sub').innerHTML = '릴레이 서버에 재연결 중입니다...';
    }
  }
}

// ─────────────── 승인 패널 ───────────────

function showApprovalPanel(requestId, payload, caller) {
  currentRequestId = requestId;

  $('apCaller').textContent = caller.agentId ?? '—';

  const trustEl = $('apTrust');
  trustEl.textContent = trustLevelLabel(caller.trustLevel);
  trustEl.className   = `av trust-badge ${caller.trustLevel ?? 'unverified'}`;

  $('apSkill').textContent  = payload.skill ?? '—';
  $('apParams').textContent = JSON.stringify(payload.params ?? {}, null, 2);

  $('approvalPanel').classList.remove('hidden');
  $('idlePanel').style.display = 'none';
}

function hideApprovalPanel() {
  currentRequestId = null;
  $('approvalPanel').classList.add('hidden');
  $('idlePanel').style.display = '';
}

function trustLevelLabel(level) {
  return { platform_verified: '플랫폼 검증', community_verified: '커뮤니티 검증', unverified: '미검증' }[level] ?? level ?? '알 수 없음';
}

// ─────────────── 활동 로그 ───────────────

const DECISION_LABEL = { approved: '승인', rejected: '거절', error: '오류', timeout: '타임아웃', pending: '처리중' };

/** 로컬 수신 로그(chrome.storage) + 서버 송신 로그를 통합해서 표시 */
async function loadActivityLog() {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');

  const received = activityLog.slice(0, 20).map((e) => ({
    id:        e.id ?? e.requestId,
    direction: 'recv',
    agentId:   e.caller?.agentId ?? '?',
    skill:     e.payload?.skill  ?? '?',
    status:    e.decision ?? 'error',
    at:        e.receivedAt ? new Date(e.receivedAt).toISOString() : null,
    txHash:    e.txHash ?? null,
    score:     e.score  ?? null,
  }));

  let sent = [];
  try {
    const res = await fetch(`${settingsServerUrl}/api/relay/activity?limit=20`, {
      signal: AbortSignal.timeout(3000),
    });
    if (res.ok) {
      const data = await res.json();
      sent = (data.activities || []).map((e) => ({
        id:        e.id,
        direction: 'sent',
        agentId:   e.agentId ?? '?',
        skill:     e.skill   ?? '?',
        status:    e.status  ?? 'approved',
        at:        e.at,
        summary:   e.summary,
        txHash:    e.txHash ?? null,
        score:     e.score  ?? null,
      }));
    }
  } catch { /* 서버 오프라인이면 무시 */ }

  const combined = [...received, ...sent].sort((a, b) => {
    if (!a.at && !b.at) return 0;
    if (!a.at) return 1;
    if (!b.at) return -1;
    return b.at.localeCompare(a.at);
  });

  renderLog(combined.slice(0, 15));
}

function _buildLogItem(e) {
  const isRecv  = e.direction === 'recv';
  const dot     = e.status ?? 'error';
  const dirHtml = `<span class="log-dir ${isRecv ? 'recv' : 'sent'}">${isRecv ? '↓' : '↑'}</span>`;
  const text    = isRecv
    ? `${e.agentId} / ${e.skill}`
    : `→ ${e.agentId} / ${e.skill}`;
  const label   = DECISION_LABEL[e.status] ?? e.status ?? '?';

  // on-chain txHash 링크 (Sepolia Etherscan)
  const txHtml = e.txHash
    ? `<a class="log-tx" data-href="https://sepolia.etherscan.io/tx/${e.txHash}" title="Tx: ${e.txHash.slice(0, 10)}... — Etherscan에서 확인">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
      </a>`
    : '';

  // 점수 배지 (score가 있을 때만)
  const scoreCls = e.score != null && e.score < 50 ? 'log-score low' : 'log-score';
  const scoreHtml = e.score != null
    ? `<span class="${scoreCls}">${e.score}</span>`
    : '';

  return `<li class="log-item" data-request-id="${e.id ?? ''}">
    <span class="log-dot ${dot}"></span>
    ${dirHtml}
    <span class="log-text">${text}</span>
    ${scoreHtml}
    ${txHtml}
    <span class="log-meta">${label}</span>
  </li>`;
}

function renderLog(entries) {
  const list = $('logList');
  if (!entries.length) {
    list.innerHTML = '<li class="log-empty">아직 활동 없음</li>';
    return;
  }
  list.innerHTML = entries.map(_buildLogItem).join('');
}

/** 수신 이벤트 실시간 추가 (background 메시지) */
function appendLog(entry) {
  const list = $('logList');
  const empty = list.querySelector('.log-empty');
  if (empty) empty.remove();

  const normalized = {
    id:        entry.requestId,
    direction: 'recv',
    agentId:   entry.caller?.agentId ?? '?',
    skill:     entry.payload?.skill  ?? (entry.requestId ? `req ${entry.requestId.slice(0, 8)}` : '?'),
    status:    entry.decision ?? 'error',
    at:        null,
    txHash:    entry.txHash ?? null,
    score:     entry.score  ?? null,
  };

  const li = document.createElement('li');
  li.innerHTML = _buildLogItem(normalized);
  list.prepend(li.firstElementChild);

  while (list.children.length > 15) list.removeChild(list.lastChild);
}

/**
 * 기존 로그 항목에 txHash / score 실시간 업데이트
 * relay에서 TX_RECORDED 메시지 수신 시 호출
 */
function updateLogItemTx(requestId, txHash, score) {
  if (!requestId || !txHash) return;

  const list  = $('logList');
  const items = list.querySelectorAll('.log-item');

  for (const li of items) {
    if (li.dataset.requestId !== requestId) continue;

    // txHash 링크 아직 없으면 추가
    if (!li.querySelector('.log-tx')) {
      const txEl = document.createElement('a');
      txEl.className = 'log-tx';
      txEl.dataset.href = `https://sepolia.etherscan.io/tx/${txHash}`;
      txEl.title = `Tx: ${txHash.slice(0, 10)}... — Etherscan에서 확인`;
      txEl.innerHTML = `<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
      </svg>`;
      const metaEl = li.querySelector('.log-meta');
      if (metaEl) li.insertBefore(txEl, metaEl);
    }

    // score 배지 아직 없으면 추가
    if (score != null && !li.querySelector('.log-score')) {
      const scoreEl = document.createElement('span');
      scoreEl.className = score < 50 ? 'log-score low' : 'log-score';
      scoreEl.textContent = score;
      const txEl = li.querySelector('.log-tx');
      const metaEl = li.querySelector('.log-meta');
      const insertBefore = txEl || metaEl;
      if (insertBefore) li.insertBefore(scoreEl, insertBefore);
    }

    break;
  }
}

// ─────────────── background 메시지 수신 ───────────────

function listenBackground() {
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case 'RELAY_STATUS':
        setRelayStatus(msg.status);
        if (msg.agentId) {
          $('agentIdVal').textContent = msg.agentId;
          updateAvatar(msg.agentId);
        }
        break;

      case 'APPROVAL_REQUEST':
        showApprovalPanel(msg.requestId, msg.payload, msg.caller);
        break;

      case 'ACTIVITY':
        if (msg.requestId === currentRequestId) hideApprovalPanel();
        appendLog(msg);
        break;

      case 'TX_RECORDED':
        // on-chain 피드백 완료 — 로그 항목에 txHash 표시
        updateLogItemTx(msg.requestId, msg.txHash, msg.score);
        break;
    }
  });
}

// ─────────────── 버튼 ───────────────

function bindButtons() {
  $('btnApprove').addEventListener('click', () => {
    if (!currentRequestId) return;
    chrome.runtime.sendMessage({ type: 'USER_APPROVED', requestId: currentRequestId });
    appendLog({ requestId: currentRequestId, decision: 'approved' });
    hideApprovalPanel();
  });

  $('btnReject').addEventListener('click', () => {
    if (!currentRequestId) return;
    chrome.runtime.sendMessage({ type: 'USER_REJECTED', requestId: currentRequestId });
    appendLog({ requestId: currentRequestId, decision: 'rejected' });
    hideApprovalPanel();
  });

  $('btnSettings').addEventListener('click', showSettingsView);

  $('btnClearLog').addEventListener('click', async () => {
    await chrome.storage.local.set({ activityLog: [] });
    $('logList').innerHTML = '<li class="log-empty">아직 활동 없음</li>';
  });

  $('btnBack').addEventListener('click', showMainView);
  $('btnTestConn').addEventListener('click', testSettingsConnection);
  $('btnSaveSettings').addEventListener('click', savePopupSettings);
  $('btnCopyAddr').addEventListener('click', copyWalletAddress);
  $('btnExportId').addEventListener('click', exportIdentity);
  $('btnImportId').addEventListener('click', importIdentity);
  $('importFileInput').addEventListener('change', handleImportFile);

  // Agent ID 복사 버튼
  $('btnCopyId').addEventListener('click', async () => {
    const id = $('agentIdVal').textContent;
    if (!id || id === '—') return;
    await navigator.clipboard.writeText(id);
    const toast = $('copyToast');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 1500);
  });

  $('sServerUrl').addEventListener('input', () => {
    $('sTestResult').className = 's-result hidden';
  });

  $('agentToggle').addEventListener('change', (e) => {
    const enabled = e.target.checked;
    chrome.runtime.sendMessage({ type: 'TOGGLE_AGENT', enabled }, (res) => {
      if (!res?.ok) return;
      if (enabled) {
        setRelayStatus('disconnected');
      } else {
        setRelayStatus('disabled');
      }
    });
  });

  // txHash 링크 — chrome.tabs.create로 새 탭 열기
  document.addEventListener('click', (e) => {
    const txEl = e.target.closest('.log-tx');
    if (!txEl) return;
    e.preventDefault();
    const url = txEl.dataset.href || txEl.href;
    if (url) chrome.tabs.create({ url });
  });
}

document.addEventListener('DOMContentLoaded', init);
