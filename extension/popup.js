/* ============================================================
   RezumeAI Chrome Extension — Full Popup Script
   Covers: auth, structured extraction, real-time ranking,
           duplicate detection, save & attach to job.
   ============================================================ */

'use strict';

// ── Storage keys ─────────────────────────────────────────────
const SK = { TOKEN: 'rezume_token', EMAIL: 'rezume_email', API_BASE: 'rezume_api_base', ROLE: 'rezume_role' };

// ── Global state ─────────────────────────────────────────────
const G = {
  apiBase:       'http://127.0.0.1:8000',
  token:         null,
  email:         '',
  lastResult:    null,   // last preview response
  selectedJobId: null,   // currently selected job external_id
  savedCandId:   null,   // external_id of saved candidate
};

// ── DOM helpers ───────────────────────────────────────────────
const $   = id => document.getElementById(id);
const show = (...ids) => ids.forEach(id => $(id)?.classList.remove('hidden'));
const hide = (...ids) => ids.forEach(id => $(id)?.classList.add('hidden'));

function setBtn(id, loading, loadingLabel) {
  const btn = $(id);
  if (!btn) return;
  btn.disabled = loading;
  const spinner = btn.querySelector('.spinner');
  const label   = btn.querySelector('.btn-label') || btn.querySelector('span:not(.spinner)');
  if (spinner) spinner.classList.toggle('hidden', !loading);
  if (label && loadingLabel) label.textContent = loading ? loadingLabel : label.dataset.orig || label.textContent;
  if (label && !label.dataset.orig) label.dataset.orig = label.textContent;
}

function showAlert(id, msg, type = 'error') {
  const el = $(id);
  if (!el) return;
  el.textContent = msg || '';
  el.className   = `alert alert-${type}${msg ? '' : ' hidden'}`;
  if (!msg) el.classList.add('hidden');
}

// ── API helpers ───────────────────────────────────────────────
async function apiReq(method, path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  if (G.token) headers['Authorization'] = `Bearer ${G.token}`;
  const res  = await fetch(`${G.apiBase}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { detail: text }; }
  if (!res.ok) {
    const d = data?.detail || data?.error || res.statusText;
    throw new Error(typeof d === 'string' ? d : JSON.stringify(d));
  }
  return data;
}

// ── Auth ──────────────────────────────────────────────────────
async function login(email, password) {
  const data = await apiReq('POST', '/api/v1/auth/login', { email, password });
  if (data.requires_otp) throw new Error('OTP required — sign in via the web app first.');
  if (!data.access_token) throw new Error('No access token returned.');
  G.token = data.access_token; G.email = email;
  await chrome.storage.local.set({ [SK.TOKEN]: G.token, [SK.EMAIL]: email, [SK.API_BASE]: G.apiBase, [SK.ROLE]: data.account_role || 'recruiter' });
}

async function logout() {
  G.token = null; G.email = '';
  await chrome.storage.local.remove([SK.TOKEN, SK.EMAIL, SK.ROLE]);
  showView('login');
}

// ── Views & steps ─────────────────────────────────────────────
function showView(name) {
  ['login', 'main'].forEach(v => $(  `view-${v}`)?.classList.toggle('hidden', v !== name));
  if (name === 'main') $('user-email').textContent = G.email;
}

function goStep(n) {
  [1, 2, 3].forEach(i => {
    $(`step-${i}`)?.classList.toggle('active', i === n);
    $(`step-${i}`)?.classList.toggle('hidden', i !== n);
    const ind = $(`step-ind-${i}`);
    if (ind) {
      ind.classList.toggle('active', i === n);
      ind.classList.toggle('done',   i < n);
    }
  });
}

// ── Status dot ────────────────────────────────────────────────
function setDot(state, text) {
  const dot = $('status-dot'), txt = $('status-text');
  if (dot) dot.className = `status-dot ${state}`;
  if (txt) txt.textContent = text;
}

async function checkHealth() {
  setDot('checking', '…');
  try {
    const d = await apiReq('GET', '/health');
    setDot(d.status === 'ok' ? 'online' : 'warn', d.status === 'ok' ? 'Connected' : d.status);
  } catch { setDot('offline', 'Unreachable'); }
}

// ── Page context + LinkedIn extraction (content script) ───────
function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function detectContext() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url) return;
    const isLI = /linkedin\.com\/in\//i.test(tab.url);
    const btn = $('btn-grab-linkedin');
    if (btn) {
      btn.disabled = !isLI;
      btn.title = isLI ? 'Re-extract this LinkedIn profile' : 'Navigate to a LinkedIn /in/ profile first';
    }
    if (isLI) {
      const urlEl = $('c-url');
      if (urlEl && !urlEl.value) urlEl.value = tab.url;
      const nameOk = ($('c-name')?.value || '').trim().length > 1;
      const textOk = ($('c-text')?.value || '').trim().length > 200;
      if (!(nameOk && textOk)) await autoExtract(tab);
    }
  } catch { /* no activeTab yet */ }
}

/**
 * LinkedIn scraping runs inside the tab (extract_core.js + content.js).
 * Retries while the SPA renders; if messaging never connects, inject extract_core.js once.
 */
async function runLinkedInExtraction(tab) {
  if (!tab?.id) return null;

  const delays = [0, 400, 900, 1800, 3200, 5200];
  for (const ms of delays) {
    if (ms) await sleep(ms);
    try {
      const d = await new Promise((resolve, reject) => {
        chrome.tabs.sendMessage(tab.id, { action: 'extract_profile' }, response => {
          const err = chrome.runtime.lastError;
          if (err) reject(new Error(err.message));
          else resolve(response);
        });
      });
      if (d && d.success && (d.fullText || d.name || d.title)) return d;
      if (d && !d.success && d.error) return d;
    } catch { /* retry */ }
  }

  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['extract_core.js'] });
    const inj = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: async () => {
        if (typeof globalThis.__rezumeExtractLinkedInAsync === 'function') {
          return await globalThis.__rezumeExtractLinkedInAsync();
        }
        if (typeof globalThis.__rezumeExtractLinkedIn === 'function') {
          return globalThis.__rezumeExtractLinkedIn();
        }
        return null;
      },
    });
    return inj?.[0]?.result || null;
  } catch {
    return null;
  }
}

async function autoExtract(tab) {
  setAutoExtractState(true);
  showAlert('step1-err', '');
  try {
    const d = await runLinkedInExtraction(tab);
    if (d && !d.success && d.error) {
      showAlert('step1-err', d.error, 'error');
      return;
    }
    const text = (d?.fullText || '').trim();
    const hasCore =
      text.length > 15 || (d?.name || '').trim().length > 1 || (d?.title || '').trim().length > 1;
    if (d && d.success && hasCore) {
      fillCandidateForm(d);
      const who = (d.name || d.title || 'Candidate').trim();
      showAlert('step1-err', `Profile loaded: ${who}`, 'success');
      setTimeout(() => showAlert('step1-err', ''), 3500);
    } else {
      showAlert(
        'step1-err',
        'Could not read this profile yet. Reload the extension on chrome://extensions, refresh this LinkedIn tab, stay on an /in/… profile URL, scroll so About & Experience appear, then click “Grab LinkedIn”.',
        'error',
      );
    }
  } catch (e) {
    console.warn('[RezumeAI] Auto-extract failed:', e?.message);
    showAlert('step1-err', e?.message || 'Could not read the active LinkedIn tab.', 'error');
  } finally {
    setAutoExtractState(false);
  }
}

function setAutoExtractState(loading) {
  const banner = $('auto-extract-banner');
  if (banner) banner.classList.toggle('hidden', !loading);
}

async function grabLinkedIn() {
  showAlert('step1-err', '');
  const btn = $('btn-grab-linkedin');
  if (btn) btn.disabled = true;
  setAutoExtractState(true);
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error('No active tab.');
    const d = await runLinkedInExtraction(tab);
    if (d && !d.success && d.error) {
      throw new Error(d.error);
    }
    const text = (d?.fullText || '').trim();
    const hasCore =
      text.length > 15 || (d?.name || '').trim().length > 1 || (d?.title || '').trim().length > 1;
    if (!d || !d.success || !hasCore) {
      throw new Error('Could not read this profile. Stay on the LinkedIn /in/ page, scroll to load About & Experience, then try again.');
    }
    fillCandidateForm(d);
    const urlEl = $('c-url');
    if (urlEl && !urlEl.value) urlEl.value = tab.url;
    showAlert('step1-err', `Loaded ${($('c-text')?.value || '').length.toLocaleString()} characters`, 'success');
    setTimeout(() => showAlert('step1-err', ''), 3500);
  } catch (e) {
    showAlert('step1-err', e.message);
  } finally {
    setAutoExtractState(false);
    await detectContext();
  }
}

async function grabSelection() {
  showAlert('step1-err', '');
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const res = await chrome.scripting.executeScript({
      target: { tabId: tab.id }, func: () => window.getSelection().toString(),
    });
    const text = (res?.[0]?.result || '').trim();
    if (!text) throw new Error('No text selected. Highlight resume text on the page first.');
    $('c-text').value = text;
    updateCharCount();
    hydrateFormFromProfileText({ onlyIfEmpty: true });
  } catch (e) { showAlert('step1-err', e.message); }
}

function normalizeDegreeForSelect(raw) {
  const s = String(raw || '').trim().toLowerCase();
  if (!s) return '';
  if (['phd', 'masters', 'bachelors', 'intermediate'].includes(s)) return s;
  if (/ph\.?d|doctor/.test(s)) return 'phd';
  if (/mba|master|m\.?s\.?\b|msc|m\.?eng/.test(s)) return 'masters';
  if (/bachelor|b\.?s\.?\b|b\.?e\.?\b|b\.?sc|b\.?tech|b\.?eng|\bba\b/.test(s)) return 'bachelors';
  if (/associate|diploma|certificate|a-level|intermediate/.test(s)) return 'intermediate';
  return '';
}

/**
 * LinkedIn public URLs are often `first-last-6741a222a` where the last hyphen chunk
 * is an opaque id. Strip that chunk so we only show a readable candidate name.
 */
function humanNameFromLinkedInSlug(encodedSlug) {
  let slug = '';
  try {
    slug = decodeURIComponent(String(encodedSlug || '').trim()).replace(/\+/g, ' ');
  } catch {
    slug = String(encodedSlug || '').trim();
  }
  slug = slug.trim();
  if (!slug) return '';

  const parts = slug.split('-').map(p => p.trim()).filter(Boolean);
  if (!parts.length) return slug;

  function looksLikeOpaqueSuffix(seg) {
    const t = String(seg);
    if (t.length < 6 || t.length > 20) return false;
    if (!/^[a-zA-Z0-9]+$/.test(t)) return false;
    if (/^[a-f0-9]{6,12}$/i.test(t)) return true;
    if (/\d/.test(t) && t.length >= 6) return true;
    return false;
  }

  while (parts.length > 1 && looksLikeOpaqueSuffix(parts[parts.length - 1])) {
    parts.pop();
  }

  let out = parts.join(' ').replace(/\s+/g, ' ').trim();
  const words = out.split(/\s+/).filter(Boolean);
  while (words.length > 1 && looksLikeOpaqueSuffix(words[words.length - 1])) {
    words.pop();
  }
  return words.join(' ').trim();
}

/** Derive display name from a LinkedIn /in/slug URL. */
function nameFromLinkedInUrl(url) {
  const m = String(url || '').match(/\/in\/([^/?#]+)/i);
  if (!m) return '';
  return humanNameFromLinkedInSlug(m[1]);
}

/**
 * Parse our exported profile blob (and common variants) into structured fields.
 */
function parseProfileTextIntoFields(text) {
  const t = String(text || '');
  const line = re => {
    const m = t.match(re);
    return m ? m[1].replace(/\s+/g, ' ').trim() : '';
  };
  const out = {};
  out.name = line(/^Name:\s*(.+)$/im) || line(/^Name \(from profile URL\):\s*(.+)$/im);
  out.title = line(/^Current Title:\s*(.+)$/im) || line(/^Headline:\s*(.+)$/im);
  out.location = line(/^Location:\s*(.+)$/im);
  out.email = line(/^Email:\s*(.+)$/im);
  const yrs = t.match(/^Years of Experience:\s*([\d.]+)\s*$/im);
  if (yrs) {
    const n = parseFloat(yrs[1]);
    if (!Number.isNaN(n)) out.years = n;
  }
  const deg = line(/^Highest Degree:\s*(.+)$/im);
  if (deg) out.degreeRaw = deg;

  const sm = t.match(/\nSKILLS\s*\n([\s\S]*?)(?=\n\n|\n(?:CERTIFICATIONS|WORK EXPERIENCE|EDUCATION|LANGUAGES|PROJECTS|VOLUNTEER)|$)/i);
  if (sm) {
    const body = sm[1].trim();
    out.skills = body
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean)
      .join(', ')
      .replace(/\s*,\s*/g, ', ');
  }
  return out;
}

/**
 * Copy parsed values from Profile Text into the form (optionally only where inputs are still empty).
 * @param {{ onlyIfEmpty?: boolean }} opts
 */
function hydrateFormFromProfileText(opts = {}) {
  const onlyIfEmpty = opts.onlyIfEmpty !== false;
  const text = ($('c-text')?.value || '').trim();
  if (!text) return { filled: 0 };

  const parsed = parseProfileTextIntoFields(text);
  const urlName = nameFromLinkedInUrl($('c-url')?.value || '');
  if (!parsed.name && urlName) parsed.name = urlName;

  const setField = (id, val) => {
    const el = $(id);
    if (!el || val == null || val === '') return false;
    const v = typeof val === 'string' ? val.trim() : String(val);
    if (!v) return false;
    if (onlyIfEmpty && (el.value || '').trim()) return false;
    el.value = v;
    return true;
  };

  let filled = 0;
  if (setField('c-name', parsed.name)) filled++;
  if (setField('c-title', parsed.title)) filled++;
  if (setField('c-location', parsed.location)) filled++;
  if (setField('c-email', parsed.email)) filled++;
  if (setField('c-skills', parsed.skills)) filled++;
  if (parsed.years != null && setField('c-years', parsed.years)) filled++;

  const deg = normalizeDegreeForSelect(parsed.degreeRaw);
  const degEl = $('c-degree');
  if (degEl && deg && (!onlyIfEmpty || !(degEl.value || '').trim())) {
    degEl.value = deg;
    filled++;
  }

  if (parsed.email) checkDuplicate();
  return { filled, parsed };
}

function fillCandidateForm(d) {
  if (!d) return;

  const setIf = (id, v) => {
    const el = $(id);
    if (!el || v == null) return;
    const t = typeof v === 'string' ? v.trim() : v;
    if (t === '' || t === false) return;
    el.value = typeof t === 'number' ? String(t) : t;
  };

  setIf('c-name', d.name);
  setIf('c-title', d.title);
  setIf('c-location', d.location);
  setIf('c-skills', d.skills);
  setIf('c-email', d.email);
  setIf('c-text', d.fullText);

  if (d.years_experience != null && !Number.isNaN(Number(d.years_experience))) {
    const y = Math.round(Number(d.years_experience) * 10) / 10;
    setIf('c-years', y);
  }

  const deg = normalizeDegreeForSelect(d.highest_degree);
  const degEl = $('c-degree');
  if (degEl && deg) degEl.value = deg;

  if (d.certifications) {
    const existing = ($('c-skills')?.value || '').toLowerCase();
    const newCerts = d.certifications.split(',').map(c => c.trim()).filter(Boolean)
      .filter(c => !existing.includes(c.toLowerCase()));
    if (newCerts.length) {
      const sk = $('c-skills');
      if (sk) {
        const cur = (sk.value || '').trim();
        sk.value = cur ? `${cur}, ${newCerts.join(', ')}` : newCerts.join(', ');
      }
    }
  }

  updateCharCount();
  if (d.email) checkDuplicate();

  /* When LinkedIn only yields blob text, fill name/title/skills from exported headers inside it. */
  hydrateFormFromProfileText({ onlyIfEmpty: true });
}

function clearForm() {
  ['c-name','c-email','c-title','c-location','c-skills','c-text','c-url','c-years']
    .forEach(id => { if ($(id)) $(id).value = ''; });
  $('c-degree').value = '';
  updateCharCount();
  hide('dup-banner'); showAlert('step1-err', '');
}

function updateCharCount() {
  const len = ($('c-text')?.value || '').length;
  const el = $('char-count');
  if (el) el.textContent = len.toLocaleString() + ' chars';
}

// ── Step 1 → 2 ────────────────────────────────────────────────
function goToAnalyze() {
  const text = ($('c-text')?.value || '').trim();
  if (!text && !($('c-skills')?.value || '').trim()) {
    showAlert('step1-err', 'Please add profile text or skills before continuing.'); return;
  }
  showAlert('step1-err', '');

  // Update candidate summary
  const name  = $('c-name')?.value.trim()  || 'Unknown Candidate';
  const title = $('c-title')?.value.trim() || '';
  $('cand-name-disp').textContent  = name;
  $('cand-title-disp').textContent = title;
  $('cand-avatar').textContent     = (name[0] || '?').toUpperCase();

  goStep(2);
  loadJobs();
}

// ── Jobs loader ───────────────────────────────────────────────
async function loadJobs() {
  const sel = $('job-select');
  sel.innerHTML = '<option value="">Loading…</option>';
  sel.disabled = true;
  try {
    const data = await apiReq('GET', '/api/v1/jobs/page?skip=0&limit=100&status=active&sort=created_at_desc');
    const jobs = data.items || [];
    if (!jobs.length) {
      sel.innerHTML = '<option value="">No active jobs found</option>';
      return;
    }
    sel.innerHTML = `<option value="">— Select a job —</option>` +
      jobs.map(j => `<option value="${esc(j.external_id)}">${esc(j.title || 'Untitled')} (${esc(j.external_id)})</option>`).join('');
    sel.disabled = false;
  } catch (e) {
    sel.innerHTML = `<option value="">Error: ${esc(e.message)}</option>`;
  }
}

// ── Analyze / real-time match ──────────────────────────────────
async function analyzeMatch() {
  const jobId = $('job-select')?.value;
  if (!jobId) { showAlert('analyze-err', 'Please select a job first.'); return; }

  showAlert('analyze-err', '');
  hide('results-card', 'save-actions');

  $('btn-analyze').disabled = true;
  show('analyze-spinner'); $('analyze-label').textContent = 'Analyzing…';

  try {
    const body = {
      job_id:            jobId,
      candidate_text:    $('c-text')?.value.trim()     || $('c-skills')?.value.trim() || '(no text)',
      candidate_name:    $('c-name')?.value.trim()     || undefined,
      candidate_title:   $('c-title')?.value.trim()    || undefined,
      candidate_skills:  $('c-skills')?.value.trim()   || undefined,
      candidate_email:   $('c-email')?.value.trim()    || undefined,
      candidate_location:$('c-location')?.value.trim() || undefined,
      years_experience:  parseFloat($('c-years')?.value) || undefined,
      highest_degree:    $('c-degree')?.value           || undefined,
      profile_url:       $('c-url')?.value.trim()       || undefined,
    };
    // Clean undefined
    Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);

    const result = await apiReq('POST', '/api/v1/match/preview', body);
    G.lastResult    = result;
    G.selectedJobId = jobId;
    renderResults(result);
    show('results-card', 'save-actions');
  } catch (e) {
    showAlert('analyze-err', e.message);
  } finally {
    $('btn-analyze').disabled = false;
    hide('analyze-spinner'); $('analyze-label').textContent = 'Analyze Match';
  }
}

function renderResults(r) {
  // Score ring
  const pct    = Math.round(r.match_score);
  const circum = 2 * Math.PI * 34; // r=34 → 213.6
  const offset = circum - (pct / 100) * circum;
  $('score-pct').textContent  = pct;

  const ring = $('ring-fill');
  if (ring) {
    const color = pct >= 70 ? '#3ecf8e' : pct >= 45 ? '#fbbf24' : '#f87171';
    ring.style.stroke = color;
    ring.style.strokeDashoffset = circum;   // reset
    setTimeout(() => { ring.style.strokeDashoffset = offset; }, 50);
  }

  // Badge
  const badge = $('score-badge');
  if (badge) {
    const lbl = (r.match_label || 'Unknown').toLowerCase();
    badge.textContent = r.match_label;
    badge.className   = `score-badge badge-${lbl}`;
  }

  // Rank info
  $('rank-info').textContent   = r.total_ranked
    ? `#${r.ranking_position} of ${r.total_ranked + 1} (est.)`
    : 'First candidate for this job';
  $('job-name-disp').textContent = r.job_title ? `vs. "${r.job_title}"` : '';

  // Breakdown bars
  function setBar(barId, valId, val) {
    const pctVal = Math.round((val || 0) * 100);
    const bar = $(barId), valEl = $(valId);
    if (bar) { bar.style.width = '0%'; setTimeout(() => { bar.style.width = pctVal + '%'; }, 50); }
    if (valEl) valEl.textContent = pctVal + '%';
    const color = pctVal >= 70 ? '#3ecf8e' : pctVal >= 45 ? '#fbbf24' : '#f87171';
    if (bar) bar.style.background = color;
  }
  const bd = r.breakdown || {};
  setBar('bar-skills',   'val-skills',   bd.skills_overlap);
  setBar('bar-critical', 'val-critical', bd.critical_skill_coverage);
  setBar('bar-exp',      'val-exp',      bd.experience_match);
  setBar('bar-title',    'val-title',    bd.title_relevance);

  // Skill chips
  renderChips('matching-skills', r.matching_skills || [], 'chip-match');
  renderChips('missing-skills',  r.missing_skills  || [], 'chip-missing');
}

function renderChips(containerId, skills, cls) {
  const el = $(containerId);
  if (!el) return;
  if (!skills.length) { el.innerHTML = '<span style="color:var(--text-muted);font-size:11px">—</span>'; return; }
  el.innerHTML = skills.slice(0, 12).map(s => `<span class="chip ${cls}">${esc(s)}</span>`).join('');
}

// ── Save candidate ─────────────────────────────────────────────
/** Ensure ingest text starts with Name:/Current Title: so the API name extractor can resolve full_name. */
function buildIngestionTextForSave() {
  let body = ($('c-text')?.value || '').trim();
  if (!body) body = ($('c-skills')?.value || '').trim() || '(no text)';

  const name = ($('c-name')?.value || '').trim();
  const title = ($('c-title')?.value || '').trim();
  const loc = ($('c-location')?.value || '').trim();
  const email = ($('c-email')?.value || '').trim();
  const skills = ($('c-skills')?.value || '').trim();

  const hasNameLine = /^Name:\s/im.test(body);
  const lines = [];
  if (name && !hasNameLine) lines.push(`Name: ${name}`);
  if (title) lines.push(`Current Title: ${title}`);
  if (loc) lines.push(`Location: ${loc}`);
  if (email) lines.push(`Email: ${email}`);
  if (skills && !/^Skills:/im.test(body)) lines.push(`Skills: ${skills}`);

  if (lines.length) return `${lines.join('\n')}\n\n${body}`;
  return body;
}

async function saveCandidate(attachToJob) {
  const text = buildIngestionTextForSave();
  const filename = ($('c-name')?.value.trim() || 'candidate') + '.txt';

  $('btn-save-only').disabled  = true;
  $('btn-save-match').disabled = true;

  try {
    // 1. Ingest / create candidate
    const ingestion = await apiReq('POST', '/api/v1/ingestions/text', {
      text,
      source:   'extension',
      filename,
    });
    G.savedCandId = ingestion.candidate_external_id || null;

    // 2. Optionally persist match score to the selected job
    if (attachToJob && G.selectedJobId && G.savedCandId) {
      try {
        await apiReq('POST',
          `/api/v1/jobs/${encodeURIComponent(G.selectedJobId)}/match-one`,
          { candidate_id: G.savedCandId },
        );
      } catch (e) {
        // Non-fatal: candidate saved, match may retry
        console.warn('match-one failed:', e.message);
      }
    }

    // 3. Show confirmation
    const scoreStr = G.lastResult ? ` — ${Math.round(G.lastResult.match_score)}% match` : '';
    $('confirm-title').textContent = attachToJob ? 'Saved & Attached' : 'Candidate Saved';
    $('confirm-msg').textContent   = attachToJob
      ? `${$('c-name')?.value || 'Candidate'} saved and attached to "${$('job-select')?.options[$('job-select')?.selectedIndex]?.text || G.selectedJobId}"${scoreStr}.`
      : `${$('c-name')?.value || 'Candidate'} saved to RezumeAI.`;
    goStep(3);
  } catch (e) {
    showAlert('analyze-err', 'Save failed: ' + e.message);
  } finally {
    $('btn-save-only').disabled  = false;
    $('btn-save-match').disabled = false;
  }
}

// ── Duplicate detection ────────────────────────────────────────
async function checkDuplicate() {
  const email = ($('c-email')?.value || '').trim().toLowerCase();
  if (!email) return;
  try {
    const data = await apiReq('GET', `/api/v1/candidates/page?skip=0&limit=1&q=${encodeURIComponent(email)}`);
    const match = (data.items || []).find(c => (c.contact_email || '').toLowerCase() === email);
    if (match) {
      $('dup-text').textContent = `"${match.full_name || email}" already exists (${match.external_id})`;
      show('dup-banner');
    } else {
      hide('dup-banner');
    }
  } catch { /* non-fatal */ }
}

// ── Event wiring ──────────────────────────────────────────────
function wireEvents() {

  // Login
  $('btn-login')?.addEventListener('click', async () => {
    showAlert('l-err', '');
    const email = $('l-email')?.value.trim(), password = $('l-pass')?.value;
    if (!email || !password) { showAlert('l-err', 'Email and password are required.'); return; }
    setBtn('btn-login', true);
    try {
      await login(email, password);
      showView('main'); checkHealth(); detectContext();
    } catch (e) { showAlert('l-err', e.message); }
    finally { setBtn('btn-login', false); }
  });
  $('l-pass')?.addEventListener('keydown', e => { if (e.key === 'Enter') $('btn-login')?.click(); });

  // Logout / Settings
  $('btn-logout')?.addEventListener('click', logout);
  $('btn-settings')?.addEventListener('click', () => chrome.runtime.openOptionsPage());

  // Step 1 — Extract
  $('btn-grab-linkedin')?.addEventListener('click', grabLinkedIn);
  $('btn-grab-selection')?.addEventListener('click', grabSelection);
  $('btn-clear')?.addEventListener('click', clearForm);
  $('c-text')?.addEventListener('input', updateCharCount);
  $('c-email')?.addEventListener('blur', checkDuplicate);
  $('btn-parse-fields')?.addEventListener('click', () => {
    showAlert('step1-err', '');
    const { filled } = hydrateFormFromProfileText({ onlyIfEmpty: false });
    if (filled > 0) {
      showAlert('step1-err', `Updated ${filled} field(s) from profile text.`, 'success');
      setTimeout(() => showAlert('step1-err', ''), 2500);
    } else {
      showAlert(
        'step1-err',
        'No lines like “Name: …”, “Current Title: …”, or “SKILLS” were found. Add those lines at the top of Profile Text, or paste a fuller export.',
        'error',
      );
    }
  });
  $('btn-to-analyze')?.addEventListener('click', goToAnalyze);

  // Step 2 — Analyze
  $('btn-back-1')?.addEventListener('click', () => goStep(1));
  $('btn-reload-jobs')?.addEventListener('click', loadJobs);
  $('btn-analyze')?.addEventListener('click', analyzeMatch);
  $('btn-reanalyze')?.addEventListener('click', () => {
    hide('results-card', 'save-actions'); showAlert('analyze-err', '');
    $('job-select').value = '';
  });

  // Save actions
  $('btn-save-only')?.addEventListener('click', () => saveCandidate(false));
  $('btn-save-match')?.addEventListener('click', () => saveCandidate(true));
  $('btn-skip')?.addEventListener('click', () => {
    clearForm(); goStep(1); show('step-1'); hide('step-2', 'step-3');
    ['step-ind-1','step-ind-2','step-ind-3'].forEach(id => { $(id)?.classList.remove('active','done'); });
    $('step-ind-1')?.classList.add('active');
  });

  // Confirmation
  $('btn-new-candidate')?.addEventListener('click', () => {
    clearForm(); goStep(1);
  });
  $('btn-open-app')?.addEventListener('click', () => {
    chrome.tabs.create({ url: G.apiBase.replace(':8000', ':5173') || 'http://localhost:5173' });
  });
}

// ── Utilities ─────────────────────────────────────────────────
function esc(s) {
  return String(s || '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  const stored = await chrome.storage.local.get([SK.TOKEN, SK.EMAIL, SK.API_BASE, SK.ROLE]);
  G.apiBase = stored[SK.API_BASE] || 'http://127.0.0.1:8000';
  G.token   = stored[SK.TOKEN]   || null;
  G.email   = stored[SK.EMAIL]   || '';

  wireEvents();
  checkHealth();

  if (G.token) {
    showView('main');
    goStep(1);
    detectContext();
  } else {
    showView('login');
  }
});
