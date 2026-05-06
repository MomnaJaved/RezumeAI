/* ============================================================
   RezumeAI Chrome Extension — Options / Settings Page
   ============================================================ */

'use strict';

const SK = {
  TOKEN:    'rezume_token',
  EMAIL:    'rezume_email',
  API_BASE: 'rezume_api_base',
};

const $ = id => document.getElementById(id);

function showMsg(id, msg, isError) {
  const el = $(id);
  if (!el) return;
  el.textContent = msg;
  el.className = `msg ${isError ? 'error' : 'success'}`;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 4000);
}

async function init() {
  const stored = await chrome.storage.local.get([SK.API_BASE, SK.EMAIL]);
  $('api-base').value = stored[SK.API_BASE] || 'http://127.0.0.1:8000';
  $('current-email').textContent = stored[SK.EMAIL] || 'Not signed in';
}

$('btn-save')?.addEventListener('click', async () => {
  const url = ($('api-base')?.value || '').trim().replace(/\/$/, '');
  if (!url) { showMsg('save-result', 'Please enter a valid URL.', true); return; }
  await chrome.storage.local.set({ [SK.API_BASE]: url });
  showMsg('save-result', '✓ Saved successfully.', false);
});

$('btn-test')?.addEventListener('click', async () => {
  const url = ($('api-base')?.value || '').trim().replace(/\/$/, '');
  if (!url) { showMsg('test-result', 'Please enter a URL first.', true); return; }
  $('btn-test').disabled = true;
  $('btn-test').textContent = 'Testing…';
  try {
    const res  = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
    const data = await res.json();
    if (data.status === 'ok') {
      showMsg('test-result', `✓ Connected — API status: ${data.status}`, false);
    } else {
      showMsg('test-result', `API responded but status: ${data.status}`, true);
    }
  } catch (e) {
    showMsg('test-result', `✗ Could not reach API: ${e.message}`, true);
  } finally {
    $('btn-test').disabled = false;
    $('btn-test').textContent = 'Test Connection';
  }
});

$('btn-clear-session')?.addEventListener('click', async () => {
  await chrome.storage.local.remove([SK.TOKEN, SK.EMAIL]);
  $('current-email').textContent = 'Not signed in';
  showMsg('save-result', 'Signed out successfully.', false);
});

document.addEventListener('DOMContentLoaded', init);
