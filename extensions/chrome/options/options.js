const $ = (id) => document.getElementById(id);

let serverUrl = 'http://localhost:8000';

async function init() {
  const cfg = await chrome.storage.local.get(['serverUrl']);
  if (cfg.serverUrl) serverUrl = cfg.serverUrl;

  $('serverUrl').value = serverUrl;
  $('dashboardLink').href = `${serverUrl}/dashboard.html`;

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
  await chrome.storage.local.set({ serverUrl });
  $('saveMsg').classList.remove('hidden');
  setTimeout(() => $('saveMsg').classList.add('hidden'), 2500);
}

function bindEvents() {
  $('btnTest').addEventListener('click', testConnection);
  $('btnSave').addEventListener('click', saveSettings);
  $('serverUrl').addEventListener('input', () => {
    $('testResult').className = 'test-result hidden';
  });
}

document.addEventListener('DOMContentLoaded', init);
