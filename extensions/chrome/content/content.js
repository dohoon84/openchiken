/**
 * OpenChiken — Content Script
 *
 * 역할:
 *   - 현재 페이지의 컨텍스트 수집 (제목, URL, 메타, 선택 텍스트)
 *   - background service-worker로 컨텍스트 전달
 *   - Phase 2: DOM 조작, 인증 세션 접근 준비
 */

(function () {
  'use strict';

  // ───────── 페이지 컨텍스트 수집 ─────────

  function collectContext() {
    return {
      title:       document.title,
      url:         location.href,
      domain:      location.hostname,
      description: getMeta('description'),
      selectedText: window.getSelection()?.toString().trim() || '',
      collectedAt: Date.now(),
    };
  }

  function getMeta(name) {
    const el =
      document.querySelector(`meta[name="${name}"]`) ||
      document.querySelector(`meta[property="og:${name}"]`);
    return el?.getAttribute('content') || '';
  }

  // ───────── background로 컨텍스트 전송 ─────────

  function sendContext() {
    const ctx = collectContext();
    chrome.runtime.sendMessage({ type: 'PAGE_CONTEXT', payload: ctx }).catch(() => {});
  }

  // 페이지 로드 완료 후 전송
  if (document.readyState === 'complete') {
    sendContext();
  } else {
    window.addEventListener('load', sendContext, { once: true });
  }

  // ───────── background 메시지 수신 ─────────

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type === 'REQUEST_CONTEXT') {
      sendResponse({ payload: collectContext() });
    }
    return false;
  });

})();
