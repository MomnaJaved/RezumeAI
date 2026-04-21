/* ============================================================
   RezumeAI Chrome Extension — Service Worker (background.js)
   ============================================================ */

'use strict';

// Set default API base URL on first install
chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    chrome.storage.local.get(['rezume_api_base'], result => {
      if (!result.rezume_api_base) {
        chrome.storage.local.set({ rezume_api_base: 'http://127.0.0.1:8000' });
      }
    });
    console.log('[RezumeAI] Extension installed. Default API: http://127.0.0.1:8000');
  }
});

// Keep service worker alive during API calls (MV3 best practice)
chrome.runtime.onMessage.addListener((_msg, _sender, _sendResponse) => {
  // Intentionally empty — prevents "receiving end does not exist" errors
  // when popup sends messages while content script isn't present.
  return false;
});
