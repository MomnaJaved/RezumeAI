/* ===================================================================
   RezumeAI Chrome Extension — Popup Controller
   Flow: Sign in → LinkedIn auto scrape + section classify → Select job →
         Match & save (or preview match only)
   Backend: POST /api/v1/match/preview, ingestions/text, jobs/.../match-candidate-save
   =================================================================== */
'use strict';

// ── Constants ─────────────────────────────────────────────────────────
const SK = {
  TOKEN:    'rezume_token',
  EMAIL:    'rezume_email',
  API_BASE: 'rezume_api_base',
  ROLE:     'rezume_role',
};

const DEFAULT_API = 'http://127.0.0.1:8000';

// ── State ─────────────────────────────────────────────────────────────
const G = {
  apiBase:         DEFAULT_API,
  token:           null,
  email:           '',
  lastResult:      null,   // last MatchPreviewResponse
  selectedJobId:   null,
  savedCandId:     null,
  lastProfileJson: null,
};

// ── DOM helpers ───────────────────────────────────────────────────────
const $   = id  => document.getElementById(id);
const show = (...ids) => ids.forEach(id => $(id)?.classList.remove('hidden'));
const hide = (...ids) => ids.forEach(id => $(id)?.classList.add('hidden'));
const esc  = s  => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const val  = id => String($(id)?.value ?? '').trim();

/** Strip lone UTF-16 surrogates (scraped DOM can produce invalid Unicode / tokenizer issues). */
function sanitizeText(s) {
  return String(s ?? '').replace(/[\uD800-\uDFFF]/g, '');
}

function clipStr(s, maxLen) {
  const t = sanitizeText(s);
  if (t.length <= maxLen) return t;
  return t.slice(0, maxLen);
}

/**
 * Comma-separated skills for the API (hidden field filled on scrape, or a `Skills:` line in the profile textarea).
 * Keeps skill overlap / match breakdown aligned with the backend while the UI shows one combined text area.
 */
function skillsForMatchApi() {
  const h = clipStr(val('c-skills'), 32000).trim();
  if (h) return h;
  const text = val('c-text') || '';
  /* First non-empty `Skills:` line (extension / paste often puts this above the profile blob). */
  const lines = text.split(/\r?\n/);
  for (const line of lines) {
    const m = line.match(/^\s*Skills:\s*(.+)\s*$/i);
    if (m && m[1] != null) {
      const t = clipStr(String(m[1]).trim(), 32000);
      if (t) return t;
    }
  }
  return '';
}

/** Years ≥ 0 for API; preserves 0 (avoid `parseFloat(x) || undefined` which drops zero). */
function optionalYears(id) {
  const raw = val(id);
  if (raw === '') return undefined;
  const n = parseFloat(raw);
  if (!Number.isFinite(n) || n < 0) return undefined;
  return n;
}

/** Normalize FastAPI / Rezume JSON errors into one readable line. */
function formatApiError(data, fallbackText) {
  if (data == null || typeof data !== 'object') return fallbackText || 'Request failed';
  const det = data.detail;
  let msg = '';
  if (typeof data.error === 'string' && data.error.trim()) msg = data.error.trim();
  if (!msg && typeof data.message === 'string' && data.message.trim()) msg = data.message.trim();
  if (!msg && typeof det === 'string' && det.trim()) msg = det.trim();
  if (!msg && Array.isArray(det)) {
    const first = det[0];
    if (first && typeof first === 'object') msg = String(first.msg || first.type || JSON.stringify(first));
    else if (first != null) msg = String(first);
  }
  if (!msg && det && typeof det === 'object' && !Array.isArray(det)) {
    const inner = det.errors;
    if (Array.isArray(inner) && inner.length) {
      const e0 = inner[0];
      msg = typeof e0 === 'object' && e0 ? String(e0.msg || JSON.stringify(e0)) : String(e0);
    } else {
      msg = JSON.stringify(det);
    }
  }
  if (!msg && data.errors) msg = typeof data.errors === 'string' ? data.errors : JSON.stringify(data.errors);
  if (!msg) msg = fallbackText || 'Request failed';
  if (typeof data.code === 'string' && data.code && !msg.includes(data.code)) msg = `${msg} [${data.code}]`;
  return msg;
}

function showAlert(id, msg, type = 'error') {
  const el = $(id);
  if (!el) return;
  el.textContent = msg || '';
  el.className = `alert alert-${type}${msg ? '' : ' hidden'}`;
  if (!msg) el.classList.add('hidden');
}

function setBtn(id, loading, label) {
  const btn = $(id);
  if (!btn) return;
  btn.disabled = loading;
  const sp  = btn.querySelector('.spinner');
  const lbl = btn.querySelector('.btn-label') || btn.querySelector('span:not(.spinner)');
  sp?.classList.toggle('hidden', !loading);
  if (lbl && label) {
    if (!lbl.dataset.orig) lbl.dataset.orig = lbl.textContent;
    lbl.textContent = loading ? label : lbl.dataset.orig;
  }
}

// ── API proxy ─────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  const bodyStr = body != null ? JSON.stringify(body) : undefined;

  // Try background service worker first (handles auth header from storage)
  const viaBg = await new Promise(resolve => {
    try {
      chrome.runtime.sendMessage(
        { type: 'rezume_api', method, path, body: bodyStr },
        res => {
          const le = chrome.runtime.lastError;
          if (le) {
            resolve({
              ok: false,
              status: 0,
              text: JSON.stringify({ detail: le.message || 'Extension could not reach the background worker.' }),
            });
            return;
          }
          resolve(res ?? null);
        },
      );
    } catch { resolve(null); }
  });

  if (viaBg && typeof viaBg.ok === 'boolean') {
    let data;
    try { data = JSON.parse(viaBg.text); } catch { data = { detail: viaBg.text }; }
    if (!viaBg.ok) {
      const msg = formatApiError(data, viaBg.text || 'Request failed');
      const suffix = viaBg.status ? ` (HTTP ${viaBg.status})` : '';
      throw new Error(msg + suffix);
    }
    return data;
  }

  // Fallback: direct fetch
  const headers = { 'Content-Type': 'application/json' };
  if (G.token) headers['Authorization'] = `Bearer ${G.token}`;
  const res  = await fetch(`${G.apiBase}${path}`, { method, headers, body: bodyStr });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!res.ok) {
    const msg = formatApiError(data, res.statusText || 'Request failed');
    throw new Error(`${msg} (HTTP ${res.status})`);
  }
  return data;
}

// ── Auth ──────────────────────────────────────────────────────────────
async function login(email, password) {
  const data = await api('POST', '/api/v1/auth/login', { email, password });
  if (data.requires_otp) throw new Error('OTP required — sign in via the web app first.');
  if (!data.access_token) throw new Error('No access token returned.');
  G.token = data.access_token;
  G.email = email;
  await chrome.storage.local.set({
    [SK.TOKEN]:    G.token,
    [SK.EMAIL]:    email,
    [SK.API_BASE]: G.apiBase,
    [SK.ROLE]:     data.account_role || 'recruiter',
  });
}

async function logout() {
  G.token = null; G.email = '';
  await chrome.storage.local.remove([SK.TOKEN, SK.EMAIL, SK.ROLE]);
  showView('login');
}

// ── Views ─────────────────────────────────────────────────────────────
function showView(name) {
  ['login', 'main'].forEach(v => $(`view-${v}`)?.classList.toggle('hidden', v !== name));
  if (name === 'main') $('user-email').textContent = G.email;
}

function showStep(n) {
  const wb   = $('step-workbench');
  const done = $('step-3');
  if (n === 1) {
    wb?.classList.add('active');
    wb?.classList.remove('hidden');
    done?.classList.remove('active');
    done?.classList.add('hidden');
  } else if (n === 3) {
    wb?.classList.remove('active');
    wb?.classList.add('hidden');
    done?.classList.add('active');
    done?.classList.remove('hidden');
  }
}

// ── Health check ──────────────────────────────────────────────────────
async function checkHealth() {
  const dot  = $('status-dot');
  const txt  = $('status-text');
  if (dot) dot.className = 'status-dot checking';
  if (txt) txt.textContent = '…';
  try {
    const d = await api('GET', '/health');
    const ok = d.status === 'ok';
    if (dot) dot.className = `status-dot ${ok ? 'online' : 'warn'}`;
    if (txt) txt.textContent = ok ? 'Connected' : d.status;
  } catch {
    if (dot) dot.className = 'status-dot offline';
    if (txt) txt.textContent = 'Unreachable';
  }
}

// ── Timing ────────────────────────────────────────────────────────────
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── LinkedIn extraction (DOM; extract_core + profile_pipeline in page) ─
function isLinkedInHost(url) {
  try {
    const h = new URL(String(url ?? '')).hostname.toLowerCase();
    return h === 'linkedin.com' || h.endsWith('.linkedin.com');
  } catch { return false; }
}

function isLinkedInProfile(url) {
  if (!isLinkedInHost(url)) return false;
  try {
    return /^\/in\/[^/]+/i.test(new URL(url).pathname);
  } catch { return false; }
}

/** Decode /in/slug → readable name when DOM extract fails (same rules as extract_core slug heuristic). */
function humanNameFromLinkedInSlugPopup(encodedSlug) {
  let slug = '';
  try {
    slug = decodeURIComponent(String(encodedSlug || '').trim()).replace(/\+/g, ' ');
  } catch {
    slug = String(encodedSlug || '').trim();
  }
  const parts = slug.split('-').map(p => p.trim()).filter(Boolean);
  if (!parts.length) return '';
  function looksLikeOpaqueSuffix(seg) {
    const t = String(seg);
    if (t.length < 6 || t.length > 20) return false;
    if (!/^[a-zA-Z0-9]+$/.test(t)) return false;
    if (/^[a-f0-9]{6,12}$/i.test(t)) return true;
    if (/\d/.test(t) && t.length >= 6) return true;
    return false;
  }
  while (parts.length > 1 && looksLikeOpaqueSuffix(parts[parts.length - 1])) parts.pop();
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

/** Minimal fields from URL so the form is never totally empty on /in/… tabs */
function fillMinFromLinkedInTab(tab) {
  const u = String(tab?.url || '');
  if (!isLinkedInProfile(u)) return;
  let slug = '';
  try {
    const m = new URL(u).pathname.match(/\/in\/([^/?#]+)/i);
    if (m) slug = m[1];
  } catch { return; }
  if (!slug) return;
  const name = humanNameFromLinkedInSlugPopup(slug);
  const nEl = $('c-name');
  if (nEl && name && !(String(nEl.value ?? '').trim())) nEl.value = name;
  const tEl = $('c-text');
  if (tEl && !String(tEl.value ?? '').trim()) {
    tEl.value =
      `Name (from profile URL): ${name || slug}\nProfile: ${u.split('?')[0]}\n\n` +
      'If sections stay empty: hard-refresh LinkedIn (Ctrl+Shift+R), reload the extension, scroll About & Experience, then reopen this popup.';
  }
  const uEl = $('c-url');
  if (uEl && !String(uEl.value ?? '').trim()) uEl.value = u.split('?')[0];
  updateCharCount();
  syncCandSummary();
}

function isLinkedInDetailsSubpage(url) {
  if (!isLinkedInProfile(url)) return false;
  try {
    return /\/in\/[^/]+\/details\//i.test(new URL(url).pathname);
  } catch { return false; }
}

function linkedInMemberBaseProfileUrl(url) {
  try {
    const u = new URL(String(url || ''));
    const m = u.pathname.match(/^(\/in\/[^/]+)\//i);
    if (!m) return String(url || '');
    return `${u.origin}${m[1]}/`;
  } catch {
    return String(url || '');
  }
}

/**
 * Tab to scrape while the action popup is open.
 * Prefer any open LinkedIn /in/… tab (even in the background) so we never scrape localhost
 * or the RezumeAI app just because it was the last-focused window’s active tab.
 */
async function getRelevantTab() {
  const pickBest = tabs => {
    if (!tabs?.length) return null;
    const profile = tabs.find(t => t?.id && t.url && isLinkedInHost(t.url) && isLinkedInProfile(t.url));
    if (profile) return profile;
    const onLi = tabs.find(t => t?.id && t.url && isLinkedInHost(t.url));
    if (onLi) return onLi;
    const web = tabs.find(
      t =>
        t?.id &&
        t.url &&
        /^https?:\/\//i.test(t.url) &&
        !/^(chrome|edge|brave|vivaldi|about|devtools):/i.test(t.url),
    );
    return web || tabs.find(t => t?.id) || null;
  };

  try {
    const profileTabs = await chrome.tabs.query({
      url: [
        'https://*.linkedin.com/in/*',
        'http://*.linkedin.com/in/*',
        'https://linkedin.com/in/*',
        'http://linkedin.com/in/*',
      ],
    });
    if (profileTabs?.length) {
      let lastWinId = null;
      try {
        lastWinId = (await chrome.windows.getLastFocused()).id;
      } catch {
        /* ignore */
      }
      const inLastWin =
        lastWinId != null ? profileTabs.filter(t => t.windowId === lastWinId && isLinkedInProfile(t.url || '')) : [];
      const activeInLast = inLastWin.find(t => t.active);
      if (activeInLast) return activeInLast;
      const activeAny = profileTabs.find(t => t.active && isLinkedInProfile(t.url || ''));
      if (activeAny) return activeAny;
      if (inLastWin.length === 1) return inLastWin[0];
      if (inLastWin.length) return inLastWin[0];
      return profileTabs[0];
    }
  } catch {
    /* fall through */
  }

  try {
    const allActive = await chrome.tabs.query({ active: true });
    const t0 = pickBest(allActive);
    if (t0?.url && isLinkedInHost(t0.url)) return t0;
  } catch { /* ignore */ }

  try {
    const w = await chrome.windows.getLastFocused({ populate: true });
    const tx = pickBest(w.tabs || []);
    if (tx?.url && isLinkedInHost(tx.url)) return tx;
    if (tx) return tx;
  } catch { /* ignore */ }

  return null;
}

function extractionIsUsable(d) {
  if (!d || d.success === false) return false;
  if (d.extracted_ok) return true;
  const pj = d.profile_json;
  const pjOk =
    pj &&
    (String(pj.summary || '').length > 20 ||
      (Array.isArray(pj.skills) && pj.skills.length > 0) ||
      (Array.isArray(pj.experience) && pj.experience.length > 0));
  return (
    String(d.fullText ?? '').length >= 10 ||
    String(d.name ?? '').length >= 1 ||
    String(d.title ?? '').length >= 1 ||
    String(d.skills ?? '').length >= 3 ||
    Boolean(pjOk)
  );
}

function extractionIsSubstantial(d) {
  if (!d?.success) return false;
  const t = String(d.fullText ?? '');
  if (/PROFILE SECTIONS|WORK EXPERIENCE|EDUCATION \(from page\)/i.test(t)) return true;
  if (String(d.skills ?? '').length > 40) return true;
  const pj = d.profile_json;
  if (pj && ((pj.experience && pj.experience.length > 0) || String(pj.summary || '').length > 200))
    return true;
  return t.length > 1400;
}

/** LinkedIn SPA: injecting while status is still "loading" often yields no result. */
async function waitTabReady(tabId, maxMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const t = await chrome.tabs.get(tabId);
      if (t.discarded) throw new Error('That browser tab was unloaded. Click the LinkedIn tab once, then open the extension again.');
      if (t.status === 'complete' && t.url && !/^chrome:\/\//i.test(t.url)) return;
    } catch (e) {
      const msg = e?.message || String(e);
      if (/discarded|No tab with id/i.test(msg)) throw e instanceof Error ? e : new Error(msg);
    }
    await sleep(200);
  }
}

async function injectAndExtract(tabId, opts = {}) {
  if (tabId == null) throw new Error('Missing tab id');
  await waitTabReady(tabId);

  if (opts.requireLinkedInProfile) {
    const live = await chrome.tabs.get(tabId);
    const u = String(live.url || '');
    if (!isLinkedInHost(u) || !isLinkedInProfile(u)) {
      throw new Error(
        'This browser tab is not on a LinkedIn member profile anymore (it may have navigated to another site). Switch back to linkedin.com/in/…, then open the extension again.',
      );
    }
  }

  let needFiles = true;
  try {
    const probe = await chrome.scripting.executeScript({
      target: { tabId },
      func: () =>
        typeof globalThis.__rezumeRunProfilePipeline === 'function' &&
        (typeof globalThis.__rezumeExtractLinkedInAsync === 'function' ||
          typeof globalThis.__rezumeExtractLinkedIn === 'function'),
    });
    needFiles = !probe?.[0]?.result;
  } catch {
    needFiles = true;
  }

  if (needFiles) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['extract_core.js', 'profile_pipeline.js'],
      });
    } catch (e) {
      const le = typeof chrome !== 'undefined' ? chrome.runtime.lastError?.message : '';
      const m = [e?.message, le].filter(Boolean).join(' · ') || String(e);
      throw new Error(
        `Could not load extract scripts into this tab (${m}). Close other Chrome profiles, hard-refresh LinkedIn, then open the popup again.`,
      );
    }
  }

  let res;
  try {
    /**
     * Return payload as JSON inside a small object. Chrome’s structured-clone of the raw
     * pipeline object sometimes yields `result: undefined` on large / complex trees; a string
     * envelope clones reliably.
     */
    res = await chrome.scripting.executeScript({
      target: { tabId },
      args:   [{}],
      func: async req => {
        const pack = v => {
          try {
            return { ok: true, json: JSON.stringify(v === undefined ? null : v) };
          } catch (ser) {
            return { ok: false, err: 'JSON.stringify: ' + String(ser && ser.message ? ser.message : ser) };
          }
        };
        try {
          let data;
          if (typeof globalThis.__rezumeRunProfilePipeline === 'function')
            data = await globalThis.__rezumeRunProfilePipeline(req);
          else if (typeof globalThis.__rezumeExtractLinkedInAsync === 'function')
            data = await globalThis.__rezumeExtractLinkedInAsync(req);
          else if (typeof globalThis.__rezumeExtractLinkedIn === 'function')
            data = globalThis.__rezumeExtractLinkedIn({ skipPrime: false });
          else
            data = {
              success: false,
              error: 'Extract script not found. Reload the extension on chrome://extensions.',
              fullText: '',
              extracted_ok: false,
            };
          return pack(data);
        } catch (runErr) {
          return pack({
            success: false,
            extracted_ok: false,
            fullText: '',
            error: String(runErr && runErr.message ? runErr.message : runErr),
          });
        }
      },
    });
  } catch (e) {
    const le = typeof chrome !== 'undefined' ? chrome.runtime.lastError?.message : '';
    const m = [e?.message, le].filter(Boolean).join(' · ') || String(e);
    throw new Error(`Extract run failed (${m}).`);
  }
  if (!res?.length) {
    throw new Error(
      'Chrome returned no script result for this tab. Hard-refresh LinkedIn (Ctrl+Shift+R), reload the extension, then try again.',
    );
  }
  const boxed = res[0]?.result;
  if (boxed && typeof boxed === 'object' && boxed.ok === true && typeof boxed.json === 'string') {
    try {
      return JSON.parse(boxed.json);
    } catch (pe) {
      throw new Error(`Extract result could not be parsed: ${pe.message}`);
    }
  }
  if (boxed && typeof boxed === 'object' && boxed.ok === false && boxed.err) {
    throw new Error(`Extract data could not be sent from the page: ${boxed.err}`);
  }
  if (boxed !== undefined && boxed !== null && typeof boxed === 'object' && 'success' in boxed) {
    return boxed;
  }
  throw new Error(
    'Extract returned no result (page may still be loading, or scripting was blocked in this frame). Wait for the profile to finish loading, hard-refresh LinkedIn, then try again.',
  );
}

/** Chrome’s sendMessage error when no content script listener is registered on the tab. */
function isNoReceiverError(msg) {
  const s = String(msg || '').toLowerCase();
  return (
    s.includes('receiving end') ||
    s.includes('could not establish connection') ||
    s.includes('message port closed') ||
    s.includes('extension context invalidated')
  );
}

async function runExtraction(tab) {
  if (!tab?.id) return null;

  let url = String(tab.url || '');
  try {
    const live = await chrome.tabs.get(tab.id);
    url = String(live.url || url);
  } catch {
    /* keep url from caller */
  }
  let lastOk = null;
  let lastErr = '';

  /**
   * LinkedIn: do NOT rely on content.js being attached (tab predates install, bfcache, races).
   * Programmatic inject is authoritative — avoids “Could not establish connection. Receiving end does not exist.”
   */
  if (isLinkedInHost(url)) {
    const delays = [0, 450, 1200, 2400];
    for (let i = 0; i < delays.length; i++) {
      if (delays[i]) await sleep(delays[i] - (delays[i - 1] ?? 0));
      try {
        let liveUrl = url;
        try {
          liveUrl = String((await chrome.tabs.get(tab.id)).url || url);
        } catch {
          /* use url */
        }
        if (!isLinkedInHost(liveUrl) || !isLinkedInProfile(liveUrl)) {
          lastErr =
            'That tab left the LinkedIn profile page before scraping finished. Go back to linkedin.com/in/… on that tab, then try again.';
          break;
        }
        const d = await injectAndExtract(tab.id, { requireLinkedInProfile: true });
        if (d && !d.error) {
          lastOk = d;
          if (extractionIsSubstantial(d)) return d;
        } else if (d?.error) lastErr = String(d.error);
      } catch (e) {
        lastErr = String(e?.message ?? e);
      }
    }
    if (lastOk) return lastOk;
    return {
      success: false,
      extracted_ok: false,
      fullText: '',
      error:
        lastErr ||
        `Could not inject into the LinkedIn tab (${url || 'unknown'}). ` +
        'Close this popup, click the LinkedIn profile tab so it is focused, then click the RezumeAI icon again. ' +
        'If it persists: chrome://extensions → Reload RezumeAI, then hard-refresh LinkedIn (Ctrl+Shift+R).',
    };
  }

  /* Non-LinkedIn: optional message bridge if a content script is present */
  const delays = [0, 500, 1100];
  for (let i = 0; i < delays.length; i++) {
    if (delays[i]) await sleep(delays[i] - (delays[i - 1] ?? 0));
    try {
      const d = await new Promise((resolve, reject) => {
        chrome.tabs.sendMessage(
          tab.id,
          { action: 'extract_profile', rescanOnly: i > 0 },
          res => {
            const err = chrome.runtime.lastError;
            if (err) reject(new Error(err.message));
            else resolve(res ?? null);
          },
        );
      });
      if (!d) continue;
      if (d.error) {
        lastErr = String(d.error);
        continue;
      }
      lastOk = d;
      return d;
    } catch (e) {
      lastErr = String(e?.message ?? e);
      if (isNoReceiverError(lastErr)) {
        try {
          const d = await injectAndExtract(tab.id);
          if (d && !d.error) return d;
          if (d?.error) lastErr = String(d.error);
        } catch (ie) {
          lastErr = [lastErr, String(ie?.message ?? ie)].filter(Boolean).join(' | ');
        }
        break;
      }
    }
  }

  return {
    success: false,
    extracted_ok: false,
    fullText: '',
    error: lastErr || 'No extractor for this page type.',
  };
}

/** Classified sections UI (About / Experience+skills / Education) */
function renderClassifiedPanel(pj) {
  const panel = $('classified-panel');
  if (!panel) return;
  if (!pj?.role_sections) {
    panel.classList.add('hidden');
    return;
  }
  panel.classList.remove('hidden');
  const rs = pj.role_sections;
  const pills = $('role-pills');
  if (pills) {
    const xpN = rs.experience?.length || 0;
    const nChipSkills = Array.isArray(pj.skills) ? pj.skills.length : 0;
    const nRoleSkills = rs.skills?.length || 0;
    const expSkillsItems = xpN + (nChipSkills || nRoleSkills);
    pills.innerHTML = [
      ['About', rs.about?.length || 0],
      ['Education', rs.education?.length || 0],
      ['Experience & skills', expSkillsItems],
    ]
      .map(([l, n]) => `<span class="role-pill">${esc(l)} <strong>${n}</strong></span>`)
      .join('');
  }
  const setBlocks = (id, arr) => {
    const el = $(id);
    if (!el) return;
    const t = (arr || []).join('\n\n').trim();
    el.textContent = t || '—';
    el.style.whiteSpace = 'pre-wrap';
  };
  setBlocks('sec-about', rs.about);
  setBlocks('sec-education', rs.education);

  const combo = $('sec-exp-skills');
  if (!combo) return;
  combo.replaceChildren();
  combo.className = 'role-card-body';
  const xpText = (rs.experience || []).join('\n\n').trim();
  const chipSkills = Array.isArray(pj.skills) ? pj.skills : [];
  if (xpText) {
    const d = document.createElement('div');
    d.className = 'exp-skills-text';
    d.textContent = xpText;
    combo.appendChild(d);
  }
  if (chipSkills.length) {
    const wrap = document.createElement('div');
    wrap.className = 'role-skills-chips';
    if (xpText) wrap.style.marginTop = '6px';
    for (const s of chipSkills.slice(0, 40)) {
      const span = document.createElement('span');
      span.className = 'chip-skill';
      span.textContent = String(s ?? '').trim();
      if (span.textContent) wrap.appendChild(span);
    }
    combo.appendChild(wrap);
  } else {
    const roleSkillLines = (rs.skills || []).join('\n\n').trim();
    if (roleSkillLines) {
      const d = document.createElement('div');
      d.className = 'exp-skills-text';
      if (xpText) d.style.marginTop = '6px';
      d.style.whiteSpace = 'pre-wrap';
      d.textContent = roleSkillLines;
      combo.appendChild(d);
    }
  }
  if (!combo.childNodes.length) combo.textContent = '—';
}

/** Fill form fields from extractor payload (name, title, skills, email when visible, fullText, etc.) */
function fillForm(d) {
  if (!d) return;
  G.lastProfileJson = d.profile_json || null;
  const pj = d.profile_json;
  const set = (id, v) => {
    const el = $(id);
    if (!el || v == null) return;
    const s = typeof v === 'number' ? String(v) : String(v).trim();
    if (s) el.value = s;
  };
  if (pj?.identity) {
    const id = pj.identity;
    set('c-name',     id.full_name || d.name);
    set('c-title',    id.headline || d.title);
    set('c-location', id.location || d.location);
    set('c-email',    id.email || d.email);
  } else {
    set('c-name',     d.name);
    set('c-title',    d.title);
    set('c-location', d.location);
    set('c-email',    d.email);
  }
  const canon = d.candidate_text_canonical || d.fullText;
  set('c-text', canon);
  if (pj?.skills?.length) {
    const joined = pj.skills.join(', ');
    const sk = $('c-skills');
    const skCur = String(sk?.value ?? '').trim();
    if (sk && (!skCur || joined.length >= skCur.length)) sk.value = joined;
  } else {
    set('c-skills', d.skills);
  }

  const emailHint = $('c-email-hint');
  if (emailHint) {
    const has = String(d.email || '').trim().length > 0;
    const msg = has ? '' : String(d.email_hint || '').trim();
    if (msg) {
      emailHint.textContent = msg;
      emailHint.hidden = false;
    } else {
      emailHint.textContent = '';
      emailHint.hidden = true;
    }
  }
  const yExp = pj?.metrics?.years_experience ?? d.years_experience;
  if (yExp != null && !Number.isNaN(+yExp))
    set('c-years', Math.round(+yExp * 10) / 10);
  const deg = normalizeDegree(pj?.metrics?.highest_degree || d.highest_degree);
  if (deg) { const el = $('c-degree'); if (el) el.value = deg; }

  if (d.certifications) {
    const existing = val('c-skills').toLowerCase();
    let certParts = [];
    if (Array.isArray(d.certifications)) {
      certParts = d.certifications;
    } else if (typeof d.certifications === 'string') {
      certParts = d.certifications.includes('\n')
        ? d.certifications.split(/\n+/)
        : d.certifications.split(',');
    }
    const certs = certParts
      .map(c => String(c ?? '').trim())
      .filter(c => c && !existing.includes(c.toLowerCase()));
    if (certs.length) {
      const sk = $('c-skills');
      if (sk) sk.value = [val('c-skills'), ...certs].filter(Boolean).join(', ');
    }
  }

  updateCharCount();
  syncCandSummary();
  if (d.email || pj?.identity?.email) scheduleCheckDuplicate();

  const meta = $('cand-meta-disp');
  if (meta) {
    const bits = [];
    if (d.scrape_chars) bits.push(`${(d.scrape_chars / 1000).toFixed(1)}k chars scraped`);
    if (d.pipeline_version) bits.push(`v${d.pipeline_version}`);
    meta.textContent = bits.join(' · ');
  }
  renderClassifiedPanel(pj);
}

// ── Form helpers ──────────────────────────────────────────────────────
function syncCandSummary() {
  const name  = val('c-name')  || '—';
  const title = val('c-title') || '—';
  const el    = $('cand-name-disp');
  const et    = $('cand-title-disp');
  const av    = $('cand-avatar');
  if (el) el.textContent = name;
  if (et) et.textContent = title;
  if (av) av.textContent = (name !== '—' ? name[0] : '?').toUpperCase();
}

function updateCharCount() {
  const len = (val('c-text')).length;
  const el  = $('char-count');
  if (el) el.textContent = `${len.toLocaleString()} chars`;
}

const DEGREE_MAP = [
  [/ph\.?d|doctor/i,                   'phd'],
  [/mba|master|m\.?s\.?\b|msc|m\.?eng/i, 'masters'],
  [/bachelor|b\.?s\.?\b|b\.?e\.?\b|b\.?sc|b\.?tech|b\.?eng|\bba\b/i, 'bachelors'],
  [/associate|diploma|certificate|a-level/i, 'intermediate'],
];

function normalizeDegree(raw) {
  const s = String(raw ?? '').trim().toLowerCase();
  if (!s) return '';
  if (['phd','masters','bachelors','intermediate'].includes(s)) return s;
  for (const [re, label] of DEGREE_MAP) if (re.test(s)) return label;
  return '';
}

/** Parse structured fields from blob text (Name:, Skills: headers) */
function parseProfileText() {
  const text = val('c-text');
  if (!text) return;
  const setIfEmpty = (id, v) => {
    const el = $(id);
    if (el && !String(el.value ?? '').trim() && v) el.value = v;
  };
  const line = re => {
    const m = text.match(re);
    return m && m[1] != null ? String(m[1]).trim() : '';
  };
  setIfEmpty('c-name',     line(/^Name:\s*(.+)$/im));
  setIfEmpty('c-title',    line(/^Current[_ ]?Title:\s*(.+)$/im));
  setIfEmpty('c-location', line(/^Location:\s*(.+)$/im));
  setIfEmpty('c-email',    line(/^Email:\s*(.+)$/im));
  const skillsLine = line(/^Skills:\s*(.+)$/im);
  if (skillsLine) setIfEmpty('c-skills', skillsLine);
  const yearsLine = line(/^Years[_ ]?of[_ ]?Experience:\s*([\d.]+)/im);
  if (yearsLine) setIfEmpty('c-years', yearsLine);
  const degLine = line(/^Highest[_ ]?Degree:\s*(.+)$/im);
  if (degLine) {
    const d = normalizeDegree(degLine);
    const el = $('c-degree');
    if (el && !el.value && d) el.value = d;
  }
  syncCandSummary();
}

function clearForm() {
  ['c-name','c-email','c-title','c-location','c-skills','c-text','c-url','c-years']
    .forEach(id => { const el = $(id); if (el) el.value = ''; });
  const eh = $('c-email-hint');
  if (eh) { eh.textContent = ''; eh.hidden = true; }
  const deg = $('c-degree'); if (deg) deg.value = '';
  updateCharCount();
  syncCandSummary();
  hide('dup-banner','dup-preview','results-card','save-actions','classified-panel','pipeline-ready');
  const meta = $('cand-meta-disp');
  if (meta) meta.textContent = '';
  showAlert('step1-err', '');
  showAlert('analyze-err', '');
  G.lastResult         = null;
  G.savedCandId        = null;
  G.lastProfileJson    = null;
}

// ── Duplicate check ───────────────────────────────────────────────────
let _dupTimer = null;
function scheduleCheckDuplicate() {
  clearTimeout(_dupTimer);
  _dupTimer = setTimeout(checkDuplicate, 600);
}

async function checkDuplicate() {
  const email = val('c-email');
  const url   = val('c-url');
  hide('dup-banner');
  if (!email && !url) return;

  try {
    let endpoint = '';
    if (email) endpoint = `/api/v1/candidates/page?skip=0&limit=1&q=${encodeURIComponent(email)}`;
    else return;
    const data = await api('GET', endpoint);
    const items = data.items || [];
    if (!items.length) return;
    const c = items[0];
    const dupText = $('dup-text');
    if (dupText) dupText.textContent = `Already in pool: ${c.full_name || c.external_id}`;
    const dupView = $('dup-view');
    if (dupView) dupView.onclick = () => chrome.tabs.create({ url: `${G.apiBase.replace(':8000',':5173')}/candidates/${c.external_id}` });
    show('dup-banner');
  } catch { /* silent */ }
}

// ── Jobs ──────────────────────────────────────────────────────────────
async function loadJobs() {
  const sel = $('job-select');
  if (!sel) return;
  sel.innerHTML = '<option value="">Loading…</option>';
  sel.disabled  = true;
  try {
    const data = await api('GET', '/api/v1/jobs/page?skip=0&limit=100&status=active&sort=created_at_desc');
    const jobs = data.items || [];
    if (!jobs.length) {
      sel.innerHTML = '<option value="">No active jobs found</option>';
      return;
    }
    sel.innerHTML =
      '<option value="">— Select a job —</option>' +
      jobs.map(j => `<option value="${esc(j.external_id)}">${esc(j.title || 'Untitled')} (${esc(j.external_id)})</option>`).join('');
    sel.disabled = false;
  } catch (e) {
    sel.innerHTML = `<option value="">Failed: ${esc(e.message)}</option>`;
  }
}

// ── Context + LinkedIn Grab profile + optional auto-extract ───────────
async function detectContext() {
  try {
    const tab = await getRelevantTab();
    if (!tab?.url) return;

    const onProfile = isLinkedInProfile(tab.url);
    const onDetails = isLinkedInDetailsSubpage(tab.url);
    const btn = $('btn-grab-linkedin');
    if (btn) {
      btn.disabled = !isLinkedInHost(tab.url);
      btn.title    = onProfile
        ? onDetails
          ? 'Optional refresh — for full About, open: ' + linkedInMemberBaseProfileUrl(tab.url)
          : 'Optional manual re-scrape of this tab'
        : 'Open a LinkedIn /in/… profile tab for automatic extract';
    }

    if (onProfile) {
      const urlEl = $('c-url');
      if (urlEl && !String(urlEl.value ?? '').trim()) urlEl.value = tab.url;
      const msgEl = $('auto-extract-msg');
      if (msgEl) msgEl.textContent = 'Scraping page & classifying sections…';
      await autoExtract(tab);
    }
  } catch { /* ignore */ }
}

function setBanner(on) {
  const b = $('auto-extract-banner');
  b?.classList.toggle('hidden', !on);
}

async function autoExtract(tab) {
  hide('pipeline-ready');
  const msgEl = $('auto-extract-msg');
  let d = null;
  setBanner(true);
  showAlert('step1-err', '');
  if (msgEl) msgEl.textContent = 'Scraping visible page → classifying About / Experience & skills / Education…';
  try {
    d = await runExtraction(tab);
    if (!d) {
      showAlert(
        'step1-err',
        'No data from this tab. Stay on the LinkedIn profile, hard-refresh (Ctrl+Shift+R), reload the extension, then try again.',
        'error',
      );
      fillMinFromLinkedInTab(tab);
      return;
    }
    if (d.error) {
      showAlert('step1-err', String(d.error), 'error');
      fillMinFromLinkedInTab(tab);
      return;
    }
    if (extractionIsUsable(d)) {
      fillForm(d);
    } else {
      showAlert(
        'step1-err',
        'LinkedIn returned very little text (selectors may have changed, or the profile did not finish loading). Scroll the full profile, wait a few seconds, then reopen the extension — or use Refresh scrape.',
        'error',
      );
      fillForm(d);
      fillMinFromLinkedInTab(tab);
    }
  } catch (e) {
    showAlert('step1-err', e?.message || String(e), 'error');
    fillMinFromLinkedInTab(tab);
  } finally {
    setBanner(false);
    if (d && extractionIsUsable(d)) {
      show('pipeline-ready');
      const prt = $('pipeline-ready-text');
      if (prt) {
        const sc = d.scrape_chars ? `${(d.scrape_chars / 1000).toFixed(1)}k chars scraped` : 'Page processed';
        prt.textContent = `Profile ready · ${sc}`;
      }
    }
  }
}

async function grabLinkedIn() {
  showAlert('step1-err', '');
  const btn = $('btn-grab-linkedin');
  if (btn) btn.disabled = true;
  setBanner(true);
  try {
    const tab = await getRelevantTab();
    if (!tab?.id) throw new Error('No suitable tab found. Focus a LinkedIn profile tab, then open this popup again.');
    if (!isLinkedInHost(tab.url ?? ''))
      throw new Error('Switch to a LinkedIn tab first.');
    const d = await runExtraction(tab);
    if (!d) throw new Error('No data returned from the page.');
    if (d.error) throw new Error(d.error);
    fillForm(d);
    const urlEl = $('c-url');
    if (urlEl && !urlEl.value && tab.url) urlEl.value = tab.url;
    if (!extractionIsUsable(d)) {
      fillMinFromLinkedInTab(tab);
      const hint =
        isLinkedInDetailsSubpage(tab.url || '')
          ? ` Open the main profile: ${linkedInMemberBaseProfileUrl(tab.url)}`
          : '';
      showAlert(
        'step1-err',
        'Partial read — scroll About, experience, and skills on the profile overview, wait a moment, then click Refresh scrape or reopen the extension.' + hint,
        'error',
      );
    } else {
      const chars = val('c-text').length;
      let msg = `Loaded ${chars.toLocaleString()} chars from LinkedIn`;
      if (isLinkedInDetailsSubpage(tab.url || ''))
        msg += `. For full About, open: ${linkedInMemberBaseProfileUrl(tab.url)}`;
      showAlert('step1-err', msg, 'success');
      setTimeout(() => showAlert('step1-err', ''), 4000);
    }
  } catch (e) {
    showAlert('step1-err', e.message);
    try {
      const t = await getRelevantTab();
      if (t) fillMinFromLinkedInTab(t);
    } catch { /* ignore */ }
  } finally {
    setBanner(false);
    await detectContext();
  }
}

// ── Match preview API ─────────────────────────────────────────────────
async function fetchMatchPreview(jobId) {
  const text = clipStr(val('c-text'), 100000).trim();
  const skills = skillsForMatchApi();
  if (!text && !skills)
    throw new Error('No profile text yet. Stay on a LinkedIn /in/ profile until “Profile ready” appears.');
  // API requires min_length 10; main narrative in candidate_text, structured skills in candidate_skills.
  const merged = [text, skills].filter(Boolean).join('\n\n').trim();
  if (merged.length < 10)
    throw new Error('Profile text is too short to match (need at least 10 characters). Scroll the profile and scrape again, or add a “Skills:” line in the text box.');
  const jid = clipStr(String(jobId || '').trim(), 64);
  if (!jid) throw new Error('No job selected.');
  const body = {
    job_id:             jid,
    candidate_text:     clipStr(text || merged, 120000),
    candidate_name:     clipStr(val('c-name'), 512) || undefined,
    candidate_title:    clipStr(val('c-title'), 512) || undefined,
    candidate_skills:   skills || undefined,
    candidate_email:    clipStr(val('c-email'), 320) || undefined,
    candidate_location: clipStr(val('c-location'), 256) || undefined,
    years_experience:   optionalYears('c-years'),
    highest_degree:     clipStr(val('c-degree'), 256) || undefined,
    profile_url:        clipStr(val('c-url'), 1024) || undefined,
  };
  for (const k of Object.keys(body)) if (body[k] === undefined) delete body[k];
  return api('POST', '/api/v1/match/preview', body);
}

// ── Preview match only ───────────────────────────────────────────────
async function analyzeMatch() {
  const jobId = val('job-select') || $('job-select')?.value;
  if (!jobId) { showAlert('analyze-err', 'Select a job first.'); return; }

  showAlert('analyze-err', '');
  hide('results-card', 'save-actions', 'dup-preview');
  syncCandSummary();

  const analyzeBtn   = $('btn-analyze');
  const analyzeLabel = $('analyze-label');
  const analyzeSpinner = $('analyze-spinner');
  if (analyzeBtn)    analyzeBtn.disabled   = true;
  if (analyzeLabel)  analyzeLabel.textContent = 'Matching…';
  if (analyzeSpinner) analyzeSpinner.classList.remove('hidden');

  try {
    const result = await fetchMatchPreview(jobId);
    G.lastResult    = result;
    G.selectedJobId = jobId;
    renderResults(result);
    show('results-card', 'save-actions');
    $('results-card')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) {
    showAlert('analyze-err', e.message);
  } finally {
    if (analyzeBtn)    analyzeBtn.disabled    = false;
    if (analyzeLabel)  analyzeLabel.textContent = 'Preview match only';
    if (analyzeSpinner) analyzeSpinner.classList.add('hidden');
  }
}

// ── Match + save to RezumeAI (ingest + job match row) ─────────────────
async function matchAndSaveToDashboard() {
  const jobId = val('job-select') || $('job-select')?.value;
  if (!jobId) { showAlert('analyze-err', 'Select a job first.'); return; }

  showAlert('analyze-err', '');
  hide('dup-preview');

  const btn   = $('btn-match-save');
  const lbl   = $('match-save-label');
  const spin  = $('match-save-spinner');
  if (btn)   btn.disabled = true;
  if (lbl)   lbl.textContent = 'Matching…';
  if (spin)  spin.classList.remove('hidden');

  try {
    const result = await fetchMatchPreview(jobId);
    G.lastResult    = result;
    G.selectedJobId = jobId;
    renderResults(result);
    show('results-card');
    hide('save-actions');
    if (lbl) lbl.textContent = 'Saving to pool…';
    await saveCandidate(true);
  } catch (e) {
    showAlert('analyze-err', e.message);
  } finally {
    if (btn)   btn.disabled = false;
    if (lbl)   lbl.textContent = 'Match & save to dashboard';
    if (spin)  spin.classList.add('hidden');
  }
}

// ── Render results card ───────────────────────────────────────────────
function renderResults(r) {
  const pct    = Math.round(Number(r.match_score) || 0);
  const circum = 2 * Math.PI * 34;

  // Score number
  const sp = $('score-pct');
  if (sp) sp.textContent = String(pct);

  const headline = $('score-headline');
  if (headline) {
    const pos = r.ranking_position;
    const n = r.total_ranked;
    const wsPool = r.pool_ranking_scope === 'workspace_pool';
    if (pos != null && n >= 0 && (wsPool || n > 0)) {
      const label = wsPool ? 'workspace' : 'saved';
      headline.textContent = `${pct}% match · #${pos} of ${n + 1} (${label} pool)`;
    } else {
      headline.textContent = `${pct}% match`;
    }
  }

  // Animated ring
  const ring = $('ring-fill');
  if (ring) {
    const color  = pct >= 70 ? '#3ecf8e' : pct >= 45 ? '#fbbf24' : '#f87171';
    ring.style.stroke           = color;
    ring.style.strokeDashoffset = String(circum);
    setTimeout(() => {
      ring.style.strokeDashoffset = String(circum - (pct / 100) * circum);
    }, 60);
  }

  // Badge: Strong / Medium / Weak
  const badge = $('score-badge');
  if (badge) {
    const lbl = (r.match_label || 'Unknown').toLowerCase();
    badge.textContent = r.match_label || '—';
    badge.className   = `score-badge badge-${lbl}`;
  }

  // Ranking position
  const ri = $('rank-info');
  if (ri) {
    const capNote = r.pool_capped ? ' Sample capped for API speed.' : '';
    if (r.pool_ranking_scope === 'workspace_pool') {
      if (r.total_ranked > 0) {
        ri.textContent = `Rank #${r.ranking_position} of ${r.total_ranked + 1} scored profiles in your workspace.${capNote}`;
      } else {
        ri.textContent = `No other scored profiles in this workspace — #1 of 1.${capNote}`;
      }
    } else if (r.total_ranked > 0) {
      ri.textContent = `Rank #${r.ranking_position} of ${r.total_ranked + 1} saved job rankings (recruiter sign-in uses full workspace pool).`;
    } else {
      ri.textContent = 'First ranked candidate for this job';
    }
  }

  const jn = $('job-name-disp');
  if (jn) jn.textContent = r.job_title ? `Job: ${r.job_title}` : '';

  // Breakdown bars
  const bd = r.breakdown || {};
  setBar('bar-skills',   'val-skills',   bd.skills_overlap);
  setBar('bar-critical', 'val-critical', bd.critical_skill_coverage);
  setBar('bar-exp',      'val-exp',      bd.experience_match);
  setBar('bar-edu',      'val-edu',      bd.education_match);
  setBar('bar-title',    'val-title',    bd.title_relevance);

  // Skill chips
  renderChips('matching-skills', r.matching_skills        || [], 'chip-match');
  renderChips('missing-skills',  r.missing_skills         || [], 'chip-missing');

  const crit = r.missing_critical_skills || [];
  const cb   = $('critical-skills-block');
  if (crit.length) {
    renderChips('critical-skills', crit, 'chip-missing');
    cb?.classList.remove('hidden');
  } else {
    cb?.classList.add('hidden');
  }

  // Duplicate detection banner
  const dp = $('dup-preview');
  if (dp) {
    if (r.duplicate) {
      const prev = r.duplicate.existing_match_score != null
        ? ` · previous best match ${r.duplicate.existing_match_score}%`
        : '';
      dp.textContent = `Already in pool: ${r.duplicate.full_name || r.duplicate.external_id}${prev}. You can still save or skip.`;
      show('dup-preview');
    } else {
      hide('dup-preview');
      dp.textContent = '';
    }
  }
}

function setBar(barId, valId, rawVal) {
  const pctVal = Math.round((rawVal || 0) * 100);
  const color  = pctVal >= 70 ? '#3ecf8e' : pctVal >= 45 ? '#fbbf24' : '#f87171';
  const bar    = $(barId);
  const valEl  = $(valId);
  if (bar) {
    bar.style.width      = '0%';
    bar.style.background = color;
    setTimeout(() => { bar.style.width = `${pctVal}%`; }, 60);
  }
  if (valEl) valEl.textContent = `${pctVal}%`;
}

function renderChips(containerId, skills, cls) {
  const el = $(containerId);
  if (!el) return;
  if (!skills.length) {
    el.innerHTML = '<span style="color:var(--text-muted);font-size:11px">—</span>';
    return;
  }
  el.innerHTML = skills.slice(0, 18).map(s => `<span class="chip ${cls}">${esc(s)}</span>`).join('');
}

// ── Save candidate (optional step after analysis) ─────────────────────
function buildSaveText() {
  let body = val('c-text') || skillsForMatchApi() || '(no text)';
  const name   = val('c-name');
  const title  = val('c-title');
  const loc    = val('c-location');
  const email  = val('c-email');
  const skills = skillsForMatchApi();
  const header = [];
  if (name   && !/^Name:\s/im.test(body))   header.push(`Name: ${name}`);
  if (title)                                 header.push(`Current Title: ${title}`);
  if (loc)                                   header.push(`Location: ${loc}`);
  if (email)                                 header.push(`Email: ${email}`);
  if (skills && !/^Skills:\s/im.test(body)) header.push(`Skills: ${skills}`);
  return header.length ? `${header.join('\n')}\n\n${body}` : body;
}

async function saveCandidate(attachToJob) {
  const sb = $('btn-save-only');
  const sm = $('btn-save-match');
  const bms = $('btn-match-save');
  if (sb) sb.disabled = true;
  if (sm) sm.disabled = true;
  if (bms) bms.disabled = true;

  try {
    // 1. Ingest the profile text
    const ingestion = await api('POST', '/api/v1/ingestions/text', {
      text:     buildSaveText(),
      source:   'extension',
      filename: (val('c-name') || 'candidate') + '.txt',
    });

    // 2. Poll until done (max 15 s)
    let extId = ingestion.candidate_external_id || null;
    if (ingestion.status !== 'done') {
      for (let i = 0; i < 15; i++) {
        await sleep(1000);
        try {
          const st = await api('GET', `/api/v1/ingestions/batch/${ingestion.batch_id}`);
          const row = (st.items || []).find(x => x.id === ingestion.id);
          if (row?.status === 'done') { extId = row.candidate_external_id; break; }
          if (row?.status === 'failed') throw new Error(row.error || 'Ingestion failed.');
        } catch (e) {
          if (String(e.message).includes('failed')) throw e;
        }
      }
    }

    G.savedCandId = extId;

    // 3. Optionally persist match vs selected job (same cross-encoder path as the app)
    let matchPersistNote = '';
    if (attachToJob && G.selectedJobId && extId) {
      try {
        // Must mirror POST /match/preview: server builds cross-encoder input as
        // title + skills + candidate_text_for_match. Do NOT repeat title/skills here
        // (that was inflating/deflating scores vs the extension preview).
        const profileBlob = String(val('c-text') || skillsForMatchApi() || '').trim();
        const yRaw = val('c-years');
        const payload = {
          candidate_external_id: extId,
          candidate_text_for_match: profileBlob.length >= 10 ? profileBlob : undefined,
          candidate_title: val('c-title') || undefined,
          candidate_skills: skillsForMatchApi() || undefined,
          highest_degree: val('c-degree') || undefined,
        };
        if (yRaw !== '') {
          const y = parseFloat(yRaw);
          if (!Number.isNaN(y)) payload.years_experience = y;
        }
        await api('POST', `/api/v1/jobs/${G.selectedJobId}/match-candidate-save`, payload);
      } catch (e) {
        matchPersistNote = ` Match score was not saved to the job (${e.message}). You can run matching from the job in the web app.`;
      }
    }

    // 4. Success screen
    const title = $('confirm-title');
    const msg   = $('confirm-msg');
    if (title) title.textContent = 'Candidate Saved';
    if (msg) {
      const name = val('c-name') || extId || 'Candidate';
      const jobPart = attachToJob && G.lastResult
        ? ` and matched to job (${Math.round(G.lastResult.match_score)}% preview)`
        : '';
      msg.textContent = `${name} added to the pool${jobPart}.${matchPersistNote}`;
    }
    showStep(3);
  } catch (e) {
    showAlert('step1-err', e.message);
    if (sb) sb.disabled = false;
    if (sm) sm.disabled = false;
    if (bms) bms.disabled = false;
  }
}

// ── Event wiring ──────────────────────────────────────────────────────
function wireEvents() {
  // Login
  $('btn-login')?.addEventListener('click', async () => {
    showAlert('l-err', '');
    const email = val('l-email'), password = $('l-pass')?.value;
    if (!email || !password) { showAlert('l-err', 'Email and password required.'); return; }
    setBtn('btn-login', true);
    try {
      await login(email, password);
      showView('main');
      checkHealth();
      loadJobs();
      detectContext();
      syncCandSummary();
    } catch (e) { showAlert('l-err', e.message); }
    finally { setBtn('btn-login', false); }
  });
  $('l-pass')?.addEventListener('keydown', e => { if (e.key === 'Enter') $('btn-login')?.click(); });

  // Logout / settings
  $('btn-logout')?.addEventListener('click', logout);
  $('btn-settings')?.addEventListener('click', () => chrome.runtime.openOptionsPage());

  $('btn-grab-linkedin')?.addEventListener('click', grabLinkedIn);
  $('btn-clear')?.addEventListener('click', clearForm);

  // Profile text: parse fields button
  $('btn-parse-fields')?.addEventListener('click', () => {
    showAlert('step1-err', '');
    parseProfileText();
    showAlert('step1-err', 'Fields updated from profile text', 'success');
    setTimeout(() => showAlert('step1-err', ''), 2500);
  });

  // Char counter + auto-sync avatar
  $('c-text')?.addEventListener('input', updateCharCount);
  ['c-name','c-title'].forEach(id => $(`${id}`)?.addEventListener('input', syncCandSummary));
  $('c-email')?.addEventListener('blur', scheduleCheckDuplicate);

  // Jobs
  $('btn-reload-jobs')?.addEventListener('click', loadJobs);

  $('btn-match-save')?.addEventListener('click', () => void matchAndSaveToDashboard());
  $('btn-analyze')?.addEventListener('click', analyzeMatch);

  // Clear result / pick another job
  $('btn-reanalyze')?.addEventListener('click', () => {
    hide('results-card', 'save-actions');
    showAlert('analyze-err', '');
    G.lastResult = null;
  });

  // Save actions
  $('btn-save-only')?.addEventListener('click',  () => saveCandidate(false));
  $('btn-save-match')?.addEventListener('click', () => saveCandidate(true));
  $('btn-skip')?.addEventListener('click', () => {
    clearForm();
    showStep(1);
  });

  // Confirmation screen
  $('btn-new-candidate')?.addEventListener('click', () => {
    clearForm();
    showStep(1);
    void detectContext();
  });
  $('btn-open-app')?.addEventListener('click', () => {
    const frontendBase = G.apiBase.replace(':8000', ':5173');
    chrome.tabs.create({ url: G.savedCandId
      ? `${frontendBase}/candidates/${G.savedCandId}`
      : frontendBase,
    });
  });
}

// ── Init ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get([SK.TOKEN, SK.EMAIL, SK.API_BASE, SK.ROLE]);
  G.apiBase = stored[SK.API_BASE] || DEFAULT_API;
  G.token   = stored[SK.TOKEN]   || null;
  G.email   = stored[SK.EMAIL]   || '';

  wireEvents();
  checkHealth();

  if (G.token) {
    showView('main');
    showStep(1);
    syncCandSummary();
    loadJobs();
    detectContext();
  } else {
    showView('login');
  }
});
