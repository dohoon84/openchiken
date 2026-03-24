const $ = (id) => document.getElementById(id);

let serverUrl = 'http://localhost:8000';

async function init() {
  const cfg = await chrome.storage.local.get(['serverUrl', 'tokenId', 'agentId', 'agentAddress']);
  if (cfg.serverUrl) serverUrl = cfg.serverUrl;

  $('serverUrl').value = serverUrl;
  $('dashboardLink').href = `${serverUrl}/dashboard.html`;

  if (cfg.tokenId) $('tokenId').value = cfg.tokenId;

  // 지갑 주소 표시
  const addr = cfg.agentAddress;
  if (addr) {
    $('agentAddressDisplay').textContent = addr;
  } else {
    $('agentAddressDisplay').textContent = '지갑 없음 (Extension 재설치 필요)';
  }

  $('agentIdDisplay').textContent = cfg.agentId || '—';

  // 릴레이 연결 상태 + tokenId 조회
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (res) => {
    if (res) {
      $('relayStatus').textContent = res.relayConnected ? '연결됨' : '연결 안됨';
      $('relayStatus').style.color = res.relayConnected ? 'var(--green)' : 'var(--red)';
      if (res.tokenId) $('tokenIdDisplay').textContent = res.tokenId;
    }
  });

  await fetchProviderStatus();
  bindEvents();
}

async function fetchProviderStatus() {
  try {
    const res = await fetch(`${serverUrl}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error('non-ok');
    const data = await res.json();
    $('pvProvider').textContent = data.provider || '—';
    $('pvModel').textContent    = data.model    || '—';
    $('pvName').textContent     = data.assistant_name || '—';
  } catch {
    $('pvProvider').textContent = '서버 미연결';
    $('pvModel').textContent    = '—';
    $('pvName').textContent     = '—';
  }
}

async function testConnection() {
  const url = $('serverUrl').value.trim();
  const result = $('testResult');
  result.className = 'test-result';
  result.textContent = '연결 테스트 중...';

  try {
    const res = await fetch(`${url}/api/dashboard/agent-status`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    result.classList.add('ok');
    result.textContent = `연결 성공 — ${data.provider} / ${data.model} (${data.assistant_name})`;
    $('pvProvider').textContent = data.provider || '—';
    $('pvModel').textContent    = data.model    || '—';
    $('pvName').textContent     = data.assistant_name || '—';
    $('dashboardLink').href     = `${url}/dashboard.html`;
  } catch (e) {
    result.classList.add('err');
    result.textContent = `연결 실패 — ${e.message}. 서버가 실행 중인지 확인하세요.`;
  }
}

async function saveSettings() {
  serverUrl = $('serverUrl').value.trim();
  const tokenIdVal = $('tokenId').value.trim();

  const settings = { serverUrl };
  if (tokenIdVal) settings.tokenId = tokenIdVal;

  await chrome.storage.local.set(settings);

  // 런타임 상태에도 즉시 반영 (relay 재연결 없이 tokenId만 갱신)
  chrome.runtime.sendMessage({ type: 'UPDATE_SETTINGS', settings });

  $('saveMsg').classList.remove('hidden');
  setTimeout(() => $('saveMsg').classList.add('hidden'), 2500);
}

function bindEvents() {
  $('btnTest').addEventListener('click', testConnection);
  $('btnSave').addEventListener('click', saveSettings);
  $('serverUrl').addEventListener('input', () => {
    $('testResult').className = 'test-result hidden';
  });

  // 지갑 주소 복사
  $('btnCopyAddress').addEventListener('click', async () => {
    const addr = $('agentAddressDisplay').textContent;
    if (!addr || addr.startsWith('지갑')) return;
    await navigator.clipboard.writeText(addr);
    $('copyMsg').classList.remove('hidden');
    setTimeout(() => $('copyMsg').classList.add('hidden'), 2000);
  });
}

document.addEventListener('DOMContentLoaded', init);
