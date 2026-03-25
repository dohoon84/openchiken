const $ = (id) => document.getElementById(id);

let currentRequestId = null;
let settingsServerUrl = 'http://localhost:8000';
let currentTab = 'activity';
let _agentId = null;
let _agentAddress = null;
let _tokenId = null;

// ─────────────── 초기화 ───────────────

async function init() {
  const cfg = await chrome.storage.local.get(['serverUrl']);
  if (cfg.serverUrl) settingsServerUrl = cfg.serverUrl;

  await loadStatus();
  await loadBalance();
  await loadActivityLog();
  bindButtons();
  listenBackground();
}

// ─────────────── 아바타 ───────────────

function updateAvatar(agentId) {
  const el = $('agentAvatar');
  if (!el || !agentId || agentId === '—') return;

  const hash = agentId.split('').reduce((acc, c) => (acc * 31 + c.charCodeAt(0)) | 0, 0);
  const h1 = Math.abs(hash) % 360;
  const h2 = (h1 + 70) % 360;
  el.style.background = `linear-gradient(135deg, hsl(${h1},65%,50%), hsl(${h2},65%,38%))`;
  el.textContent = agentId.replace('oc_ext_', '').slice(0, 2).toUpperCase();
}

function truncateAddr(addr) {
  if (!addr || addr.length < 12) return addr || '—';
  return addr.slice(0, 6) + '...' + addr.slice(-4);
}

function truncateId(id) {
  if (!id || id.length < 20) return id || '—';
  return id.slice(0, 14) + '...' + id.slice(-4);
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

// ─────────────── 상태 로드 ───────────────

async function loadStatus() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (!res) return;

    $('agentToggle').checked = res.agentEnabled === true;

    setRelayStatus(res.agentEnabled ? (res.relayConnected ? 'connected' : 'disconnected') : 'disabled');

    _agentId = res.agentId ?? null;
    _agentAddress = res.agentAddress ?? null;
    _tokenId = res.tokenId ?? null;

    $('agentIdShort').textContent = truncateId(_agentId);
    $('walletAddr').textContent = truncateAddr(_agentAddress);
    updateAvatar(_agentId);

    if (_tokenId) {
      $('tokenBadge').textContent = `Token #${_tokenId}`;
      $('tokenBadge').classList.remove('none');
    } else {
      $('tokenBadge').textContent = '토큰 미연결';
      $('tokenBadge').classList.add('none');
    }

    $('trustBadge').textContent = '—';
    $('trustBadge').className = 'trust-badge unverified';

    if (res.pendingApproval) {
      showApprovalPanel(res.pendingApproval.requestId, res.pendingApproval.payload, res.pendingApproval.caller);
    }
  });
}

async function loadBalance() {
  chrome.runtime.sendMessage({ type: 'GET_BALANCE' }, (info) => {
    if (!info) return;
    const bal = parseFloat(info.balance);
    $('balanceDisplay').textContent = isNaN(bal) ? '— ETH' : `${bal.toFixed(4)} ETH`;
    if (info.chainName) $('networkName').textContent = info.chainName.replace(' Testnet', '');
  });
}

// ─────────────── Relay 상태 ───────────────

function setRelayStatus(status) {
  const dot = $('relayDot');
  const label = $('relayLabel');
  const idle = $('approvalPanel')?.classList.contains('hidden') ? true : false;

  if (status === 'disabled') {
    dot.className = 'relay-dot';
    label.textContent = '비활성';
  } else if (status === 'connected') {
    dot.className = 'relay-dot connected';
    label.textContent = '연결됨';
  } else {
    dot.className = 'relay-dot disconnected';
    label.textContent = '오프라인';
  }
}

// ─────────────── 탭 전환 ───────────────

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tab);
  });
  $('tabActivity').classList.toggle('hidden', tab !== 'activity');
  $('tabOnchain').classList.toggle('hidden', tab !== 'onchain');

  if (tab === 'onchain') loadOnchainTab();
}

// ─────────────── 승인 패널 ───────────────

function showApprovalPanel(requestId, payload, caller) {
  currentRequestId = requestId;
  $('apCaller').textContent = caller.agentId ?? '—';

  const trustEl = $('apTrust');
  const tl = caller.trustLevel ?? 'unverified';
  trustEl.textContent = { platform_verified: '플랫폼 검증', community_verified: '커뮤니티 검증', unverified: '미검증' }[tl] ?? tl;
  trustEl.className = `ap-v trust-pill ${tl}`;

  $('apSkill').textContent = payload.skill ?? '—';
  $('apParams').textContent = JSON.stringify(payload.params ?? {}, null, 2);
  $('approvalPanel').classList.remove('hidden');
}

function hideApprovalPanel() {
  currentRequestId = null;
  $('approvalPanel').classList.add('hidden');
}

// ─────────────── 활동 로그 ───────────────

const DECISION_LABEL = { approved: '승인', rejected: '거절', error: '오류', timeout: '타임아웃' };

async function loadActivityLog() {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');

  const received = activityLog.slice(0, 20).map(e => ({
    id: e.id ?? e.requestId,
    direction: 'recv',
    agentId: e.caller?.agentId ?? '?',
    skill: e.payload?.skill ?? '?',
    status: e.decision ?? 'error',
    at: e.receivedAt ? new Date(e.receivedAt).toISOString() : null,
    txHash: e.txHash ?? null,
    score: e.score ?? null,
  }));

  let sent = [];
  try {
    const res = await fetch(`${settingsServerUrl}/api/relay/activity?limit=20`, { signal: AbortSignal.timeout(3000) });
    if (res.ok) {
      const data = await res.json();
      sent = (data.activities || []).map(e => ({
        id: e.id, direction: 'sent', agentId: e.agentId ?? '?',
        skill: e.skill ?? '?', status: e.status ?? 'approved', at: e.at,
        txHash: e.txHash ?? null, score: e.score ?? null,
      }));
    }
  } catch { /* ignore */ }

  const combined = [...received, ...sent].sort((a, b) => {
    if (!a.at && !b.at) return 0;
    if (!a.at) return 1;
    if (!b.at) return -1;
    return b.at.localeCompare(a.at);
  });

  renderLog(combined.slice(0, 15));
}

function _buildLogItem(e) {
  const isRecv = e.direction === 'recv';
  const dot = e.status ?? 'error';
  const dirHtml = `<span class="log-dir ${isRecv ? 'recv' : 'sent'}">${isRecv ? '↓' : '↑'}</span>`;
  const text = isRecv ? `${e.agentId} / ${e.skill}` : `→ ${e.agentId} / ${e.skill}`;
  const label = DECISION_LABEL[e.status] ?? e.status ?? '?';

  const txHtml = e.txHash
    ? `<a class="log-tx" data-href="https://sepolia.etherscan.io/tx/${e.txHash}" title="${e.txHash.slice(0, 14)}…">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
      </a>` : '';

  const scoreCls = e.score != null && e.score < 50 ? 'log-score low' : 'log-score';
  const scoreHtml = e.score != null ? `<span class="${scoreCls}">${e.score}</span>` : '';

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
  if (!entries.length) { list.innerHTML = '<li class="log-empty">아직 활동 없음</li>'; return; }
  list.innerHTML = entries.map(_buildLogItem).join('');
}

function appendLog(entry) {
  const list = $('logList');
  list.querySelector('.log-empty')?.remove();

  const normalized = {
    id: entry.requestId, direction: 'recv',
    agentId: entry.caller?.agentId ?? '?',
    skill: entry.payload?.skill ?? (entry.requestId ? `req ${entry.requestId.slice(0, 8)}` : '?'),
    status: entry.decision ?? 'error', at: null,
    txHash: entry.txHash ?? null, score: entry.score ?? null,
  };

  const li = document.createElement('li');
  li.innerHTML = _buildLogItem(normalized);
  list.prepend(li.firstElementChild);
  while (list.children.length > 15) list.removeChild(list.lastChild);
}

function updateLogItemTx(requestId, txHash, score) {
  if (!requestId || !txHash) return;
  for (const li of $('logList').querySelectorAll('.log-item')) {
    if (li.dataset.requestId !== requestId) continue;

    if (!li.querySelector('.log-tx')) {
      const a = document.createElement('a');
      a.className = 'log-tx';
      a.dataset.href = `https://sepolia.etherscan.io/tx/${txHash}`;
      a.title = txHash.slice(0, 14) + '…';
      a.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
      const ref = li.querySelector('.log-meta');
      if (ref) li.insertBefore(a, ref);
    }

    if (score != null && !li.querySelector('.log-score')) {
      const span = document.createElement('span');
      span.className = score < 50 ? 'log-score low' : 'log-score';
      span.textContent = score;
      const ref = li.querySelector('.log-tx') || li.querySelector('.log-meta');
      if (ref) li.insertBefore(span, ref);
    }
    break;
  }
}

// ─────────────── 온체인 탭 ───────────────

async function loadOnchainTab() {
  $('chainTokenId').textContent = _tokenId ? `#${_tokenId}` : '미연결';
  $('chainOwner').textContent = truncateAddr(_agentAddress);
  $('chainTrust').textContent = '—';
  $('chainFeedback').textContent = '— 건';

  // activityLog에서 txHash 있는 항목 추출
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');
  const txEntries = activityLog.filter(e => e.txHash).slice(0, 20);

  const txList = $('txList');
  if (!txEntries.length) {
    txList.innerHTML = '<li class="tx-empty">기록 없음</li>';
  } else {
    txList.innerHTML = txEntries.map(e => {
      const hash = e.txHash;
      const shortHash = hash.slice(0, 10) + '...' + hash.slice(-6);
      const scoreCls = e.score != null && e.score < 50 ? 'tx-score low' : 'tx-score';
      const scoreHtml = e.score != null ? `<span class="${scoreCls}">${e.score}</span>` : '';
      const skill = e.payload?.skill ?? '';
      return `<li class="tx-item">
        <a class="tx-hash" data-href="https://sepolia.etherscan.io/tx/${hash}" title="${hash}">${shortHash}</a>
        ${scoreHtml}
        <span class="tx-skill">${skill}</span>
      </li>`;
    }).join('');
  }

  // 서버 프록시로 on-chain 평판 조회 시도
  if (!_agentId) return;
  try {
    const res = await fetch(`${settingsServerUrl}/api/dashboard/agents`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return;
    const data = await res.json();
    const me = (data.agents || []).find(a => a.agentId === _agentId);
    if (me) {
      if (me.tokenId) $('chainTokenId').textContent = `#${me.tokenId}`;
      $('chainTrust').textContent = { platform_verified: '플랫폼 검증', community_verified: '커뮤니티 검증', unverified: '미검증' }[me.trustLevel] ?? me.trustLevel ?? '—';

      // 메인 뷰 trust badge도 업데이트
      const mainTrust = $('trustBadge');
      if (me.trustLevel) {
        mainTrust.textContent = { platform_verified: '플랫폼 검증', community_verified: '커뮤니티 검증', unverified: '미검증' }[me.trustLevel] ?? me.trustLevel;
        mainTrust.className = `trust-badge ${me.trustLevel}`;
      }

      if (me.reputation) {
        const avg = me.reputation.average != null ? `${me.reputation.average}/100` : '—';
        $('chainFeedback').textContent = `${me.reputation.count}건 (평균 ${avg})`;
      }
    }
  } catch { /* ignore */ }
}

// ─────────────── Background 메시지 수신 ───────────────

function listenBackground() {
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case 'RELAY_STATUS':
        setRelayStatus(msg.status);
        if (msg.agentId) {
          _agentId = msg.agentId;
          $('agentIdShort').textContent = truncateId(msg.agentId);
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
        updateLogItemTx(msg.requestId, msg.txHash, msg.score);
        break;
      case 'ONCHAIN_REGISTERED':
        _tokenId = msg.tokenId;
        $('tokenBadge').textContent = `Token #${msg.tokenId}`;
        $('tokenBadge').classList.remove('none');
        break;
    }
  });
}

// ─────────────── 설정 데이터 로드 ───────────────

async function loadSettingsData() {
  const cfg = await chrome.storage.local.get(['serverUrl', 'tokenId', 'agentId', 'agentAddress']);
  if (cfg.serverUrl) settingsServerUrl = cfg.serverUrl;

  $('sServerUrl').value = settingsServerUrl;
  $('sDashboardLink').href = `${settingsServerUrl}/dashboard.html`;
  if (cfg.tokenId) $('sTokenIdInput').value = cfg.tokenId;
  $('sWalletAddr').textContent = cfg.agentAddress || '지갑 없음';
  $('sAgentId').textContent = cfg.agentId || '—';

  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (!res) return;
    if (!res.agentEnabled) {
      $('sRelayStatus').textContent = '비활성';
      $('sRelayStatus').style.color = 'var(--text3)';
    } else {
      $('sRelayStatus').textContent = res.relayConnected ? '연결됨' : '연결 안됨';
      $('sRelayStatus').style.color = res.relayConnected ? 'var(--green)' : 'var(--red)';
    }
    if (res.tokenId) $('sTokenId').textContent = res.tokenId;
  });

  chrome.runtime.sendMessage({ type: 'GET_BALANCE' }, (info) => {
    if (!info) return;
    const bal = parseFloat(info.balance);
    $('sBalance').textContent = isNaN(bal) ? info.balance : `${bal.toFixed(4)} ETH`;
    $('sChainName').textContent = info.chainName || '—';
  });

  try {
    const res = await fetch(`${settingsServerUrl}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw 0;
    const data = await res.json();
    $('sPvProvider').textContent = data.provider || '—';
    $('sPvModel').textContent = data.model || '—';
    $('sPvName').textContent = data.assistant_name || '—';
  } catch {
    $('sPvProvider').textContent = '서버 미연결';
    $('sPvModel').textContent = '—';
    $('sPvName').textContent = '—';
  }
}

// ─────────────── Identity Export / Import ───────────────

function showIdentityMsg(text, type) {
  const el = $('identityMsg');
  el.className = `identity-msg ${type}`;
  el.textContent = text;
  if (type === 'ok') setTimeout(() => el.classList.add('hidden'), 4000);
}

function exportIdentity() {
  chrome.runtime.sendMessage({ type: 'EXPORT_IDENTITY' }, (res) => {
    if (!res?.ok || !res.identity) {
      showIdentityMsg('Export 실패', 'err');
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

function handleImportFile(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    try {
      const identity = JSON.parse(ev.target.result);
      if (!identity.privateKey) { showIdentityMsg('유효하지 않은 파일', 'err'); return; }

      const msg = identity.agentId
        ? `에이전트 "${identity.agentId}"로 교체합니다. 계속?`
        : '프라이빗 키를 Import합니다. 계속?';
      if (!confirm(msg)) return;

      chrome.runtime.sendMessage({ type: 'IMPORT_IDENTITY', identity }, (res) => {
        if (res?.ok) {
          showIdentityMsg(`Import 완료 — ${res.agentAddress}`, 'ok');
          _agentId = res.agentId;
          _agentAddress = res.agentAddress;
          $('agentIdShort').textContent = truncateId(res.agentId);
          $('walletAddr').textContent = truncateAddr(res.agentAddress);
          updateAvatar(res.agentId);
        } else {
          showIdentityMsg(res?.error || 'Import 실패', 'err');
        }
      });
    } catch { showIdentityMsg('JSON 파싱 실패', 'err'); }
  };
  reader.readAsText(file);
  e.target.value = '';
}

// ─────────────── 버튼 바인딩 ───────────────

function bindButtons() {
  // Tabs
  document.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => switchTab(t.dataset.tab));
  });

  // Approval
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

  // Agent toggle
  $('agentToggle').addEventListener('change', (e) => {
    const enabled = e.target.checked;
    chrome.runtime.sendMessage({ type: 'TOGGLE_AGENT', enabled }, (res) => {
      if (!res?.ok) return;
      setRelayStatus(enabled ? 'disconnected' : 'disabled');
    });
  });

  // Header
  $('btnCopyId').addEventListener('click', async () => {
    if (!_agentId) return;
    await navigator.clipboard.writeText(_agentId);
    const toast = $('copyToast');
    toast.classList.remove('hidden');
    setTimeout(() => toast.classList.add('hidden'), 1500);
  });

  $('btnMenu').addEventListener('click', showSettingsView);

  // Action buttons
  $('btnDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: `${settingsServerUrl}/dashboard.html` });
  });

  $('btnEtherscan').addEventListener('click', () => {
    if (_agentAddress) {
      chrome.tabs.create({ url: `https://sepolia.etherscan.io/address/${_agentAddress}` });
    }
  });

  $('btnExportId').addEventListener('click', exportIdentity);
  $('btnImportId').addEventListener('click', () => $('importFileInput').click());
  $('importFileInput').addEventListener('change', handleImportFile);

  // Log
  $('btnClearLog').addEventListener('click', async () => {
    await chrome.storage.local.set({ activityLog: [] });
    $('logList').innerHTML = '<li class="log-empty">아직 활동 없음</li>';
  });

  // Settings
  $('btnBack').addEventListener('click', showMainView);
  $('btnTestConn').addEventListener('click', async () => {
    const url = $('sServerUrl').value.trim();
    const r = $('sTestResult'); r.className = 's-result'; r.textContent = '연결 테스트 중...';
    try {
      const res = await fetch(`${url}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      r.classList.add('ok'); r.textContent = `연결 성공 — ${data.provider} / ${data.model}`;
      $('sPvProvider').textContent = data.provider || '—';
      $('sPvModel').textContent = data.model || '—';
      $('sPvName').textContent = data.assistant_name || '—';
      $('sDashboardLink').href = `${url}/dashboard.html`;
    } catch (e) { r.classList.add('err'); r.textContent = `연결 실패 — ${e.message}`; }
  });

  $('btnSaveSettings').addEventListener('click', async () => {
    settingsServerUrl = $('sServerUrl').value.trim();
    const tokenIdVal = $('sTokenIdInput').value.trim();
    const settings = { serverUrl: settingsServerUrl };
    if (tokenIdVal) settings.tokenId = tokenIdVal;
    await chrome.storage.local.set(settings);
    chrome.runtime.sendMessage({ type: 'UPDATE_SETTINGS', settings });
    $('sSaveMsg').classList.remove('hidden');
    setTimeout(() => $('sSaveMsg').classList.add('hidden'), 2500);
  });

  $('sServerUrl').addEventListener('input', () => { $('sTestResult').className = 's-result hidden'; });

  $('btnCopyAddr').addEventListener('click', async () => {
    const addr = $('sWalletAddr').textContent;
    if (!addr || addr.startsWith('지갑')) return;
    await navigator.clipboard.writeText(addr);
    $('sCopyMsg').classList.remove('hidden');
    setTimeout(() => $('sCopyMsg').classList.add('hidden'), 2000);
  });

  // tx/log link delegation
  document.addEventListener('click', (e) => {
    const link = e.target.closest('[data-href]');
    if (!link) return;
    e.preventDefault();
    chrome.tabs.create({ url: link.dataset.href });
  });
}

document.addEventListener('DOMContentLoaded', init);
