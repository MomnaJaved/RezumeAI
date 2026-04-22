/**
 * LinkedIn profile scrape — runs in the extension isolated world (content script).
 * Exposed for: chrome.tabs.sendMessage (via content.js) and programmatic executeScript fallback.
 */
(function initRezumeExtract() {
  if (typeof globalThis.__rezumeExtractLinkedIn === 'function') return;

  /** Hard cap so payloads stay reasonable; raise if LinkedIn ever allows huge skill lists. */
  const MAX_SKILLS_IN_OUTPUT = 500;

  /**
   * Prefer the inner profile column LinkedIn uses in scaffold layouts; plain <main> can miss cards.
   */
  function profileMain() {
    const sels = [
      'main.scaffold-layout__main',
      'div.scaffold-layout__main',
      'main[role="main"]',
      '[role="main"].scaffold-layout__main',
      '[role="main"]',
      'main:not([hidden])',
      'main',
      '.scaffold-layout__list-detail-inner',
      '.scaffold-layout__list-detail',
    ];
    for (const sel of sels) {
      try {
        const el = document.querySelector(sel);
        if (el) return el;
      } catch {
        /* ignore invalid selector in older engines */
      }
    }
    return null;
  }

  function rootEl() {
    return (
      profileMain() ||
      document.querySelector('.scaffold-layout__list-detail-inner') ||
      document.querySelector('.scaffold-layout__list-detail') ||
      document.body
    );
  }

  /** Strip direction marks / ZWJ so headings match (LinkedIn sometimes injects invisible chars). */
  function normalizeHeading(s) {
    return String(s || '')
      .replace(/[\u200e\u200f\u202a-\u202e\u200b-\u200d\ufeff]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /** Resolve profile anchors inside <main> first (avoids stray #experience elsewhere). */
  function anchorById(id) {
    const main = profileMain();
    if (main) {
      try {
        const scoped = main.querySelector(`#${id}`);
        if (scoped) return scoped;
      } catch {
        /* invalid id — fall back */
      }
    }
    return document.getElementById(id);
  }

  /**
   * LinkedIn virtualizes Experience / Education / Skills until those regions scroll into view.
   * Many layouts scroll on **window** (not `<main>`), so we drive both.
   */
  function primeProfileSections() {
    try {
      primeProfileSectionsInner();
    } catch {
      /* LinkedIn DOM changes should not brick extraction */
    }
  }

  function primeProfileSectionsInner() {
    const main = profileMain();
    let maxY = 0;
    try {
      maxY = Math.max(
        document.documentElement?.scrollHeight || 0,
        document.body?.scrollHeight || 0,
        main?.scrollHeight || 0,
        4000,
      );
    } catch {
      maxY = 6000;
    }
    for (let i = 0; i <= 14; i++) {
      try {
        window.scrollTo(0, Math.floor((maxY * i) / 14));
      } catch { /* ignore */ }
    }
    if (main && main.scrollHeight > (main.clientHeight || 0) + 50) {
      const h = main.scrollHeight;
      for (let i = 0; i <= 10; i++) {
        try {
          main.scrollTop = (h * i) / 10;
        } catch { /* ignore */ }
      }
    }
    try {
      window.scrollTo(0, Math.min(maxY, 12000));
    } catch { /* ignore */ }
    [
      'experience',
      'education',
      'skills',
      'about',
      'licenses_and_certifications',
      'certifications',
      'projects',
      'languages',
      'volunteer_experience',
      'recommendations',
    ].forEach(id => {
      const el = anchorById(id);
      try {
        el?.scrollIntoView({ block: 'center', inline: 'nearest' });
      } catch { /* ignore */ }
    });
    expandLinkedInSkillsPanel(profileMain());
    /* Do not reset main.scrollTop to 0 — LinkedIn virtualizes sections and will unmount Experience/Skills. */
  }

  /**
   * Prefer `profile-card-*` / profile-ish `data-view-name` nodes. A bare fragment `skill` matches
   * skill-assessment promos first in DOM order and can hijack the whole scrape.
   */
  function sectionByDataView(root, fragment) {
    const r = root || document;
    const frag = String(fragment || '').toLowerCase();
    if (!frag) return null;
    const scored = [];
    r.querySelectorAll('[data-view-name]').forEach(node => {
      const name = (node.getAttribute('data-view-name') || '').toLowerCase();
      if (!name.includes(frag)) return;
      let s = 0;
      if (name.includes('profile-card')) s += 10;
      else if (name.includes('profile')) s += 4;
      if (name.includes('pvs')) s += 2;
      if (/skill-assessment|skills-quiz|endorsement|global-nav|msg-overlay|hiring|rsc-nav/i.test(name)) s -= 30;
      scored.push({ node, s });
    });
    scored.sort((a, b) => b.s - a.s);
    for (const { node, s } of scored) {
      if (s < 0) break;
      const selfCard =
        typeof node.matches === 'function' &&
        (node.matches('section.artdeco-card') || node.matches('div.artdeco-card'))
          ? node
          : null;
      const card =
        node.closest('section.artdeco-card') ||
        node.closest('div.artdeco-card') ||
        selfCard ||
        node.closest('section') ||
        node;
      if (card && card !== r) return card;
    }
    return null;
  }

  /** Walk artdeco profile cards and match the visible section title (handles "Experience (2)" etc.). */
  function sectionByArtdecoCardHeader(root, patterns) {
    const r = root || document;
    for (const card of r.querySelectorAll('section.artdeco-card, div.artdeco-card')) {
      const headerEl =
        card.querySelector('.pvs-header__container h2') ||
        card.querySelector('h2.pvs-header__title') ||
        card.querySelector('.artdeco-card__header h2') ||
        card.querySelector('h2');
      if (!headerEl) continue;
      const t = normalizeHeading(headerEl.innerText || '');
      if (!t || t.length > 120) continue;
      if (
        /people who follow|also follow|more profiles|similar to|you may know|premium profiles|profiles for you|^activity$|^featured$/i.test(
          t,
        )
      ) {
        continue;
      }
      for (const re of patterns) {
        if (re.test(t)) return card;
      }
    }
    return null;
  }

  /** Find a profile card when the #experience anchor layout differs by locale / A-B test. */
  function sectionByHeading(root, patterns) {
    const r = root || document;
    const candidates = r.querySelectorAll(
      [
        'h2.pvs-header__title span[aria-hidden="true"]',
        'h2 span[aria-hidden="true"]',
        'h2 .hoverable-link-text span[aria-hidden="true"]',
        '.pvs-header__title span[aria-hidden="true"]',
        '.pvs-header__title',
        'h2',
        'h3',
      ].join(', '),
    );
    for (const h of candidates) {
      const t = normalizeHeading(h.innerText || '');
      if (!t) continue;
      for (const re of patterns) {
        if (re.test(t)) {
          const card =
            h.closest('section.artdeco-card') ||
            h.closest('div.artdeco-card') ||
            h.closest('section') ||
            h.closest('[data-view-name]');
          if (card) return card;
        }
      }
    }
    return null;
  }

  function tx(sel, root) {
    return ((root || document).querySelector(sel)?.innerText || '').trim();
  }

  function txs(sel, root) {
    return [...(root || document).querySelectorAll(sel)]
      .map(n => n.innerText.trim())
      .filter(Boolean);
  }

  /** Section card that contains an element with id=slug (LinkedIn profile layout). */
  function sectionFor(slug) {
    const el = anchorById(slug);
    if (!el) return null;
    return (
      el.closest('section.artdeco-card') ||
      el.closest('div.artdeco-card') ||
      el.closest('section') ||
      el.closest('[data-view-name]') ||
      el.parentElement
    );
  }

  const experienceHeadingRes = [
    /^Experience(\s|\(|$|:)/i,
    /^Work experience$/i,
    /^Employment$/i,
    /^Berufserfahrung$/i,
    /^Expérience$/i,
    /^Experiencia$/i,
  ];

  function sectionExperience(root) {
    const r = root || document;
    return (
      sectionFor('experience') ||
      sectionByDataView(r, 'experience') ||
      sectionByHeading(r, experienceHeadingRes) ||
      sectionByArtdecoCardHeader(r, experienceHeadingRes)
    );
  }

  function sectionAbout(root) {
    return sectionFor('about') || sectionByHeading(root, [/^About$/i, /^Info$/i, /^Über mich$/i, /^À propos$/i, /^Acerca de$/i]);
  }

  const skillsHeadingRes = [
    /^Skills(\s|\(|$|:)/i,
    /^Compétences$/i,
    /^Kenntnisse$/i,
    /^Habilidades$/i,
  ];

  function sectionSkills(root) {
    const r = root || document;
    return (
      sectionFor('skills') ||
      sectionByDataView(r, 'skills') ||
      sectionByHeading(r, skillsHeadingRes) ||
      sectionByArtdecoCardHeader(r, skillsHeadingRes)
    );
  }

  const educationHeadingRes = [
    /^Education(\s|\(|$|:)/i,
    /^Ausbildung$/i,
    /^Formation$/i,
    /^Educación$/i,
  ];

  function sectionEducation(root) {
    const r = root || document;
    return (
      sectionFor('education') ||
      sectionByDataView(r, 'education') ||
      sectionByHeading(r, educationHeadingRes) ||
      sectionByArtdecoCardHeader(r, educationHeadingRes)
    );
  }

  function sectionRecommendations(root) {
    const r = root || document;
    return (
      sectionFor('recommendations') ||
      sectionByDataView(r, 'recommendation') ||
      sectionByHeading(r, [/^Recommendations$/i, /^Empfehlungen$/i, /^Recommandations$/i]) ||
      sectionByArtdecoCardHeader(r, [/^Recommendations(\s|\(|$|:)/i, /^Empfehlungen$/i])
    );
  }

  const certHeadingRes = [
    /^Licenses\s+&\s+certifications$/i,
    /^Licenses and certifications$/i,
    /^Licenses(\s|\(|$|:)/i,
    /^Certifications(\s|\(|$|:)/i,
    /^Certificados$/i,
    /^Zertifikate$/i,
  ];

  function sectionCertifications(root) {
    const r = root || document;
    return (
      sectionFor('licenses_and_certifications') ||
      sectionFor('certifications') ||
      sectionByDataView(r, 'license') ||
      sectionByDataView(r, 'certification') ||
      sectionByHeading(r, certHeadingRes) ||
      sectionByArtdecoCardHeader(r, certHeadingRes)
    );
  }

  /**
   * Prefer the smallest meaningful card around an anchor (closest('section') can be huge).
   */
  function profileCardAround(el) {
    if (!el) return null;
    let n = el;
    for (let depth = 0; depth < 8 && n; depth++) {
      const tag = (n.tagName || '').toLowerCase();
      const cls = (n.getAttribute && n.getAttribute('class')) || '';
      if (
        (tag === 'section' || tag === 'div') &&
        (cls.includes('artdeco-card') || n.getAttribute('data-view-name'))
      ) {
        return n;
      }
      n = n.parentElement;
    }
    return (
      el.closest('section.artdeco-card') ||
      el.closest('div.artdeco-card') ||
      el.closest('section') ||
      el.closest('[data-view-name]') ||
      el.parentElement
    );
  }

  /** Clicks "Show all … skills" / "See all … skills" so the full list mounts in the DOM. */
  function expandLinkedInSkillsPanel(root) {
    try {
      const sec = sectionSkills(root || document);
      if (!sec) return;
      const tryClick = el => {
        if (!el) return false;
        try {
          el.click();
          return true;
        } catch {
          return false;
        }
      };
      sec.querySelectorAll('[aria-label]').forEach(el => {
        const lab = String(el.getAttribute('aria-label') || '').toLowerCase();
        if (/show all|see all|expand|more skills/.test(lab) && /skill/.test(lab)) tryClick(el);
      });
      sec.querySelectorAll('a, button, [role="button"], .artdeco-button').forEach(el => {
        const raw = normalizeHeading(el.innerText || el.textContent || '');
        if (!raw || raw.length > 90) return;
        if (/^show all\b/i.test(raw) && /skill/i.test(raw)) tryClick(el);
        else if (/^see all\b/i.test(raw) && /skill/i.test(raw)) tryClick(el);
        else if (/show more/i.test(raw) && /skill/i.test(raw)) tryClick(el);
      });
    } catch {
      /* ignore */
    }
  }

  /** "Top skills" line often appears inside the About body (bullet-separated). */
  function extractSkillsFromAboutTopSkills(aboutText) {
    const a = String(aboutText || '');
    const m = a.match(/\btop\s+skills\b\s*[:\s]*([^\n]+(?:\n[^\n·•]{0,120}){0,6})/i);
    if (!m) return [];
    return m[1]
      .split(/[·•,|]|\s{2,}/)
      .map(s => s.trim())
      .filter(s => s.length > 1 && s.length < 120);
  }

  /** Keep skill field clean: real skill phrases only, no LinkedIn UI chrome. */
  function isLikelySkillName(t) {
    const s = String(t || '').replace(/\s+/g, ' ').trim();
    if (!s || s.length < 2 || s.length > 100) return false;
    const low = s.toLowerCase();
    if (/https?:|linkedin\.com|@/.test(s)) return false;
    if (/^\d+$/.test(s)) return false;
    if (/\d{4}\s*[–—-]\s*(present|\d{4})/i.test(s)) return false;
    if (/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b/i.test(s) && /\d{4}/.test(s)) return false;
    const words = s.split(/\s+/).length;
    if (words > 12) return false;

    const junk = [
      'show all',
      'see all',
      'see less',
      'add skill',
      'endorse',
      'endorsed',
      'endorsement',
      'endorsements',
      'demonstrate',
      'skill assessment',
      'assessments',
      'take skill quiz',
      'quiz',
      'verify',
      'recommendations',
      'following',
      'followers',
      'connections',
      'mutual',
      'message',
      'connect',
      'pending',
      'more skills',
      'other skills',
      'skills and',
      'top skills',
      'interests',
      'services',
      'activity',
      'analytics',
      'about',
      'experience',
      'education',
      'licenses',
      'certifications',
      'volunteer',
      'languages',
      'projects',
      'summary',
      'profile',
      'view',
      'click',
      'skip',
    ];
    for (const j of junk) {
      if (low === j || low.startsWith(j + ' ') || low.includes(' ' + j + ' ') || low.endsWith(' ' + j)) return false;
    }
    if (/endorsement/i.test(s)) return false;
    return true;
  }

  /**
   * LinkedIn Skills card — links, list rows, card text, and optional About "Top skills" line.
   * Merges every pass so profile text can list the full skill set (up to MAX_SKILLS_IN_OUTPUT).
   */
  function extractLinkedInSkills(skillsSec, aboutText) {
    const out = [];
    const seen = new Set();
    const add = raw => {
      const t = String(raw || '')
        .replace(/\s+/g, ' ')
        .replace(/[·•]+/g, ' ')
        .trim();
      if (!t) return;
      if (/^show all\s+\d+\s+skills?$/i.test(t) || /^see all\s+\d+/i.test(t)) return;
      if (/^endorsed?\s+by\b/i.test(t)) return;
      const k = t.toLowerCase();
      if (seen.has(k)) return;
      if (!isLikelySkillName(t)) return;
      seen.add(k);
      out.push(t);
    };

    if (skillsSec) {
      skillsSec
        .querySelectorAll(
          [
            'a[data-field="skill_card_skill_topic"]',
            'a[href*="/details/skills/"]',
            'a[href*="/skills/"]',
          ].join(', '),
        )
        .forEach(a => {
          const s =
            a.querySelector('span[aria-hidden="true"]')?.textContent?.trim() ||
            a.querySelector('.hoverable-link-text')?.textContent?.trim() ||
            a.textContent?.trim().split('\n')[0]?.trim();
          add(s);
        });

      skillsSec.querySelectorAll('li[class*="pvs-list"] .hoverable-link-text span[aria-hidden="true"]').forEach(el => {
        add(el.textContent?.trim());
      });

      skillsSec.querySelectorAll('li[class*="pvs-list"] .t-bold span[aria-hidden="true"]').forEach(el => {
        add(el.textContent?.trim());
      });

      skillsSec.querySelectorAll('[class*="pvs-list"] span[aria-hidden="true"]').forEach(el => {
        add(el.textContent?.trim());
      });

      listItems(skillsSec).forEach(item => {
        rowTextParts(item).forEach(part => add(part));
      });

      (skillsSec.innerText || '')
        .split(/[·•]+|\n+/)
        .map(s => s.trim())
        .forEach(line => add(line));
    }

    extractSkillsFromAboutTopSkills(aboutText).forEach(t => add(t));

    return out.slice(0, MAX_SKILLS_IN_OUTPUT);
  }

  function arHidden(item) {
    return txs('span[aria-hidden="true"]', item);
  }

  /** When LinkedIn omits aria-hidden spans, fall back to visible line chunks. */
  function rowTextParts(item) {
    let parts = arHidden(item);
    if (parts.length) return parts;
    const seen = new Set();
    const fromSpans = [];
    item
      .querySelectorAll(
        [
          'span[aria-hidden="true"]',
          '.hoverable-link-text span[aria-hidden="true"]',
          '.t-bold span[aria-hidden="true"]',
          'div.t-bold span[aria-hidden="true"]',
          'a .hoverable-link-text span[aria-hidden="true"]',
        ].join(', '),
      )
      .forEach(el => {
        const t = (el.textContent || '').replace(/\s+/g, ' ').trim();
        if (!t || t.length < 2 || t.length > 400) return;
        const k = t.toLowerCase();
        if (seen.has(k)) return;
        seen.add(k);
        fromSpans.push(t);
      });
    if (fromSpans.length) return fromSpans.slice(0, 8);
    const t = (item.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length < 3) return [];
    return t
      .split(/\s*[·•|]\s*|\s{2,}/)
      .map(s => s.trim())
      .filter(s => s.length > 1 && s.length < 500)
      .slice(0, 8);
  }

  function listItems(sec) {
    if (!sec) return [];
    const seen = new Set();
    const out = [];
    const add = node => {
      if (!node || seen.has(node)) return;
      seen.add(node);
      out.push(node);
    };
    sec.querySelectorAll('ul > li, ol > li').forEach(add);
    sec.querySelectorAll('ul[class*="pvs-list"] > li').forEach(add);
    sec.querySelectorAll('.pvs-list__outer-container > ul > li').forEach(add);
    sec
      .querySelectorAll(
        [
          'li[class*="pvs-list__paged-list-item"]',
          'li[class*="pvs-list__item--two-column"]',
          'li[class*="pvs-list__item--one-column"]',
          'li[class*="pvs-entity"]',
          'li.artdeco-list__item',
          'div[class*="pvs-list__paged-list-item"]',
        ].join(', '),
      )
      .forEach(add);
    return out;
  }

  function cleanLines(text) {
    return String(text || '')
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean)
      .join('\n');
  }

  function parseMonthsFromDates(dates) {
    if (!dates) return 0;
    const dot = dates.match(/(\d+)\s+yr[s]?\s*(\d+)?\s*mo[s]?/i);
    if (dot) return parseInt(dot[1] || 0, 10) * 12 + parseInt(dot[2] || 0, 10);
    const yr = dates.match(/(\d+)\s+yr[s]?\b/i);
    if (yr) return parseInt(yr[1], 10) * 12;
    const parts = dates.split(/[–—-]/).map(s => s.trim());
    if (parts.length < 2) return 0;
    const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
    const parseYrMo = str => {
      if (/present/i.test(str)) return new Date().getFullYear() * 12 + new Date().getMonth();
      const m = str.match(/([A-Za-z]{3,9})[.\s,]+(\d{4})/);
      if (m) {
        const mi = months.indexOf(m[1].toLowerCase().slice(0, 3));
        const y = parseInt(m[2], 10);
        if (mi >= 0 && !Number.isNaN(y)) return y * 12 + mi;
      }
      const yOnly = str.match(/(\d{4})/);
      return yOnly ? parseInt(yOnly[1], 10) * 12 : 0;
    };
    const s = parseYrMo(parts[0]);
    const e = parseYrMo(parts[1]);
    if (s && e && e >= s) return e - s;
    return 0;
  }

  /** Strip LinkedIn's trailing slug id (e.g. `…-6741a222a`) before turning hyphens into spaces. */
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

  function emptyExtractResult(err) {
    return {
      success: false,
      extracted_ok: false,
      error: err ? String(err.message || err) : '',
      name: '',
      title: '',
      location: '',
      email: '',
      phone: '',
      website: '',
      skills: '',
      certifications: '',
      languages: '',
      years_experience: null,
      highest_degree: '',
      experience_summary: '',
      education_summary: '',
      fullText: '',
    };
  }

  globalThis.__rezumeExtractLinkedIn = function rezumeExtractLinkedIn() {
    try {
    primeProfileSections();

    const main = rootEl();

    let nameFromSlug = '';
    try {
      const m = location.pathname.match(/\/in\/([^/?#]+)/i);
      if (m) nameFromSlug = humanNameFromLinkedInSlug(m[1]);
    } catch { /* ignore */ }

    const nameGuess =
      tx('[data-anonymize="person-name"]') ||
      tx('h1.text-heading-xlarge') ||
      tx('.pv-text-details__left-panel h1') ||
      tx('.top-card-layout__title') ||
      tx('main .ph5.pb5 h1') ||
      tx('main h1.break-words') ||
      tx('main h1') ||
      '';

    function looksLikeSectionHeading(s) {
      const t = (s || '').trim();
      if (!t) return true;
      if (t.length > 90) return true;
      return /^(experience|education|skills|about|activity|interests|people|analytics|services)$/i.test(t);
    }

    let nameFinal = (nameGuess || '').trim();
    if (!nameFinal || looksLikeSectionHeading(nameFinal)) nameFinal = nameFromSlug;

    const title =
      tx('.text-body-medium.break-words') ||
      tx('div.text-body-medium.break-words') ||
      tx('.pv-text-details__left-panel .text-body-medium') ||
      tx('.top-card-layout__headline') ||
      tx('[data-generated-suggestion-target] .text-body-medium') ||
      tx('main .text-body-medium');

    const location =
      tx('.text-body-small.inline.t-black--light.break-words') ||
      tx('span.text-body-small.inline.t-black--light') ||
      tx('.pb2 .t-black--light') ||
      tx('.top-card__subline-item') ||
      tx('span.text-body-small.inline');

    let email = '';
    main.querySelectorAll('a[href^="mailto:"]').forEach(a => {
      if (!email) email = a.href.replace('mailto:', '').trim();
    });

    let phone = '';
    main.querySelectorAll('a[href^="tel:"]').forEach(a => {
      if (!phone) phone = a.href.replace('tel:', '').trim();
    });

    let website = '';
    main.querySelectorAll('a[href^="http"]').forEach(a => {
      const h = (a.href || '').toLowerCase();
      if (website) return;
      if (!h || h.includes('linkedin.com') || h.includes('lnkd.in') || h.includes('microsoft.com')) return;
      const label = (a.innerText || '').trim();
      if (label.length > 2 && label.length < 80 && !/^(follow|connect|message|more)/i.test(label)) website = a.href;
    });

    let about = '';
    const aboutSec = sectionAbout(main);
    if (aboutSec) {
      const hidden = tx('.visually-hidden', aboutSec);
      const spans = txs('span[aria-hidden="true"]', aboutSec).filter(s => s.length > 40);
      about = hidden || spans.sort((a, b) => b.length - a.length)[0] || '';
      if (!about) {
        const raw = aboutSec.innerText || '';
        about = raw.replace(/^\s*About\s*/i, '').trim();
      }
      about = cleanLines(about).slice(0, 6000);
    }

    const expItems = [];
    const expSec = sectionExperience(main);
    listItems(expSec).forEach(item => {
      const spans = rowTextParts(item);
      if (!spans.length) return;
      const subItems = item.querySelectorAll('li.pvs-list__item--with-top-padding');
      if (subItems.length) {
        const companyName = spans[0] || '';
        subItems.forEach(sub => {
          const ss = rowTextParts(sub);
          if (ss.length) {
            expItems.push({
              role: ss[0],
              company: companyName,
              dates: ss[1] || '',
              desc: ss.slice(2).join(' '),
            });
          }
        });
      } else {
        expItems.push({
          role: spans[0] || '',
          company: spans[1] || '',
          dates: spans[2] || '',
          desc: spans.slice(3).join(' '),
        });
      }
    });

    const eduItems = [];
    const eduSec = sectionEducation(main);
    listItems(eduSec).forEach(item => {
      const spans = rowTextParts(item);
      if (!spans.length) return;
      eduItems.push({
        school: spans[0] || '',
        degree: spans[1] || '',
        field: spans[2] || '',
        dates: spans[3] || '',
        desc: spans.slice(4).join(' '),
      });
    });

    expandLinkedInSkillsPanel(main);
    const skillsSec = sectionSkills(main);
    const skillsList = extractLinkedInSkills(skillsSec, about);

    const certsList = [];
    const certSec = sectionCertifications(main);
    listItems(certSec).forEach(item => {
      const spans = rowTextParts(item);
      if (spans[0] && spans[0].length < 120) certsList.push(spans[0]);
    });

    const langsList = [];
    const langSec = sectionFor('languages');
    listItems(langSec).forEach(item => {
      const spans = rowTextParts(item);
      if (spans[0]) langsList.push(spans[0]);
    });

    const volunteerItems = [];
    const volSec = sectionFor('volunteer_experience') || sectionFor('volunteering_experience');
    listItems(volSec).forEach(item => {
      const spans = rowTextParts(item);
      if (spans[0]) volunteerItems.push(spans.slice(0, 3).join(' | '));
    });

    const projects = [];
    const projSec = sectionFor('projects');
    listItems(projSec).forEach(item => {
      const spans = rowTextParts(item);
      if (spans[0]) projects.push(spans.slice(0, 3).join(' | '));
    });

    const recItems = [];
    const recSec = sectionRecommendations(main);
    listItems(recSec).forEach(item => {
      const spans = rowTextParts(item);
      if (!spans.length) return;
      const block = spans.slice(0, 6).join(' | ');
      if (block.length > 12) recItems.push(block);
    });

    let yearsExperience = null;
    if (expItems.length) {
      let totalMonths = 0;
      expItems.forEach(({ dates }) => {
        totalMonths += parseMonthsFromDates(dates);
      });
      if (totalMonths > 0) yearsExperience = Math.round((totalMonths / 12) * 10) / 10;
    }

    let highestDegree = '';
    const degreeOrder = [
      { pattern: /ph\.?d|doctor\s+of/i, label: 'phd' },
      { pattern: /m\.?b\.?a|master|m\.?s\.?\b|m\.?eng|msc\b/i, label: 'masters' },
      { pattern: /bachelor|b\.?s\.?\b|b\.?e\.?\b|b\.?sc|b\.?tech|b\.?eng|\bba\b/i, label: 'bachelors' },
      { pattern: /associate|diploma|certificate|a-level/i, label: 'intermediate' },
    ];
    const degreeText = eduItems.map(e => `${e.degree} ${e.field}`).join(' ');
    for (const { pattern, label } of degreeOrder) {
      if (pattern.test(degreeText)) {
        highestDegree = label;
        break;
      }
    }

    const lines = [];
    if (nameFinal) lines.push(`Name: ${nameFinal}`);
    if (title) lines.push(`Current Title: ${title}`);
    if (location) lines.push(`Location: ${location}`);
    if (email) lines.push(`Email: ${email}`);
    if (phone) lines.push(`Phone: ${phone}`);
    if (website) lines.push(`Website: ${website}`);
    if (yearsExperience) lines.push(`Years of Experience: ${yearsExperience}`);
    if (highestDegree) lines.push(`Highest Degree: ${highestDegree}`);
    lines.push('');

    if (about) {
      lines.push('SUMMARY / ABOUT');
      lines.push(about);
      lines.push('');
    }

    if (expItems.length) {
      lines.push('WORK EXPERIENCE');
      expItems.forEach(({ role, company, dates, desc }) => {
        lines.push(`  ${role}${company ? ' @ ' + company : ''}${dates ? ' | ' + dates : ''}`);
        if (desc) lines.push(`    ${desc.slice(0, 400)}`);
      });
      lines.push('');
    }

    if (eduItems.length) {
      lines.push('EDUCATION');
      eduItems.forEach(({ school, degree, field, dates, desc }) => {
        const deg = [degree, field].filter(Boolean).join(', ');
        lines.push(`  ${school}${deg ? ' | ' + deg : ''}${dates ? ' | ' + dates : ''}`);
        if (desc) lines.push(`    ${desc.slice(0, 200)}`);
      });
      lines.push('');
    }

    if (skillsList.length) {
      lines.push('SKILLS');
      lines.push(skillsList.join(', '));
      lines.push('');
    }

    if (certsList.length) {
      lines.push('CERTIFICATIONS');
      lines.push(certsList.slice(0, 20).join(', '));
      lines.push('');
    }

    if (langsList.length) {
      lines.push('LANGUAGES');
      lines.push(langsList.join(', '));
      lines.push('');
    }

    if (volunteerItems.length) {
      lines.push('VOLUNTEER EXPERIENCE');
      volunteerItems.forEach(v => lines.push(`  ${v}`));
      lines.push('');
    }

    if (projects.length) {
      lines.push('PROJECTS');
      projects.forEach(p => lines.push(`  ${p}`));
      lines.push('');
    }

    if (recItems.length) {
      lines.push('RECOMMENDATIONS');
      recItems.slice(0, 15).forEach(r => lines.push(`  ${r.slice(0, 500)}`));
      lines.push('');
    }

    let fullText = lines.join('\n').trim();

    const structuredLen = fullText.length;
    const hasIdentity = Boolean(nameFinal || (title || '').trim());
    const hasSections =
      about.length > 40 ||
      expItems.length > 0 ||
      eduItems.length > 0 ||
      skillsList.length > 0;

    /**
     * LinkedIn puts suggestions, feed, and other profiles inside <main>. Never use main.innerText.
     * Snapshots use **anchors when present** and fall back to **heading-based** section cards so we
     * still capture content when ids move or list parsers miss rows.
     */
    function supplementalTextFromProfileAnchors() {
      const chunks = [];
      const maxBlock = 4200;

      function isNoiseCard(sec) {
        const head = (sec.querySelector('h2, .pvs-header__title')?.innerText || '')
          .replace(/\s+/g, ' ')
          .trim();
        return (
          head &&
          /people who follow|also follow|more profiles|you may know|similar to|writers you|premium profiles|profiles for you|^activity$|^featured$/i.test(
            head,
          )
        );
      }

      /** Prefer a tight card around #slug; else the resolved section from headings. */
      function cardFor(anchorId, resolveSection) {
        if (anchorId) {
          const a = anchorById(anchorId);
          if (a) {
            const c = profileCardAround(a);
            const len = c ? cleanLines((c.innerText || '').trim()).length : 0;
            if (c && len >= 12) return c;
          }
        }
        const s = typeof resolveSection === 'function' ? resolveSection() : null;
        return s || null;
      }

      function pushSnapshot(label, sec, onlyIfEmpty) {
        if (!onlyIfEmpty || !sec) return;
        if (isNoiseCard(sec)) return;
        let body = cleanLines((sec.innerText || '').trim());
        if (body.length < 12) return;
        if (body.length > maxBlock) body = `${body.slice(0, maxBlock)}\n…`;
        chunks.push(`${label}\n${body}`);
      }

      pushSnapshot('EXPERIENCE (from page)', cardFor('experience', () => sectionExperience(main)), !expItems.length);
      pushSnapshot('EDUCATION (from page)', cardFor('education', () => sectionEducation(main)), !eduItems.length);
      pushSnapshot('SKILLS (from page)', cardFor('skills', () => sectionSkills(main)), !skillsList.length);

      if (!certsList.length) {
        const cardTextLen = sec =>
          sec ? cleanLines((sec.innerText || '').trim()).length : 0;
        let certCard = cardFor('licenses_and_certifications', () => sectionCertifications(main));
        if (cardTextLen(certCard) < 12) certCard = cardFor('certifications', () => sectionCertifications(main));
        if (cardTextLen(certCard) < 12) certCard = sectionCertifications(main);
        pushSnapshot('CERTIFICATIONS (from page)', certCard, true);
      }

      pushSnapshot('LANGUAGES (from page)', cardFor('languages', () => sectionFor('languages')), !langsList.length);
      pushSnapshot('PROJECTS (from page)', cardFor('projects', () => sectionFor('projects')), !projects.length);
      if (!volunteerItems.length) {
        let volCard = cardFor('volunteer_experience', () => sectionFor('volunteer_experience'));
        if (!volCard || cleanLines((volCard.innerText || '').trim()).length < 12) {
          volCard = cardFor('volunteering_experience', () => sectionFor('volunteering_experience'));
        }
        if (!volCard || cleanLines((volCard.innerText || '').trim()).length < 12) {
          volCard = sectionFor('volunteer_experience') || sectionFor('volunteering_experience');
        }
        pushSnapshot('VOLUNTEER (from page)', volCard, true);
      }
      pushSnapshot(
        'RECOMMENDATIONS (from page)',
        cardFor('recommendations', () => sectionRecommendations(main)),
        !recItems.length,
      );

      pushSnapshot('COURSES (from page)', cardFor('courses', () => sectionFor('courses')), true);
      pushSnapshot('HONORS (from page)', cardFor('honors_and_awards', () => sectionFor('honors_and_awards')), true);
      pushSnapshot('PUBLICATIONS (from page)', cardFor('publications', () => sectionFor('publications')), true);
      pushSnapshot('PATENTS (from page)', cardFor('patents', () => sectionFor('patents')), true);

      return chunks.filter(Boolean).join('\n\n');
    }

    const supplemental = supplementalTextFromProfileAnchors();
    if (supplemental) {
      fullText = `${fullText ? `${fullText}\n\n` : ''}--- PROFILE SECTIONS (this member only) ---\n${supplemental}`.slice(
        0,
        48000,
      );
    }

    /* If list parsers still missed rows but the section card exists (e.g. wrong expItems from noise). */
    (function appendFallbackSectionText() {
      const cap = 8000;
      const has = re => re.test(fullText);
      if (!has(/\bWORK EXPERIENCE\b/i) && !has(/EXPERIENCE \(from page\)/i)) {
        const sec = sectionExperience(main);
        const b = sec ? cleanLines((sec.innerText || '').trim()) : '';
        if (b.length > 60) fullText = `${fullText}\n\nWORK EXPERIENCE (from page)\n${b.slice(0, cap)}`;
      }
      if (!has(/\bEDUCATION\b/i) && !has(/EDUCATION \(from page\)/i)) {
        const sec = sectionEducation(main);
        const b = sec ? cleanLines((sec.innerText || '').trim()) : '';
        if (b.length > 40) fullText = `${fullText}\n\nEDUCATION (from page)\n${b.slice(0, cap)}`;
      }
      if (!has(/\bSKILLS\b/i) && !has(/SKILLS \(from page\)/i)) {
        const sec = sectionSkills(main);
        const b = sec ? cleanLines((sec.innerText || '').trim()) : '';
        if (b.length > 25) fullText = `${fullText}\n\nSKILLS (from page)\n${b.slice(0, cap)}`;
      }
      fullText = fullText.slice(0, 48000);
    })();

    /* Last resort: URL slug gives at least a searchable name line */
    if (!fullText.trim() && nameFromSlug) {
      fullText = `Name (from profile URL): ${nameFromSlug}\n\nOpen the profile in LinkedIn and scroll to load About/Experience, then click Grab LinkedIn again.`;
    }

    const ok = Boolean(nameFinal || (title || '').trim() || fullText.length >= 80);

    return {
      success: true,
      extracted_ok: ok,
      name: nameFinal,
      title,
      location,
      email,
      phone,
      website,
      skills: skillsList.join(', '),
      certifications: certsList.slice(0, 20).join(', '),
      languages: langsList.join(', '),
      years_experience: yearsExperience,
      highest_degree: highestDegree,
      experience_summary: expItems
        .slice(0, 3)
        .map(e => `${e.role} @ ${e.company} (${e.dates})`)
        .join('; '),
      education_summary: eduItems
        .slice(0, 2)
        .map(e => `${e.degree} ${e.field} – ${e.school}`)
        .join('; '),
      fullText,
    };
    } catch (e) {
      return emptyExtractResult(e);
    }
  };

  /**
   * Scroll profile <main> slowly so LinkedIn mounts Experience/Education/Skills, then run sync extract.
   */
  globalThis.__rezumeExtractLinkedInAsync = async function rezumeExtractLinkedInAsync() {
    try {
    const main = profileMain();
    let maxY = 0;
    try {
      maxY = Math.max(
        document.documentElement?.scrollHeight || 0,
        document.body?.scrollHeight || 0,
        main?.scrollHeight || 0,
        4000,
      );
    } catch {
      maxY = 6000;
    }
    for (let i = 0; i <= 16; i++) {
      try {
        window.scrollTo(0, Math.floor((maxY * i) / 16));
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 85));
    }
    if (main) {
      const h = Math.max(main.scrollHeight || 0, 1200);
      for (let i = 0; i <= 12; i++) {
        try {
          main.scrollTop = (h * i) / 12;
        } catch { /* ignore */ }
        await new Promise(r => setTimeout(r, 65));
      }
      const ids = [
        'experience',
        'education',
        'skills',
        'licenses_and_certifications',
        'certifications',
        'projects',
        'volunteer_experience',
        'volunteering_experience',
        'languages',
        'recommendations',
        'courses',
        'honors_and_awards',
        'publications',
        'patents',
      ];
      for (const id of ids) {
        try {
          anchorById(id)?.scrollIntoView({ block: 'center' });
        } catch { /* ignore */ }
        if (id === 'skills') {
          expandLinkedInSkillsPanel(main);
          await new Promise(r => setTimeout(r, 600));
        } else {
          await new Promise(r => setTimeout(r, 100));
        }
      }
      expandLinkedInSkillsPanel(main);
      await new Promise(r => setTimeout(r, 400));
      /* Leave scroll position — resetting to top unmounts lower profile sections. */
    }
    return globalThis.__rezumeExtractLinkedIn();
    } catch (e) {
      return emptyExtractResult(e);
    }
  };
})();
