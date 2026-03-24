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

    $('agentIdVal').textContent = res.agentId ?? '—';

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
        setRelayStatus(msg.status);
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
}

document.addEventListener('DOMContentLoaded', init);
