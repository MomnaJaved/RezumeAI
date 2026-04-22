/* ============================================================
   RezumeAI — Service Worker (MV3)
   Central API proxy: auth headers, consistent errors, survives
   brief popup closes during long match requests.
   ============================================================ */

'use strict';

const SK = { TOKEN: 'rezume_token', API_BASE: 'rezume_api_base' };

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    chrome.storage.local.get([SK.API_BASE], result => {
      if (!result[SK.API_BASE]) {
        chrome.storage.local.set({ [SK.API_BASE]: 'http://127.0.0.1:8000' });
      }
    });
    console.log('[RezumeAI] Extension installed. Default API: http://127.0.0.1:8000');
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== 'rezume_api') return false;

  (async () => {
    try {
      const stored = await chrome.storage.local.get([SK.TOKEN, SK.API_BASE]);
      const base = (stored[SK.API_BASE] || 'http://127.0.0.1:8000').replace(/\/$/, '');
      const headers = { Accept: 'application/json' };
      const method = (msg.method || 'GET').toUpperCase();
      if (msg.body != null) headers['Content-Type'] = 'application/json';
      const token = stored[SK.TOKEN];
      if (token) headers.Authorization = `Bearer ${token}`;

      const res = await fetch(`${base}${msg.path}`, {
        method,
        headers,
        body: msg.body != null ? msg.body : undefined,
      });
      const text = await res.text();
      sendResponse({ ok: res.ok, status: res.status, text });
    } catch (e) {
      sendResponse({
        ok: false,
        status: 0,
        text: JSON.stringify({ detail: e && e.message ? e.message : 'Network error' }),
      });
    }
  })();

  return true;
});
