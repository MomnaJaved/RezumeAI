/* ============================================================
   RezumeAI — LinkedIn content script (message bridge)
   DOM scrape: extract_core.js → profile_pipeline.js (idle + JSON)
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
        const pipeline = globalThis.__rezumeRunProfilePipeline;
        if (typeof pipeline === 'function') {
          sendResponse(await pipeline(req));
          return;
        }
        const asyncFn = globalThis.__rezumeExtractLinkedInAsync;
        const syncFn = globalThis.__rezumeExtractLinkedIn;
        const data =
          typeof asyncFn === 'function'
            ? await asyncFn(req)
            : typeof syncFn === 'function'
              ? syncFn(req)
              : {
                  success: false,
                  fullText: '',
                  extracted_ok: false,
                  error:
                    globalThis.__rezumeExtractInitError ||
                    'Rezume extract did not load. Hard-refresh this LinkedIn tab (Ctrl+Shift+R), then chrome://extensions → Reload for RezumeAI.',
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
