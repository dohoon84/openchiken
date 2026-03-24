const $ = (id) => document.getElementById(id);

let currentRequestId = null;

// ─────────────── 초기화 ───────────────

async function init() {
  await loadStatus();
  await loadActivityLog();
  bindButtons();
  listenBackground();
}

async function loadStatus() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (!res) return;
    setRelayStatus(res.relayConnected);
    $('agentIdVal').textContent = res.agentId ?? '—';

    // 팝업이 닫혀 있는 동안 쌓인 승인 요청 복원
    if (res.pendingApproval) {
      const { requestId, payload, caller } = res.pendingApproval;
      showApprovalPanel(requestId, payload, caller);
    }
  });
}

// ─────────────── Relay 상태 표시 ───────────────

function setRelayStatus(connected) {
  const dot   = $('relayDot');
  const label = $('relayLabel');
  dot.className   = `relay-dot ${connected ? 'connected' : 'disconnected'}`;
  label.textContent = connected ? '릴레이 연결됨' : '릴레이 오프라인';
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

async function loadActivityLog() {
  const { activityLog = [] } = await chrome.storage.local.get('activityLog');
  renderLog(activityLog.slice(0, 10));
}

function renderLog(entries) {
  const list = $('logList');
  if (!entries.length) {
    list.innerHTML = '<li class="log-empty">아직 활동 없음</li>';
    return;
  }
  list.innerHTML = entries.map((e) => {
    const dot   = e.decision ?? 'error';
    const text  = `${e.caller?.agentId ?? '?'} → ${e.payload?.skill ?? '?'}`;
    const meta  = e.decision ?? '?';
    const label = { approved: '승인', rejected: '거절', error: '오류', timeout: '타임아웃' }[meta] ?? meta;
    return `<li class="log-item">
      <span class="log-dot ${dot}"></span>
      <span class="log-text">${text}</span>
      <span class="log-meta">${label}</span>
    </li>`;
  }).join('');
}

function appendLog(entry) {
  const list = $('logList');
  const empty = list.querySelector('.log-empty');
  if (empty) empty.remove();

  const dot   = entry.decision ?? 'error';
  const text  = entry.payload
    ? `${entry.caller?.agentId ?? '?'} → ${entry.payload.skill ?? '?'}`
    : `요청 ${entry.requestId?.slice(0, 8) ?? '?'}`;
  const label = { approved: '승인', rejected: '거절', error: '오류', timeout: '타임아웃' }[entry.decision] ?? entry.decision ?? '?';

  const li = document.createElement('li');
  li.className = 'log-item';
  li.innerHTML = `<span class="log-dot ${dot}"></span>
    <span class="log-text">${text}</span>
    <span class="log-meta">${label}</span>`;

  list.prepend(li);

  // 최대 10개 유지
  while (list.children.length > 10) list.removeChild(list.lastChild);
}

// ─────────────── background 메시지 수신 ───────────────

function listenBackground() {
  chrome.runtime.onMessage.addListener((msg) => {
    switch (msg.type) {
      case 'RELAY_STATUS':
        setRelayStatus(msg.status === 'connected');
        if (msg.agentId) $('agentIdVal').textContent = msg.agentId;
        break;

      case 'APPROVAL_REQUEST':
        showApprovalPanel(msg.requestId, msg.payload, msg.caller);
        break;

      case 'ACTIVITY':
        if (msg.requestId === currentRequestId) hideApprovalPanel();
        appendLog(msg);
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

  $('btnSettings').addEventListener('click', () => chrome.runtime.openOptionsPage());

  $('btnClearLog').addEventListener('click', async () => {
    await chrome.storage.local.set({ activityLog: [] });
    $('logList').innerHTML = '<li class="log-empty">아직 활동 없음</li>';
  });
}

document.addEventListener('DOMContentLoaded', init);
