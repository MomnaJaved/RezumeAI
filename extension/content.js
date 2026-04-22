/* ============================================================
   RezumeAI — LinkedIn content script (message bridge)
   Heavy scraping lives in extract_core.js (same isolated world).
   ============================================================ */
'use strict';

chrome.runtime.onMessage.addListener((req, _sender, sendResponse) => {
  if (req.action === 'ping') {
    sendResponse({ pong: true, url: location.href });
    return false;
  }
  if (req.action === 'extract_profile') {
    (async () => {
      try {
        const asyncFn = globalThis.__rezumeExtractLinkedInAsync;
        const syncFn = globalThis.__rezumeExtractLinkedIn;
        const data =
          typeof asyncFn === 'function'
            ? await asyncFn()
            : typeof syncFn === 'function'
              ? syncFn()
              : {
                  success: false,
                  fullText: '',
                  extracted_ok: false,
                  error:
                    'RezumeAI scraper is not loaded on this page. Reload the extension, refresh the LinkedIn tab, and try again.',
                };
        sendResponse(data);
      } catch (e) {
        sendResponse({ success: false, fullText: '', extracted_ok: false, error: String(e && e.message) });
      }
    })();
    return true;
  }
  return false;
});
