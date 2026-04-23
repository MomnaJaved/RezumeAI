/**
 * LinkedIn profile scrape — runs in the extension isolated world (content script).
 * Exposed for: chrome.tabs.sendMessage (via content.js) and programmatic executeScript fallback.
 */
(function initRezumeExtract() {
  if (typeof globalThis.__rezumeExtractLinkedIn === 'function') return;

  /**
   * Profile column root. LinkedIn often wraps content in `.scaffold-layout__main` (sometimes without
   * `main[role="main"]` as the scroll driver), so we prefer those before falling back to `body`.
   */
  function rootEl() {
    return (
      document.querySelector('main[role="main"]') ||
      document.querySelector('main.scaffold-layout__main') ||
      document.querySelector('.scaffold-layout__main') ||
      document.querySelector('main') ||
      document.body
    );
  }

  /** Primary profile column (excludes right-rail / suggestions that also use pvs-list rows). */
  function profileLayoutMain() {
    return (
      document.querySelector('main[role="main"]') ||
      document.querySelector('main.scaffold-layout__main') ||
      document.querySelector('.scaffold-layout__main') ||
      null
    );
  }

  /** True if node lives in the member profile main column, not aside / PYMK / browsemap widgets. */
  function isNodeInProfileMainColumn(node) {
    if (!node || node.nodeType !== 1) return false;
    if (node.closest('.scaffold-layout__aside, aside.scaffold-layout__aside')) return false;
    const rail = node.closest(
      [
        '[data-view-name*="profile-card-pymk"]',
        '[data-view-name*="browsemap"]',
        '[data-view-name*="people-you-may-know"]',
        '[data-view-name*="similar-to"]',
        '[data-view-name*="discovery"]',
        '[data-view-name*="edge-creation"]',
      ].join(', '),
    );
    if (rail) return false;
    const main = profileLayoutMain();
    if (main) return main.contains(node);
    return true;
  }

  /** All elements we should scroll so virtualized Experience/Education/Skills rows mount. */
  function getProfileScrollRoots() {
    const roots = [];
    const add = n => {
      if (n && typeof n.scrollHeight === 'number' && !roots.includes(n)) roots.push(n);
    };
    add(rootEl());
    add(document.querySelector('.scaffold-layout__main'));
    add(document.querySelector('div.scaffold-layout__list-detail-inner'));
    add(document.scrollingElement || document.documentElement);
    return roots.length ? roots : [document.body];
  }

  /** Real LinkedIn member profile only — never scrape localhost / other apps if a tab navigates. */
  function isLinkedInMemberPageHostname() {
    try {
      const h = String(location.hostname || '').toLowerCase();
      if (h !== 'linkedin.com' && !h.endsWith('.linkedin.com')) return false;
      return /^\/in\/[^/]+/i.test(location.pathname || '');
    } catch {
      return false;
    }
  }

  function wrongPageExtractResult() {
    return {
      success: false,
      extracted_ok: false,
      fullText: '',
      error:
        'This tab is not a LinkedIn profile (linkedin.com/in/…). If you just switched away from LinkedIn, go back to that tab or open the profile again, then run the extension.',
    };
  }

  /**
   * LinkedIn varies `id` on section anchors (`experience` vs `background-experience`, etc.).
   * Try known variants so scrolling + parsing hit the real cards.
   */
  const PROFILE_SECTION_IDS = {
    about: ['about', 'profile-about', 'background-about', 'about-summary'],
    experience: [
      'experience',
      'background-experience',
      'profile-experience',
      'profile-experience-details',
    ],
    education: ['education', 'background-education', 'profile-education', 'profile-education-details'],
    skills: ['skills', 'background-skills', 'profile-skills', 'profile-skills-details'],
    licenses_and_certifications: [
      'licenses_and_certifications',
      'licenses-and-certifications',
      'background-licenses',
      'profile-licenses',
    ],
    certifications: ['certifications', 'background-certifications', 'profile-certifications'],
    projects: ['projects', 'background-projects', 'profile-projects'],
    languages: ['languages', 'background-languages', 'profile-languages'],
    volunteer_experience: ['volunteer_experience', 'volunteering_experience', 'background-volunteering'],
    volunteering_experience: ['volunteering_experience', 'volunteer_experience', 'background-volunteering'],
    courses: ['courses', 'background-courses', 'profile-courses'],
    honors_awards: ['honors_and_awards', 'honors-and-awards', 'background-honors', 'profile-honors'],
    publications: ['publications', 'background-publications', 'profile-publications'],
    patents: ['patents', 'background-patents', 'profile-patents'],
    test_scores: ['test_scores', 'background-scores', 'profile-test-scores'],
    organizations: ['organizations', 'background-organizations', 'profile-organizations'],
    recommendations: ['recommendations', 'recommendations_received', 'background-recommendations'],
    causes: ['causes', 'member-causes'],
  };

  /** Scroll order so virtualized profile sections mount before extraction. */
  const PROFILE_SCROLL_KEYS = [
    'about',
    'experience',
    'education',
    'skills',
    'licenses_and_certifications',
    'certifications',
    'projects',
    'languages',
    'volunteer_experience',
    'courses',
    'honors_awards',
    'publications',
    'patents',
    'organizations',
    'recommendations',
    'test_scores',
    'causes',
  ];

  /** Verbatim-ish section blocks under "--- PROFILE SECTIONS (this member only) ---". */
  const PROFILE_FROM_PAGE_SPECS = [
    ['experience', 'EXPERIENCE (from page)'],
    ['education', 'EDUCATION (from page)'],
    ['skills', 'SKILLS (from page)'],
    ['licenses_and_certifications', 'LICENSES & CERTIFICATIONS (from page)'],
    ['certifications', 'CERTIFICATIONS (from page)'],
    ['projects', 'PROJECTS (from page)'],
    ['languages', 'LANGUAGES (from page)'],
    ['volunteer_experience', 'VOLUNTEER EXPERIENCE (from page)'],
    ['courses', 'COURSES (from page)'],
    ['honors_awards', 'HONORS & AWARDS (from page)'],
    ['publications', 'PUBLICATIONS (from page)'],
    ['patents', 'PATENTS (from page)'],
    ['organizations', 'ORGANIZATIONS (from page)'],
    ['recommendations', 'RECOMMENDATIONS (from page)'],
    ['test_scores', 'TEST SCORES (from page)'],
    ['causes', 'CAUSES (from page)'],
  ];

  function getProfileAnchor(slug) {
    const ids = PROFILE_SECTION_IDS[slug] || [slug];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) return el;
    }
    const main = rootEl();
    if (!main) return null;
    for (const id of ids) {
      const esc = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(id) : id.replace(/[^a-zA-Z0-9_-]/g, '');
      const byAttr =
        main.querySelector(`[id="${esc}"]`) ||
        main.querySelector(`[data-section="${esc}"]`) ||
        main.querySelector(`a[href="${`#${esc}`}"]`);
      if (byAttr) return byAttr;
    }
    return null;
  }

  /**
   * LinkedIn sometimes drops stable ids; locate a section root via data-view-name (locale-independent).
   */
  function sectionFromDataView(root, nameRes) {
    const r = root || document;
    for (const el of r.querySelectorAll('[data-view-name]')) {
      const v = String(el.getAttribute('data-view-name') || '').trim();
      if (!v) continue;
      for (const re of nameRes) {
        if (!re.test(v)) continue;
        const card =
          el.closest('section.artdeco-card') ||
          el.closest('div.artdeco-card') ||
          el.closest('section') ||
          el.closest('[data-view-name*="profile-card"]') ||
          el;
        if (card && isNodeInProfileMainColumn(card)) return card;
      }
    }
    return null;
  }

  /**
   * LinkedIn virtualizes Experience / Education / Skills until those regions scroll into view.
   * Drive the profile <main> scroller + anchor ids so list nodes mount before we read the DOM.
   */
  function primeProfileSections() {
    for (const main of getProfileScrollRoots()) {
      if (main && main.scrollHeight > (main.clientHeight || 0) + 50) {
        const h = main.scrollHeight;
        for (let i = 0; i <= 10; i++) {
          try {
            main.scrollTop = (h * i) / 10;
          } catch { /* ignore */ }
        }
      }
    }
    try {
      window.scrollTo(0, Math.min(document.body.scrollHeight, 8000));
    } catch { /* ignore */ }
    const mainRoot = rootEl();
    PROFILE_SCROLL_KEYS.forEach(sectionKey => {
      let el = getProfileAnchor(sectionKey);
      if (!el && mainRoot) {
        if (sectionKey === 'experience') el = sectionExperience(mainRoot);
        else if (sectionKey === 'education') el = sectionEducation(mainRoot);
        else if (sectionKey === 'skills') el = sectionSkills(mainRoot);
        else if (sectionKey === 'about') el = sectionAbout(mainRoot);
      }
      try {
        el?.scrollIntoView({ block: 'center', inline: 'nearest' });
      } catch { /* ignore */ }
    });
    /* Do not scroll main back to top — virtualized sections may unmount. */
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
        'h2.pvs-header__title',
        '.pvs-header__title',
        '[data-view-name*="profile-card"] h2',
        '[data-view-name*="profile"] h2 span[aria-hidden="true"]',
        'h2',
        'h3',
      ].join(', '),
    );
    nextHeading: for (const h of candidates) {
      const t = (h.textContent || h.innerText || '').replace(/\s+/g, ' ').trim();
      if (!t || t.length > 120) continue;
      for (const re of patterns) {
        if (!re.test(t)) continue;
        let card =
          h.closest('section.artdeco-card') ||
          h.closest('div.artdeco-card') ||
          h.closest('section') ||
          h.closest('[data-view-name*="profile-card"]') ||
          h.closest('[data-view-name]');
        const head = (card?.querySelector?.('h2, .pvs-header__title')?.textContent || '')
          .replace(/\s+/g, ' ')
          .trim();
        if (card && shouldSkipProfileSectionCardHead(head)) continue nextHeading;
        if (!card || card === h) {
          let p = h.parentElement;
          for (let d = 0; d < 14 && p; d++) {
            if (
              p.querySelector?.(
                'ul[class*="pvs-list"], li[class*="pvs-list"], li[class*="pvs-entity"], [data-view-name="profile-component-entity"]',
              )
            ) {
              card = p;
              break;
            }
            p = p.parentElement;
          }
        }
        if (card && isNodeInProfileMainColumn(card)) return card;
      }
    }
    return null;
  }

  function tx(sel, root) {
    return String((root || document).querySelector(sel)?.innerText ?? '').trim();
  }

  function txs(sel, root) {
    return [...(root || document).querySelectorAll(sel)]
      .map(n => String(n.innerText ?? '').trim())
      .filter(Boolean);
  }

  /** Section card that contains a profile anchor (tries LinkedIn id variants). */
  function sectionFor(slug) {
    const el = getProfileAnchor(slug);
    if (!el) return null;
    const card =
      cardRootFromAnchorEl(el) ||
      el.closest('section.artdeco-card') ||
      el.closest('div.artdeco-card') ||
      el.closest('section') ||
      el.closest('[data-view-name]') ||
      el.parentElement;
    if (card && !isNodeInProfileMainColumn(card)) return null;
    return card;
  }

  function sectionExperience(root) {
    return (
      sectionFor('experience') ||
      sectionFromDataView(root, [
        /(^|[-_\s])experience([-_]|$)/i,
        /work[-_\s]?history/i,
        /employment[-_\s]?history/i,
        /profile.*experience/i,
      ]) ||
      sectionByHeading(root, [
        /^Experience$/i,
        /^Work experience$/i,
        /^Employment$/i,
        /^Berufserfahrung$/i,
        /^Expérience$/i,
        /^Experiencia$/i,
      ])
    );
  }

  function sectionAbout(root) {
    return sectionFor('about') || sectionByHeading(root, [/^About$/i, /^Info$/i, /^Über mich$/i, /^À propos$/i, /^Acerca de$/i]);
  }

  function sectionSkills(root) {
    return (
      sectionFor('skills') ||
      sectionFromDataView(root, [/(^|[-_\s])skills?([-_]|$)/i, /profile[-_\s].*skill/i]) ||
      sectionByHeading(root, [/^Skills$/i, /^Compétences$/i, /^Kenntnisse$/i, /^Habilidades$/i])
    );
  }

  function sectionEducation(root) {
    return (
      sectionFor('education') ||
      sectionFromDataView(root, [/(^|[-_\s])education([-_]|$)/i, /academic/i, /profile.*education/i]) ||
      sectionByHeading(root, [
        /^Education$/i,
        /^Ausbildung$/i,
        /^Formation$/i,
        /^Educación$/i,
      ])
    );
  }

  function sectionCertifications(root) {
    return (
      sectionFor('licenses_and_certifications') ||
      sectionFor('certifications') ||
      sectionFromDataView(root, [
        /license|certif|credential|accreditation/i,
        /profile.*(license|certif)/i,
      ]) ||
      sectionByHeading(root, [
        /^Licenses\s+(&|and)\s+certifications$/i,
        /^Certifications$/i,
        /^Certificados$/i,
        /^Zertifikate$/i,
      ])
    );
  }

  function arHidden(item) {
    return txs('span[aria-hidden="true"]', item);
  }

  /** When LinkedIn omits aria-hidden spans, fall back to visible line chunks. */
  function rowTextParts(item) {
    let parts = arHidden(item);
    if (parts.length) return parts;
    parts = txs('.t-bold span[aria-hidden="true"]', item);
    if (parts.length) return parts;
    parts = txs('.hoverable-link-text span[aria-hidden="true"]', item);
    if (parts.length) return parts;
    const tb = [...item.querySelectorAll('.t-bold, [class*="t-bold"], .hoverable-link-text')]
      .map(n => (n.textContent || '').replace(/\s+/g, ' ').trim())
      .filter(s => s.length > 1 && s.length < 400 && !/^(show more|show all)$/i.test(s));
    if (tb.length) return tb.slice(0, 8);
    parts = txs('span[aria-hidden="true"]', item).filter(s => s.length > 1 && s.length < 400);
    if (parts.length) return parts.slice(0, 8);
    const t = (item.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length < 3) return [];
    const byDelim = t
      .split(/\s*[·•|]\s*|\s{2,}/)
      .map(s => String(s ?? '').trim())
      .filter(s => s.length > 1 && s.length < 500)
      .slice(0, 8);
    if (byDelim.length >= 2) return byDelim;
    /* Newer / flatter DOM: treat line breaks as separate fields (title / org / dates). */
    const byLines = t
      .split(/\n+/)
      .map(s => String(s ?? '').replace(/\s+/g, ' ').trim())
      .filter(s => s.length > 2 && !/^(show more|show all|message|connect)$/i.test(s))
      .slice(0, 8);
    return byLines.length >= 2 ? byLines : byDelim.length ? byDelim : byLines;
  }

  function listItems(sec) {
    if (!sec) return [];
    const seen = new Set();
    const out = [];
    const add = node => {
      if (!node || seen.has(node)) return;
      if (!isNodeInProfileMainColumn(node)) return;
      seen.add(node);
      out.push(node);
    };
    /* Avoid bare `ul > li` — it pulls nested lists + “People you may know” style rows into Experience/Skills. */
    sec
      .querySelectorAll(
        [
          'li[data-view-name="profile-component-entity"]',
          'div[data-view-name="profile-component-entity"]',
          'li[class*="pvs-list__paged-list-item"]',
          'li[class*="pvs-list__item--two-column"]',
          'li[class*="pvs-list__item--one-column"]',
          'li[class*="pvs-list__item"]',
          'div[class*="pvs-list__item"]',
          'li[class*="pvs-entity"]',
          'li.artdeco-list__item',
        ].join(', '),
      )
      .forEach(add);
    return out;
  }

  /** Experience cards sometimes embed “Skill · N endorsements” rows — not jobs. */
  function rowLooksLikeInlineSkillEndorsement(spans) {
    if (!spans || !spans.length) return false;
    const j = spans.join(' ').toLowerCase();
    if (/\b\d+\s+endorsements?\b/.test(j)) return true;
    if (
      spans.length <= 3 &&
      looksLikeSkillToken(String(spans[0] || '').trim()) &&
      (!spans[1] || /endorsement|endorsed|mutual connection/i.test(String(spans[1])))
    )
      return true;
    return false;
  }

  /**
   * Experience cards embed “skills used here” rows linking to `/details/skills/` without dates / employer.
   * Those are not positions — skip so they are not emitted as jobs (and not confused with role lines).
   */
  function expRowShouldBeSkippedAsSkillChip(item, spans) {
    if (!item || !spans || !spans.length) return false;
    if (rowLooksLikeInlineSkillEndorsement(spans)) return true;
    const hasSkillLink = item.querySelector?.('a[href*="/details/skills/"], a[href*="/overlay/skill"]');
    if (!hasSkillLink) return false;
    const blob = spans.join(' ').toLowerCase();
    if (/\b(20\d{2}\s*[-–]\s*\d{2,4}|20\d{2}\s*[-–]\s*present|[-–]\s*present)\b/i.test(blob)) return false;
    if (/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b.*\b20\d{2}\b/i.test(blob)) return false;
    if (/\b(full|part)[-\s]?time|contract|internship|freelance|self[-\s]?employed\b/i.test(blob)) return false;
    if (/\s+at\s+[a-z0-9]/i.test(blob)) return false;
    return true;
  }

  /** One text line per list row for Honors, Courses, Publications, etc. */
  function genericSectionLines(sec) {
    if (!sec) return [];
    const lines = [];
    listItems(sec).forEach(item => {
      const p = rowTextParts(item);
      if (p.length) lines.push(p.slice(0, 8).join(' | '));
      else {
        const raw = sanitizeLinkedInNoise((item.innerText || '').replace(/\s+/g, ' ').trim());
        if (raw.length > 12 && raw.length < 900) lines.push(raw);
      }
    });
    return lines;
  }

  /** Lines LinkedIn shows under skills (endorsement context, CTAs) — not skill names. */
  function isSkillLineNoise(text) {
    const t = String(text || '').trim();
    if (!t || t.length > 100) return true;
    if (/^show all\b|^show more\b|^see more\b|^show less\b/i.test(t)) return true;
    if (/^skills$/i.test(t)) return true;
    if (/^\d+\s+endorsements?$/i.test(t)) return true;
    if (/^endorse\b/i.test(t)) return true;
    if (/endorsement/i.test(t) && t.length < 60) return true;
    if (/^core team\b/i.test(t)) return true;
    /* "Role at Company" pattern — role names that ended up in the list */
    if (/\s+at\s+/i.test(t)) return true;
    /* Pure numbers (like endorsement count) */
    if (/^\d+$/.test(t)) return true;
    /* Lines that look like job titles without tech skills keywords */
    if (/^(ui|ux|ui\/ux)\s+(designer|developer|engineer|researcher|lead|manager|intern|head)\b/i.test(t)) return true;
    /* "and +N skills" suffix text from LinkedIn experience cards */
    if (/^and\s+\+\d+\s+skills?$/i.test(t)) return true;
    /* Exactly matches an activity/connection line */
    if (/^\d+\+?\s*(connection|follower|contact)s?$/i.test(t)) return true;
    /* Skills UI chrome / tabs / paywalls */
    if (/^industry\s+knowledge$/i.test(t)) return true;
    if (/^tools\s+(&|and)\s+technologies$/i.test(t)) return true;
    if (/^all$/i.test(t)) return true;
    if (/^other\s+skills$/i.test(t)) return true;
    if (/^interpersonal\s+skills$/i.test(t)) return true;
    if (/^(technical|soft|leadership|communication)\s+skills$/i.test(t)) return true;
    if (/^ad\s+options?$/i.test(t)) return true;
    if (/^submit$/i.test(t)) return true;
    if (
      /why\s+am\s+i\s+seeing\s+this\s+ad|manage\s+your\s+ad\s+preferences|hide\s+or\s+report|don'?t\s+want\s+to\s+see|your\s+feedback\s+will\s+help|it'?s\s+annoying|same\s+ad\s+too\s+often|please\s+let\s+us\s+know|report\s+this\s+ad|more\s+profiles\s+for\s+you|suggested\s+for\s+you|promoted|sponsored\s+content/i.test(
        t,
      )
    )
      return true;
    if (/try\s+premium|get\s+hired|linkedin\s+learning|newsletter|subscribe\b/i.test(t)) return true;
    if (/\bfor\s+rs\b|^rs[\s.,]|\b(usd|eur|gbp)\b/i.test(t)) return true;
    /* Marketing / client-list prose that leaks from overlays */
    if (/^clients?\s+include\b/i.test(t)) return true;
    if (/\b(and\s+)?many\s+more\b/i.test(t)) return true;
    if (/\bfeaturing\b/i.test(t) && t.length > 40) return true;
    if (/\b(click|tap)\s+here\b/i.test(t)) return true;
    /* Right-rail / discovery copy that sometimes shares list row patterns */
    if (
      /\b(people you may know|mutual connections?|suggested for you|similar profiles?|profiles similar|also viewed|who to follow|because you follow|because you view)\b/i.test(
        t,
      )
    )
      return true;
    /* LinkedIn “people also viewed” name + degree line, e.g. "Name · 3rd" */
    if (/·\s*\d+(st|nd|rd|th)\b/i.test(t) && t.length < 72) return true;
    /* Short role-at-company lines that leak from rails */
    if (/^.+\s+@\s+[A-Za-z0-9][\w.&\s-]{2,60}$/i.test(t) && !/\b(node|react|next|vue|nest)\.(js|ts)\b/i.test(t)) return true;
    return false;
  }

  /**
   * Extract skill names from the skills section.
   * Priority order:
   *   1. <a href="/details/skills/…"> — most reliable; every linked skill is a real skill
   *   2. Per-list-item first bold span only (not ALL bold text which also picks up role names)
   *   3. button[aria-label] that contains skill names (rare fallback)
   * Never use bulk `.t-bold` across the whole section — that picks up endorsing job titles too.
   */
  function collectSkillsFromSection(skillsSec) {
    const seen = new Set();
    const out  = [];
    /** LinkedIn `/details/skills/` links — trust label after UI-noise strip only. */
    const addFromSkillLink = raw => {
      const s = String(raw || '').trim();
      const firstLine = String(s.split(/\n/)[0] ?? '').trim();
      if (firstLine.length < 2 || firstLine.length > 100) return;
      if (isSkillLineNoise(firstLine) || !looksLikeSkillToken(firstLine)) return;
      const k = firstLine.toLowerCase();
      if (seen.has(k)) return;
      seen.add(k);
      out.push(firstLine);
    };
    const add = raw => {
      const s = String(raw || '').trim();
      const firstLine = String(s.split(/\n/)[0] ?? '').trim();
      if (firstLine.length < 2 || firstLine.length > 100) return;
      if (isSkillLineNoise(firstLine) || !looksLikeSkillToken(firstLine)) return;
      const k = firstLine.toLowerCase();
      if (seen.has(k)) return;
      seen.add(k);
      out.push(firstLine);
    };

    if (!skillsSec) return out;

    /* ── Method 1: Skill detail links (LinkedIn uses these for every skill) ── */
    skillsSec.querySelectorAll(
      'a[href*="/details/skills/"], a[href*="/overlay/skill"], a[data-field="skill_card_skill_topic"]',
    ).forEach(a => {
      if (!isNodeInProfileMainColumn(a)) return;
      /* Prefer the first bold span inside the link — LinkedIn skill URLs are authoritative */
      const boldSpan = a.querySelector('.t-bold span[aria-hidden="true"]');
      if (boldSpan) {
        addFromSkillLink(boldSpan.textContent || '');
        return;
      }
      const anySpan = a.querySelector('span[aria-hidden="true"]');
      if (anySpan) {
        addFromSkillLink(anySpan.textContent || '');
        return;
      }
      addFromSkillLink((a.innerText || '').split('\n')[0]);
    });

    /* ── Method 2: Per list-item, grab ONLY the first .t-bold span (the skill name) ── */
    skillsSec.querySelectorAll(
      'li[class*="pvs-list"], li[class*="pvs-entity"], li[data-view-name="profile-component-entity"]',
    ).forEach(li => {
      if (!isNodeInProfileMainColumn(li)) return;
      /* Skip items that have a /details/skills/ link already counted above */
      if (li.querySelector('a[href*="/details/skills/"], a[href*="/overlay/skill"]')) return;
      const bold = li.querySelector('.t-bold span[aria-hidden="true"]');
      if (bold) {
        const line = String(bold.textContent || '').trim().split('\n')[0].trim();
        if (looksLikeSkillToken(line)) add(line);
      }
    });

    /* ── Method 3: skill-assessment links ── */
    skillsSec.querySelectorAll('a[href*="/skill-assessment/"]').forEach(a => {
      if (!isNodeInProfileMainColumn(a)) return;
      const s = a.querySelector('span[aria-hidden="true"]');
      addFromSkillLink(s ? s.textContent : a.textContent);
    });

    /* ── Method 4: buttons with aria-label (rare LinkedIn layout variant) ── */
    if (out.length < 4) {
      skillsSec.querySelectorAll('button[aria-label]').forEach(btn => {
        if (!isNodeInProfileMainColumn(btn)) return;
        const lab = (btn.getAttribute('aria-label') || '').trim();
        const chunk = lab.split(/\s*[·•]\s*/)[0];
        if (chunk && chunk.length < 80 && !/endorse|show all|show more/i.test(lab) && looksLikeSkillToken(chunk)) add(chunk);
      });
    }

    return out;
  }

  /**
   * On `/in/…/details/skills/` (and similar) there is no #skills card — skill rows are still
   * `a[href*="/details/skills/"]` anywhere in the document. Merge those into `targetList`.
   */
  function mergeSkillAnchorsFromDocument(targetList) {
    if (!Array.isArray(targetList)) return;
    const seen = new Set(targetList.map(s => String(s).toLowerCase()));
    const add = raw => {
      const firstLine = String(raw || '')
        .trim()
        .split('\n')[0]
        .trim();
      if (firstLine.length < 2 || firstLine.length > 100) return;
      if (isSkillLineNoise(firstLine) || !looksLikeSkillToken(firstLine)) return;
      const k = firstLine.toLowerCase();
      if (seen.has(k)) return;
      seen.add(k);
      targetList.push(firstLine);
    };
    const scope = profileLayoutMain() || rootEl();
    if (!scope) return;
    scope.querySelectorAll('a[href*="/details/skills/"], a[href*="/overlay/skill"]').forEach(a => {
      if (!isNodeInProfileMainColumn(a)) return;
      const boldSpan = a.querySelector('.t-bold span[aria-hidden="true"]');
      if (boldSpan) {
        add(boldSpan.textContent || '');
        return;
      }
      const anySpan = a.querySelector('span[aria-hidden="true"]');
      if (anySpan) {
        add(anySpan.textContent || '');
        return;
      }
      add((a.innerText || '').split('\n')[0]);
    });
  }

  function cleanLines(text) {
    return String(text || '')
      .split('\n')
      .map(l => String(l ?? '').trim())
      .filter(Boolean)
      .join('\n');
  }

  /** Drop LinkedIn chrome / rails / footer lines from a text blob. */
  function sanitizeLinkedInNoise(text) {
    let s = String(text || '')
      .replace(/\s*…\s*more\s*$/gim, '')
      .replace(/\s*\.\.\.\s*more\s*$/gim, '')
      .trim();
    return s
      .split('\n')
      .map(l => String(l ?? '').trim())
      .filter(l => {
        if (!l) return false;
        const low = l.toLowerCase();
        if (/^(connect|follow|message|more|skip|show all|show more|show less)$/i.test(l)) return false;
        if (/^·\s*\d+(st|nd|rd|th)\+?$/i.test(l)) return false;
        if (/^\d+\+?\s*(connections?|followers?)$/i.test(l)) return false;
        if (/^\d[\d,]*\s+followers?$/i.test(l)) return false;
        if (
          /people you may know|more profiles for you|similar to|top voices|activity\b|^interests$/i.test(low) &&
          l.length < 80
        ) {
          return false;
        }
        if (
          /linkedin corporation|privacy & terms|ad choices|help center|select language|visit our help|manage your account|recommendation transparency|community guidelines|marketing solutions|talent solutions|accessibility$/i.test(
            low,
          )
        ) {
          return false;
        }
        if (
          /why\s+am\s+i\s+seeing|manage\s+your\s+ad\s+preferences|report\s+this\s+ad|hide\s+or\s+report|ad\s+options|don'?t\s+want\s+to\s+see|your\s+feedback\s+will\s+help|it'?s\s+annoying|same\s+ad\s+too\s+often|please\s+let\s+us\s+know|sponsored\s+content|promoted\s+post/i.test(
            low,
          ) &&
          l.length < 160
        ) {
          return false;
        }
        return true;
      })
      .join('\n')
      .trim();
  }

  /**
   * Sanitize anchored section cards but keep lines like "Show all" / "Show more" (LinkedIn skills UI).
   */
  function sanitizeProfileSectionBody(text) {
    let s = String(text || '')
      .replace(/\s*…\s*more\s*$/gim, '')
      .replace(/\s*\.\.\.\s*more\s*$/gim, '')
      .trim();
    return s
      .split('\n')
      .map(l => String(l ?? '').trim())
      .filter(l => {
        if (!l) return false;
        const low = l.toLowerCase();
        if (/^(connect|follow|message|more|skip)$/i.test(l)) return false;
        if (/^·\s*\d+(st|nd|rd|th)\+?$/i.test(l)) return false;
        if (/^\d+\+?\s*(connections?|followers?)$/i.test(l)) return false;
        if (/^\d[\d,]*\s+followers?$/i.test(l)) return false;
        if (
          /people you may know|more profiles for you|similar to|top voices|activity\b|^interests$/i.test(low) &&
          l.length < 80
        ) {
          return false;
        }
        if (
          /linkedin corporation|privacy & terms|ad choices|help center|select language|visit our help|manage your account|recommendation transparency|community guidelines|marketing solutions|talent solutions|accessibility$/i.test(
            low,
          )
        ) {
          return false;
        }
        if (
          /why\s+am\s+i\s+seeing|manage\s+your\s+ad\s+preferences|report\s+this\s+ad|hide\s+or\s+report|ad\s+options|don'?t\s+want\s+to\s+see|your\s+feedback\s+will\s+help|it'?s\s+annoying|same\s+ad\s+too\s+often|please\s+let\s+us\s+know|sponsored\s+content|promoted\s+post/i.test(
            low,
          ) &&
          l.length < 160
        ) {
          return false;
        }
        return true;
      })
      .join('\n')
      .trim();
  }

  function shouldSkipProfileSectionCardHead(head) {
    return (
      head &&
      /people you may know|more profiles for you|similar to|people who follow|also follow|^activity$/i.test(head)
    );
  }

  function isVisibleElement(el) {
    if (!el || !(el instanceof Element)) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 && r.height < 1) return false;
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
    return true;
  }

  const EMAIL_ADDR_RE = /[a-z0-9][a-z0-9._%+-]*@[a-z0-9][a-z0-9.-]*\.[a-z]{2,}/gi;

  /** First plausible address in free text (About, overlay, etc.). */
  function pickFirstValidEmail(text) {
    const raw = String(text || '').slice(0, 36000);
    if (!raw.trim()) return '';
    const bad =
      /linkedin\.com|lnkd\.in|example\.com|test\.com|schema\.org|w3\.org|mozilla\.org|sentry\.io|noreply|no-reply|donotreply|@2x\.|@3x\.|\.png@|\.jpg@/i;
    const matches = raw.match(EMAIL_ADDR_RE) || [];
    for (const addr of matches) {
      const e = addr.replace(/^mailto:/i, '').split('?')[0].split('#')[0].trim();
      if (e.length < 6 || e.length > 90) continue;
      if (bad.test(e)) continue;
      return e;
    }
    return '';
  }

  function harvestMailtoFromRoot(root) {
    if (!root) return '';
    for (const a of root.querySelectorAll('a[href^="mailto:"]')) {
      const e = (a.getAttribute('href') || '').replace(/^mailto:/i, '').split('?')[0].split('#')[0].trim();
      if (e && !/linkedin\.com/i.test(e)) return e;
    }
    return '';
  }

  function dismissProfileModalQuick() {
    try {
      document
        .querySelectorAll(
          '.artdeco-modal__dismiss, button[data-test-modal-close-btn], button[aria-label*="Dismiss"], [aria-label="Dismiss"]',
        )
        .forEach(btn => {
          if (isVisibleElement(btn)) btn.click();
        });
    } catch { /* ignore */ }
  }

  /**
   * Optional email path: open the member "Contact info" overlay. Default off (see async opts.tryContactInfo).
   * Href matching is strict so we do not click random /overlay/ links.
   */
  async function tryOpenContactInfoForEmail() {
    const main = rootEl();
    if (!main || !/\/in\/[^/]+/i.test(location.pathname || '')) return '';

    dismissProfileModalQuick();
    await new Promise(r => setTimeout(r, 160));

    let trigger = null;
    const consider = el => {
      if (!el || trigger) return;
      const vis = el.tagName === 'A' || el.tagName === 'BUTTON' ? el : el.closest('a, button');
      if (!vis || !isVisibleElement(vis)) return;
      const href = (vis.getAttribute('href') || '').toLowerCase();
      const al = (vis.getAttribute('aria-label') || '').trim();
      const txLo = (vis.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      const hrefLooksLikeMemberContact =
        /\/in\/[^/]+\/overlay\/contact-info/i.test(href) ||
        (href.includes('contact-info') && href.includes('/in/'));
      if (
        vis.id === 'top-card-text-details-contact-info' ||
        hrefLooksLikeMemberContact ||
        (/^contact info$/i.test(al) && (vis.tagName === 'BUTTON' || href.includes('/in/')))
      ) {
        trigger = vis;
      }
    };

    main.querySelectorAll('a[href*="contact-info"], button#top-card-text-details-contact-info').forEach(consider);

    if (!trigger) return '';

    try {
      trigger.scrollIntoView({ block: 'center' });
    } catch { /* ignore */ }
    await new Promise(r => setTimeout(r, 120));
    try {
      trigger.click();
    } catch { /* ignore */ }
    try {
      trigger.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    } catch { /* ignore */ }

    await new Promise(r => setTimeout(r, 820));

    let email = '';
    document.querySelectorAll('[role="dialog"], .artdeco-modal, aside.msg-overlay-container').forEach(root => {
      if (email || !isVisibleElement(root)) return;
      email = harvestMailtoFromRoot(root);
      if (!email) {
        const t = root.innerText || '';
        if (t.length > 20 && /email|e-mail|phone|birthday|website|address|contact/i.test(t))
          email = pickFirstValidEmail(t);
      }
    });

    dismissProfileModalQuick();
    await new Promise(r => setTimeout(r, 140));
    return email;
  }

  /**
   * Walk up from a section anchor to the card that actually lists items (LinkedIn layout varies).
   */
  function cardRootFromAnchorEl(el) {
    if (!el) return null;
    let n = el;
    for (let depth = 0; depth < 18 && n; depth++) {
      if (n.matches?.('section.artdeco-card, div.artdeco-card')) return n;
      const cls = String(n.className || '');
      if (
        n.querySelector?.(
          'ul[class*="pvs-list"], li[class*="pvs-list"], [data-view-name="profile-component-entity"]',
        ) &&
        (/pvs-|profile-component|experience|education|skill/i.test(cls) || n.tagName === 'SECTION')
      ) {
        return n;
      }
      n = n.parentElement;
    }
    return (
      el.closest('section.artdeco-card') ||
      el.closest('div.artdeco-card') ||
      el.closest('section') ||
      el.parentElement
    );
  }

  function controlLooksLikeExpand(tRaw) {
    const t = String(tRaw || '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!t || t.length > 140) return false;
    if (/^(message|connect|follow|save|saved|dismiss|close)$/i.test(t)) return false;
    return (
      /^show all\b/i.test(t) ||
      /^show more\b/i.test(t) ||
      /^see more\b/i.test(t) ||
      /show all \d+/i.test(t) ||
      /show more \d+/i.test(t) ||
      /see more positions|show all \d+ positions|show more positions|show all positions/i.test(t) ||
      /\d+\s+more\b/i.test(t) ||
      /alle anzeigen|weitere anzeigen|ver más|voir plus/i.test(t)
    );
  }

  /** Find an in-card "Show all" / "Show more" control (scoped so we do not hit Activity / PYMK). */
  function findExpandControlInCard(card) {
    if (!card) return null;
    const candidates = card.querySelectorAll(
      'button, a.artdeco-button, a[class*="artdeco-button"], span.artdeco-button__text, [role="button"], a[href="#"]',
    );
    for (const n of candidates) {
      if (!isVisibleElement(n)) continue;
      const direct = (n.innerText || n.textContent || '').replace(/\s+/g, ' ').trim();
      const aria = (n.getAttribute?.('aria-label') || '').replace(/\s+/g, ' ').trim();
      if (controlLooksLikeExpand(direct) || controlLooksLikeExpand(aria)) {
        const clickable =
          n.tagName === 'BUTTON'
            ? n
            : n.closest('button, a.artdeco-button, a[class*="artdeco-button"], [role="button"]') || n;
        if (clickable && card.contains(clickable) && isVisibleElement(clickable)) return clickable;
      }
    }
    return null;
  }

  /**
   * LinkedIn often renders "Show all … skills" outside the tight card root.
   * Search main below the #skills anchor for the expand control.
   */
  function findSkillsShowAllControl() {
    const main = rootEl();
    if (!main) return null;
    let anchor = getProfileAnchor('skills');
    if (!anchor) {
      const sec = sectionSkills(main);
      anchor = sec?.querySelector?.('h2, .pvs-header__title, [class*="pvs-header"]') || sec || null;
    }
    if (!anchor) return null;
    const card = cardRootFromAnchorEl(anchor);
    const inCard = findExpandControlInCard(card);
    if (inCard) return inCard;
    const skRect = anchor.getBoundingClientRect();
    for (const n of main.querySelectorAll('button, a, [role="button"]')) {
      if (!isVisibleElement(n)) continue;
      const r = n.getBoundingClientRect();
      if (r.top + 4 < skRect.top) continue;
      if (r.top > skRect.bottom + 1400) continue;
      const raw = `${n.innerText || ''} ${n.textContent || ''} ${n.getAttribute?.('aria-label') || ''}`.replace(
        /\s+/g,
        ' ',
      );
      const t = raw.trim();
      if (!controlLooksLikeExpand(t)) continue;
      const clickable =
        n.tagName === 'BUTTON'
          ? n
          : n.closest('button, a.artdeco-button, a[class*="optional-action"], [role="button"]') || n;
      if (!isVisibleElement(clickable)) continue;
      return clickable;
    }
    return null;
  }

  async function clickExpandInSectionCard(sectionKey, maxClicks, settleMs) {
    const wait = settleMs || (sectionKey === 'skills' ? 780 : 520);
    const main = rootEl();
    let el = getProfileAnchor(sectionKey);
    if (!el && main) {
      if (sectionKey === 'experience') el = sectionExperience(main);
      else if (sectionKey === 'education') el = sectionEducation(main);
      else if (sectionKey === 'skills') el = sectionSkills(main);
    }
    if (!el && sectionKey !== 'skills') return;
    const card = el ? cardRootFromAnchorEl(el) || el : null;
    if (!card && sectionKey !== 'skills') return;
    for (let c = 0; c < maxClicks; c++) {
      const btn = sectionKey === 'skills' ? findSkillsShowAllControl() : findExpandControlInCard(card);
      if (!btn) break;
      try {
        btn.scrollIntoView({ block: 'center', inline: 'nearest' });
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 160));
      try {
        btn.click();
      } catch { /* ignore */ }
      try {
        btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, wait));
    }
  }

  /** If LinkedIn opened a skills dialog / overlay, read its body (full list often lives here). */
  function skillsOverlaySupplementText() {
    const modals = document.querySelectorAll(
      '.artdeco-modal, div.msg-overlay-list-bubble, div[role="dialog"][aria-modal="true"], div[role="dialog"], aside.msg-overlay-container',
    );
    let best = '';
    for (const m of modals) {
      if (!isVisibleElement(m)) continue;
      const raw = (m.innerText || '').trim();
      if (raw.length < 36) continue;
      const low = raw.toLowerCase();
      /* Ads / feedback dialogs can be large and mention “endorse” — never treat as skills unless skill links exist */
      if (
        /why\s+am\s+i\s+seeing|ad\s+preferences|report\s+this\s+ad|don'?t\s+want\s+to\s+see|sponsored|promoted\s+post/i.test(
          low,
        )
      )
        continue;
      const hasSkillAnchors = !!m.querySelector('a[href*="/details/skills/"], a[href*="/overlay/skill"]');
      const looksSkillish =
        hasSkillAnchors ||
        (/skill|endorsement|compétence|habilidad|kenntnis/i.test(raw) &&
          /\/details\/skills\/|\/overlay\/skill/i.test(raw));
      if (!looksSkillish) continue;
      const cleaned = sanitizeProfileSectionBody(cleanLines(raw));
      if (cleaned.length > best.length) best = cleaned;
    }
    return best;
  }

  /**
   * After "Show all", LinkedIn exposes many `a[href*="/details/skills/"]` nodes (profile + modal).
   * Merge unique titles into skillsList (mutates array).
   */
  function mergeSkillsFromExpandedUi(skillsList) {
    const seen = new Set((skillsList || []).map(s => String(s).toLowerCase()));
    const add = raw => {
      const s = String(raw || '').trim();
      if (s.length < 2 || s.length > 92 || isSkillLineNoise(s) || !looksLikeSkillToken(s)) return;
      const k = s.toLowerCase();
      if (seen.has(k)) return;
      seen.add(k);
      skillsList.push(s);
    };
    const roots = [];
    const main = rootEl();
    if (main) roots.push(main);
    document
      .querySelectorAll(
        '.artdeco-modal[aria-hidden="false"], .artdeco-modal:not([aria-hidden="true"]), [role="dialog"][aria-modal="true"], aside.msg-overlay-container',
      )
      .forEach(el => {
        if (isVisibleElement(el)) roots.push(el);
      });
    roots.forEach(root => {
      const skipMainColumnCheck =
        root.classList?.contains('artdeco-modal') ||
        root.getAttribute?.('role') === 'dialog' ||
        /msg-overlay/i.test(root.className || '');
      root.querySelectorAll('a[href*="/details/skills/"], a[href*="/overlay/skill"]').forEach(a => {
        if (!isVisibleElement(a)) return;
        if (!skipMainColumnCheck && !isNodeInProfileMainColumn(a)) return;
        const s = String(
          tx('span[aria-hidden="true"]', a) ||
            (a.querySelector('.hoverable-link-text span[aria-hidden="true"]')?.textContent ?? '').trim() ||
            (a.querySelector('.hoverable-link-text')?.innerText ?? '').trim() ||
            ((a.innerText || '').split('\n')[0] ?? ''),
        ).trim();
        add(s);
      });
    });
    /* Overlay body is noisy if split naïvely; only keep lines that look like real skill tokens. */
    const overlay = skillsOverlaySupplementText();
    if (overlay) {
      overlay.split('\n').forEach(line => {
        const s = String(line ?? '').trim();
        if (looksLikeSkillToken(s)) add(s);
      });
    }
  }

  /**
   * Wait up to `maxMs` for a skills modal/dialog to become visible in the DOM.
   * Returns true when found, false on timeout.
   */
  async function waitForSkillsDialog(maxMs) {
    const deadline = Date.now() + (maxMs || 2500);
    while (Date.now() < deadline) {
      const dialogs = document.querySelectorAll(
        '[role="dialog"][aria-modal="true"], .artdeco-modal:not([aria-hidden="true"]), [role="dialog"]',
      );
      for (const d of dialogs) {
        if (!isVisibleElement(d)) continue;
        const txt = (d.innerText || '').toLowerCase();
        if (/why\s+am\s+i\s+seeing|report\s+this\s+ad|manage\s+your\s+ad\s+preferences|don'?t\s+want\s+to\s+see/i.test(txt))
          continue;
        if (
          (/skill|endorse|compétence|habilidad/i.test(txt) && txt.length > 40) ||
          d.querySelector('a[href*="/details/skills/"], a[href*="/overlay/skill"]')
        )
          return true;
      }
      await new Promise(r => setTimeout(r, 160));
    }
    return false;
  }

  /**
   * Expand truncated lists (skills "Show all", experience "Show more" / positions) before reading DOM.
   */
  async function expandProfileListsBeforeExtract() {
    /* `/in/…/details/…` is a different shell — "Show all" heuristics hit the wrong controls. */
    if (/\/in\/[^/]+\/details\//i.test(window.location.pathname || '')) return;
    const main0 = rootEl();
    try {
      (getProfileAnchor('skills') || (main0 && sectionSkills(main0)))?.scrollIntoView({ block: 'center' });
    } catch { /* ignore */ }
    await new Promise(r => setTimeout(r, 350));

    /* Click "Show all skills" — one attempt, then wait for dialog */
    await clickExpandInSectionCard('skills', 1, 400);
    const dialogOpened = await waitForSkillsDialog(2800);
    if (!dialogOpened) {
      /* Retry once more in case first click missed */
      await clickExpandInSectionCard('skills', 1, 400);
      await waitForSkillsDialog(1800);
    }
    /* Extra settle time so skill links render inside the dialog */
    await new Promise(r => setTimeout(r, 600));

    await clickExpandInSectionCard('experience', 5, 520);
    await clickExpandInSectionCard('education', 2, 520);
    const main = rootEl();
    if (main) {
      try {
        getProfileAnchor('experience')?.scrollIntoView({ block: 'start' });
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 280));
      try {
        getProfileAnchor('skills')?.scrollIntoView({ block: 'center' });
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 400));
      try {
        main.scrollTop = Math.min(main.scrollHeight, main.scrollTop + 400);
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 220));
    }
  }

  function resolveSectionCardFromMain(sectionKey, main) {
    if (!main) return null;
    switch (sectionKey) {
      case 'experience':
        return sectionExperience(main);
      case 'education':
        return sectionEducation(main);
      case 'skills':
        return sectionSkills(main);
      case 'about':
        return sectionAbout(main);
      case 'licenses_and_certifications':
        return sectionFor('licenses_and_certifications') || sectionCertifications(main);
      case 'certifications':
        return sectionFor('certifications') || sectionCertifications(main);
      default:
        return sectionFor(sectionKey);
    }
  }

  /** Raw card text for one logical section (experience, education, …). */
  function getCardInnerBySectionKey(sectionKey, maxLen) {
    const main = rootEl();
    const tryCard = card => {
      if (!card || !isNodeInProfileMainColumn(card)) return '';
      const head = (card.querySelector('h2, .pvs-header__title')?.innerText || '')
        .replace(/\s+/g, ' ')
        .trim();
      if (shouldSkipProfileSectionCardHead(head)) return '';
      let body = sanitizeProfileSectionBody(cleanLines((card.innerText || '').trim()));
      if (sectionKey === 'skills') {
        /* Prefer the expanded overlay if it has more content */
        const overlay = skillsOverlaySupplementText();
        if (overlay && overlay.length > (body?.length || 0) + 40) body = overlay;
        /* Strip endorsement-context lines from the skills section body so the output is clean */
        body = body
          .split('\n')
          .filter(l => {
            const t = String(l ?? '').trim();
            if (!t) return false;
            if (/^skills$/i.test(t)) return true;
            /* Drop obvious noise; keep real lines (looksLikeSkillToken was too strict and emptied the card). */
            return !isSkillLineNoise(t);
          })
          .join('\n');
      }
      if (body.length < 12) return '';
      if (body.length > maxLen) body = `${body.slice(0, maxLen)}\n…`;
      return body;
    };
    const el = getProfileAnchor(sectionKey);
    if (el) {
      const fromAnchor = tryCard(cardRootFromAnchorEl(el));
      if (fromAnchor) return fromAnchor;
    }
    return tryCard(resolveSectionCardFromMain(sectionKey, main));
  }

  function buildProfileSectionsFromPageBlock(maxPerSection) {
    const max = maxPerSection || 5200;
    const parts = [];
    for (const [key, label] of PROFILE_FROM_PAGE_SPECS) {
      const body = getCardInnerBySectionKey(key, max);
      if (!body) continue;
      parts.push(`${label}\n${body}`);
    }
    return parts.join('\n\n');
  }

  /**
   * Returns true if `text` looks like a genuine skill token (used to guard the raw-card fallback).
   * Accepts: "Web Design", "Adobe XD", "React.js", "C++", "Node.js", etc.
   * Rejects: multi-word job-title phrases like "UI UX Designer", "Full-time", date ranges, etc.
   */
  function looksLikeSkillToken(text) {
    const t = String(text || '').trim();
    if (!t || t.length < 2 || t.length > 72) return false;
    if (isSkillLineNoise(t)) return false;
    const words = t.split(/\s+/).filter(Boolean);
    if (words.length > 9) return false;
    if (/https?:\/\/|www\.\w/i.test(t)) return false;
    /* Reject first-person / promo blurbs */
    if (/\b(we've|we\s+have|i\s+specialize|our\s+clients?|book\s+a\s+call)\b/i.test(t)) return false;
    /* Reject obvious job-title patterns: "X Designer/Developer/Manager/Engineer/Lead/Intern/Head" */
    if (/\b(designer|developer|engineer|manager|researcher|lead|intern|head|coordinator|analyst|architect|consultant|director|officer|specialist|executive|strategist)\s*$/i.test(t)) return false;
    /* “Python Dev”, “MERN Dev” style role shorthand */
    if (/\b(dev|devops)\s*$/i.test(t) && t.split(/\s+/).length <= 3) return false;
    /* Reject employment types */
    if (/^(full[-\s]?time|part[-\s]?time|freelance|contract|remote|on[-\s]?site|hybrid)$/i.test(t)) return false;
    /* Reject date ranges */
    if (/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b.*\d{4}/i.test(t)) return false;
    if (/^\d{4}\s*[-–]\s*(\d{4}|present)/i.test(t)) return false;
    /* Long comma-heavy lines are usually lists of brands, not one skill */
    if ((t.match(/,/g) || []).length >= 2 && t.length > 48) return false;
    return true;
  }

  /** Final pass: keep only plausible skill labels for export / UI. */
  function refineSkillsListForExport(list) {
    const seen = new Set();
    const out = [];
    for (const raw of list || []) {
      const s = String(raw || '').trim();
      if (!s || isSkillLineNoise(s) || !looksLikeSkillToken(s)) continue;
      const k = s.toLowerCase();
      if (seen.has(k)) continue;
      seen.add(k);
      out.push(s);
    }
    return out;
  }

  /** Top "Skills:" line — real skill names only (no "X at Company", "Show all", endorsements). */
  function skillsCommaPreviewLine(skillsSec, skillsList) {
    const fromList = [];
    const seen = new Set();
    for (const raw of skillsList || []) {
      const s = String(raw || '').trim();
      if (!s || isSkillLineNoise(s) || !looksLikeSkillToken(s) || seen.has(s.toLowerCase())) continue;
      seen.add(s.toLowerCase());
      fromList.push(s);
    }
    if (fromList.length) {
      const j = fromList.slice(0, 120).join(', ');
      return j.length > 2600 ? `${j.slice(0, 2597)}…` : j;
    }
    /* Fallback: parse card body text, but apply stricter skill-token guard */
    let body = getCardInnerBySectionKey('skills', 9000);
    if (!body && skillsSec) {
      body = sanitizeProfileSectionBody(cleanLines((skillsSec.innerText || '').trim()));
    }
    if (body && body.length > 12) {
      const lines = body.split('\n').map(l => String(l ?? '').trim()).filter(Boolean);
      const filtered = lines.filter((l, idx) => {
        if (idx === 0 && /^skills$/i.test(l)) return false;
        return looksLikeSkillToken(l);
      });
      const joined = filtered.join(', ').replace(/\s+,/g, ',').trim();
      if (joined.length > 8) return joined.length > 2600 ? `${joined.slice(0, 2597)}…` : joined;
    }
    return '';
  }

  /** Month index (year * 12 + monthIndex) for overlap math; null if unparseable. */
  function parseYrMoToMonthIndex(str) {
    const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
    const st = String(str ?? '').trim();
    if (!st) return null;
    if (/present|current/i.test(st)) return new Date().getFullYear() * 12 + new Date().getMonth();
    const m = st.match(/([A-Za-z]{3,9})[.\s,]+(\d{4})/);
    if (m) {
      const mi = months.indexOf(m[1].toLowerCase().slice(0, 3));
      const y = parseInt(m[2], 10);
      if (mi >= 0 && !Number.isNaN(y)) return y * 12 + mi;
    }
    const yOnly = st.match(/\b(19|20)\d{2}\b/);
    return yOnly && !Number.isNaN(parseInt(yOnly[0], 10)) ? parseInt(yOnly[0], 10) * 12 : null;
  }

  /** Prefer calendar range over embedded "X yrs" so we can merge overlaps across roles. */
  function parseMonthsFromDates(dates) {
    if (!dates) return 0;
    const raw = String(dates);
    const parts = raw.split(/[–—-]/).map(s => String(s ?? '').trim());
    if (parts.length >= 2) {
      const s = parseYrMoToMonthIndex(parts[0]);
      const e = parseYrMoToMonthIndex(parts[1]);
      if (s != null && e != null && e >= s) return e - s;
    }
    const dot = raw.match(/(\d+)\s+yr[s]?\s*(\d+)?\s*mo[s]?/i);
    if (dot) return parseInt(dot[1] || 0, 10) * 12 + parseInt(dot[2] || 0, 10);
    const yr = raw.match(/(\d+)\s+yr[s]?\b/i);
    if (yr) return parseInt(yr[1], 10) * 12;
    return 0;
  }

  function parseCalendarRangeFromDates(dates) {
    const raw = String(dates || '').trim();
    if (!raw) return null;
    const parts = raw.split(/[–—-]/).map(s => String(s ?? '').trim()).filter(Boolean);
    if (parts.length < 2) return null;
    const start = parseYrMoToMonthIndex(parts[0]);
    const end = parseYrMoToMonthIndex(parts[1]);
    if (start == null || end == null || end < start) return null;
    return { start, end };
  }

  /** Normalize date lines so education vs duplicate rows match despite dash/space variants. */
  function normalizedDatesKey(dates) {
    return String(dates || '')
      .replace(/[–—]/g, '-')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  function buildEducationDateIndex(eduItems) {
    const norm = new Set();
    const ranges = new Set();
    for (const e of eduItems || []) {
      const nd = normalizedDatesKey(e.dates);
      if (nd) norm.add(nd);
      const cal = parseCalendarRangeFromDates(e.dates);
      if (cal) ranges.add(`${cal.start}:${cal.end}`);
    }
    return { norm, ranges };
  }

  function experienceDatesOverlapEducation(dates, eduIdx) {
    if (!eduIdx) return false;
    const nd = normalizedDatesKey(dates);
    if (nd && eduIdx.norm.has(nd)) return true;
    const cal = parseCalendarRangeFromDates(dates);
    if (cal && eduIdx.ranges.has(`${cal.start}:${cal.end}`)) return true;
    return false;
  }

  /**
   * LinkedIn sometimes mounts an education card inside the Experience list, or row order shifts so
   * school dates are parsed as a job — that inflates years_experience. Drop those rows.
   */
  function experienceRowLooksLikeEducation(item, row) {
    if (!item || !row) return false;
    const role = String(row.role || '').trim();
    const company = String(row.company || '').trim();
    const desc = String(row.desc || '').trim();
    const blob = `${role}\n${company}\n${desc}`.toLowerCase();
    try {
      if (item.querySelector?.('a[href*="/school/"]')) return true;
    } catch {
      /* ignore */
    }
    if (/\bfield\s+of\s+study\b|\bactivities\s+and\s+societies\b|\bgrade\b/.test(blob)) return true;
    const degreeRe =
      /\b(bachelor|bachelors|master|masters|mba|phd|ph\.?\s*d\.?|doctorate|doctoral|m\.?phil|b\.?s\.?\b|m\.?s\.?\b|m\.?sc\.?\b|b\.?e\.?\b|b\.?tech|m\.?tech|b\.?a\.?\b|b\.?sc\.?\b|m\.?eng|associate'?s?\s+degree|undergraduate|graduate\s+degree|diploma\s+in)\b/i;
    const schoolish =
      /\b(university|college|polytechnic|école|escuela|uni\s+de\b|institute\s+of\s+technology|academy)\b/i.test(blob) ||
      /\b(high\s+school|secondary\s+school)\b/i.test(blob);
    if (degreeRe.test(blob) && schoolish) return true;
    if (/\b(bachelor|master|doctor|mba|associate)\'?s?\s+degree'?s?\b/i.test(role)) return true;
    if (/\bstudent\b/i.test(role) && schoolish) return true;
    return false;
  }

  /**
   * LinkedIn often lists overlapping/nested roles each with full tenure; summing durations inflates
   * "years of experience". Merge calendar ranges, then fall back to the longest single duration hint.
   */
  function totalExperienceMonthsFromExpItems(items) {
    const ranges = [];
    let maxDurationHint = 0;
    for (const { dates } of items) {
      const cal = parseCalendarRangeFromDates(dates);
      if (cal) ranges.push(cal);
      else {
        const raw = String(dates || '');
        const dot = raw.match(/(\d+)\s+yr[s]?\s*(\d+)?\s*mo[s]?/i);
        if (dot) {
          const mo = parseInt(dot[1] || 0, 10) * 12 + parseInt(dot[2] || 0, 10);
          if (mo > 0 && mo < 720) maxDurationHint = Math.max(maxDurationHint, mo);
        } else {
          const yr = raw.match(/(\d+)\s+yr[s]?\b/i);
          if (yr) {
            const mo = parseInt(yr[1], 10) * 12;
            if (mo > 0 && mo < 720) maxDurationHint = Math.max(maxDurationHint, mo);
          }
        }
      }
    }
    if (ranges.length) {
      ranges.sort((a, b) => a.start - b.start);
      const merged = [];
      for (const iv of ranges) {
        if (!merged.length || iv.start > merged[merged.length - 1].end)
          merged.push({ start: iv.start, end: iv.end });
        else merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, iv.end);
      }
      let sum = 0;
      for (const iv of merged) sum += iv.end - iv.start;
      return sum;
    }
    if (maxDurationHint > 0) return maxDurationHint;
    let maxLegacy = 0;
    for (const { dates } of items) maxLegacy = Math.max(maxLegacy, parseMonthsFromDates(dates));
    return maxLegacy;
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
    const parts = slug.split('-').map(p => String(p ?? '').trim()).filter(Boolean);
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

  globalThis.__rezumeExtractLinkedIn = function rezumeExtractLinkedIn(req) {
    const opts = req && typeof req === 'object' ? req : {};
    if (!isLinkedInMemberPageHostname()) return wrongPageExtractResult();
    const skipPrime = Boolean(opts.skipPrime);
    if (!skipPrime) {
      globalThis.__rezumePrefetchedEmail = '';
      primeProfileSections();
    }

    const main = rootEl();

    let nameFromSlug = '';
    try {
      const m = window.location.pathname.match(/\/in\/([^/?#]+)/i);
      if (m) nameFromSlug = humanNameFromLinkedInSlug(m[1]);
    } catch { /* ignore */ }

    const topCard =
      document.querySelector('[data-view-name="profile-top-card"]') ||
      document.querySelector('[data-view-name="profile-card"]') ||
      document.querySelector('.top-card-layout') ||
      null;

    let nameGuess = '';
    if (topCard) {
      nameGuess =
        (topCard.querySelector('[data-anonymize="person-name"]')?.textContent || '').replace(/\s+/g, ' ').trim() ||
        (topCard.querySelector('h1')?.innerText || '').replace(/\s+/g, ' ').trim() ||
        '';
    }
    if (!nameGuess)
      nameGuess =
        tx('[data-anonymize="person-name"]') ||
        tx('h1.text-heading-xlarge') ||
        tx('main h1[class*="break-words"]') ||
        tx('.pv-text-details__left-panel h1') ||
        tx('.top-card-layout__title') ||
        tx('main .ph5.pb5 h1') ||
        tx('main h1.break-words') ||
        tx('main h1') ||
        '';

    function looksLikeSectionHeading(s) {
      const t = String(s ?? '').trim();
      if (!t) return true;
      if (t.length > 90) return true;
      return /^(experience|education|skills|about|activity|interests|people|analytics|services)$/i.test(t);
    }

    let nameFinal = String(nameGuess ?? '').trim();
    if (!nameFinal || looksLikeSectionHeading(nameFinal)) nameFinal = nameFromSlug;

    let title = '';
    if (topCard) {
      title =
        (topCard.querySelector('.text-body-medium.break-words')?.innerText || '').replace(/\s+/g, ' ').trim() ||
        (topCard.querySelector('div[class*="headline"]')?.innerText || '').replace(/\s+/g, ' ').trim() ||
        (topCard.querySelector('[data-generated-suggestion-target] .text-body-medium')?.innerText || '')
          .replace(/\s+/g, ' ')
          .trim() ||
        '';
    }
    if (!title)
      title =
        tx('.text-body-medium.break-words') ||
        tx('div.text-body-medium.break-words') ||
        tx('.pv-text-details__left-panel .text-body-medium') ||
        tx('.top-card-layout__headline') ||
        tx('[data-generated-suggestion-target] .text-body-medium') ||
        tx('main .text-body-medium');

    let profileLocation = '';
    if (topCard) {
      profileLocation =
        (topCard.querySelector('.text-body-small.inline.t-black--light.break-words')?.innerText || '')
          .replace(/\s+/g, ' ')
          .trim() ||
        (topCard.querySelector('span.text-body-small.inline')?.innerText || '').replace(/\s+/g, ' ').trim() ||
        '';
    }
    if (!profileLocation)
      profileLocation =
        tx('.text-body-small.inline.t-black--light.break-words') ||
        tx('span.text-body-small.inline.t-black--light') ||
        tx('.pb2 .t-black--light') ||
        tx('.top-card__subline-item') ||
        tx('span.text-body-small.inline');

    /* LinkedIn `/in/…/details/skills|experience|…` uses a slim header (entity lockup), not the main top card. */
    if (/\/in\/[^/]+\/details\//i.test(window.location.pathname || '')) {
      const lu =
        document.querySelector('.artdeco-entity-lockup') ||
        document.querySelector('[data-view-name="profile-top-card-member-info"]') ||
        document.querySelector('header .artdeco-entity-lockup');
      if (lu) {
        const tn =
          (lu.querySelector('.artdeco-entity-lockup__title span[aria-hidden="true"]')?.textContent || '').trim() ||
          (lu.querySelector('.artdeco-entity-lockup__title')?.innerText || '').trim();
        if (tn && tn.length > 1 && !looksLikeSectionHeading(tn)) nameFinal = tn;
        const tst = (lu.querySelector('.artdeco-entity-lockup__subtitle')?.innerText || '')
          .replace(/\s+/g, ' ')
          .trim();
        if (tst && tst.length > 2) title = tst;
        const tmet = (lu.querySelector('.artdeco-entity-lockup__metadata')?.innerText || '')
          .replace(/\s+/g, ' ')
          .trim();
        if (tmet && tmet.length > 2 && !String(profileLocation || '').trim()) profileLocation = tmet;
      }
    }

    let email = String(globalThis.__rezumePrefetchedEmail || '').trim();
    globalThis.__rezumePrefetchedEmail = '';
    if (!email) email = harvestMailtoFromRoot(main);

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
      about = sanitizeLinkedInNoise(cleanLines(about).slice(0, 6000));
    }

    if (!email && about) email = pickFirstValidEmail(about);
    if (!email) email = pickFirstValidEmail((main.innerText || '').slice(0, 42000));

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
    const eduDateIdx = buildEducationDateIndex(eduItems);

    const expRowsPending = [];
    const expSec = sectionExperience(main);
    listItems(expSec).forEach(item => {
      const spans = rowTextParts(item);
      if (!spans.length) return;
      if (rowLooksLikeInlineSkillEndorsement(spans)) return;
      if (expRowShouldBeSkippedAsSkillChip(item, spans)) return;
      const subItems = item.querySelectorAll('li.pvs-list__item--with-top-padding');
      if (subItems.length) {
        const companyName = spans[0] || '';
        subItems.forEach(sub => {
          const ss = rowTextParts(sub);
          if (!ss.length) return;
          if (rowLooksLikeInlineSkillEndorsement(ss)) return;
          if (expRowShouldBeSkippedAsSkillChip(sub, ss)) return;
          expRowsPending.push({
            item: sub,
            role: ss[0],
            company: companyName,
            dates: ss[1] || '',
            desc: ss.slice(2).join(' '),
          });
        });
      } else {
        expRowsPending.push({
          item,
          role: spans[0] || '',
          company: spans[1] || '',
          dates: spans[2] || '',
          desc: spans.slice(3).join(' '),
        });
      }
    });
    const expItems = expRowsPending
      .filter(
        r =>
          !experienceRowLooksLikeEducation(r.item, r) &&
          !experienceDatesOverlapEducation(r.dates, eduDateIdx),
      )
      .map(r => ({ role: r.role, company: r.company, dates: r.dates, desc: r.desc }));

    const skillsSec = sectionSkills(main);
    const skillsList = collectSkillsFromSection(skillsSec);
    mergeSkillsFromExpandedUi(skillsList);
    /* Full skills list page has no #skills section — harvest anchors from the whole document. */
    if (/\/in\/[^/]+\/details\/skills/i.test(window.location.pathname || '') || skillsList.length === 0)
      mergeSkillAnchorsFromDocument(skillsList);
    {
      const refined = refineSkillsListForExport(skillsList);
      skillsList.length = 0;
      refined.forEach(s => skillsList.push(s));
    }

    const certsList = [];
    const seenCertKeys = new Set();
    const pushCertFromItem = item => {
      const spans = rowTextParts(item);
      if (!spans.length) return;
      const key = (spans[0] || '').toLowerCase().slice(0, 120);
      if (!key || seenCertKeys.has(key)) return;
      seenCertKeys.add(key);
      const line = spans.slice(0, 6).join(' | ').trim();
      if (line.length > 3) certsList.push(line.length > 280 ? `${line.slice(0, 277)}…` : line);
    };
    const certSections = [];
    const addCertSection = sec => {
      if (!sec) return;
      if (certSections.some(s => s === sec)) return;
      certSections.push(sec);
    };
    addCertSection(sectionCertifications(main));
    addCertSection(sectionFor('licenses_and_certifications'));
    addCertSection(sectionFor('certifications'));
    certSections.forEach(certSec => listItems(certSec).forEach(pushCertFromItem));

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
    const projSec = sectionFor('projects') || sectionByHeading(main, [/^Projects$/i, /^Projets$/i]);
    listItems(projSec).forEach(item => {
      const spans = rowTextParts(item);
      if (spans[0]) projects.push(spans.slice(0, 5).join(' | '));
    });

    const coursesSec =
      sectionFor('courses') || sectionByHeading(main, [/^Courses$/i, /^Coursework$/i, /^Cursos$/i]);
    const coursesLines = genericSectionLines(coursesSec);
    const honorsSec =
      sectionFor('honors_awards') ||
      sectionByHeading(main, [/^Honors and awards$/i, /^Honors$/i, /^Awards$/i, /^Distinctions$/i]);
    const honorsLines = genericSectionLines(honorsSec);
    const pubSec = sectionFor('publications') || sectionByHeading(main, [/^Publications$/i]);
    const publicationsLines = genericSectionLines(pubSec);
    const patentSec = sectionFor('patents') || sectionByHeading(main, [/^Patents$/i]);
    const patentsLines = genericSectionLines(patentSec);
    const orgSec = sectionFor('organizations') || sectionByHeading(main, [/^Organizations$/i, /^Organisations$/i]);
    const organizationsLines = genericSectionLines(orgSec);
    const recSec =
      sectionFor('recommendations') ||
      sectionByHeading(main, [/^Recommendations$/i, /^Recommendations received$/i]);
    const recommendationsLines = genericSectionLines(recSec).map(l => l.slice(0, 500));
    const scoresSec = sectionFor('test_scores') || sectionByHeading(main, [/^Test scores$/i, /^Scores$/i]);
    const testScoresLines = genericSectionLines(scoresSec);
    const causesSec = sectionFor('causes') || sectionByHeading(main, [/^Causes$/i]);
    const causesLines = genericSectionLines(causesSec);

    let yearsExperience = null;
    if (expItems.length) {
      const totalMonths = totalExperienceMonthsFromExpItems(expItems);
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

    const skillsCommaTop = skillsCommaPreviewLine(skillsSec, skillsList);
    const skillsExportLine =
      skillsCommaTop ||
      skillsList
        .map(s => String(s).trim())
        .filter(s => s && !isSkillLineNoise(s) && looksLikeSkillToken(s))
        .slice(0, 120)
        .join(', ');
    const profileSectionsBlock = buildProfileSectionsFromPageBlock(5200);

    const lines = [];
    if (nameFinal) lines.push(`Name: ${nameFinal}`);
    lines.push('');
    lines.push(skillsExportLine ? `Skills: ${skillsExportLine}` : 'Skills: ');
    lines.push('');

    if (about) {
      lines.push('SUMMARY / ABOUT');
      lines.push(about);
      lines.push('');
    }

    const appendStructuredFallback = () => {
      if (title) lines.push(`Current Title: ${title}`);
      if (profileLocation) lines.push(`Location: ${profileLocation}`);
      if (email) lines.push(`Email: ${email}`);
      if (phone) lines.push(`Phone: ${phone}`);
      if (website) lines.push(`Website: ${website}`);
      if (yearsExperience) lines.push(`Years of Experience: ${yearsExperience}`);
      if (highestDegree) lines.push(`Highest Degree: ${highestDegree}`);
      if (title || profileLocation || email || phone || website || yearsExperience || highestDegree) lines.push('');

      if (expItems.length) {
        lines.push('WORK EXPERIENCE');
        expItems.forEach(({ role, company, dates, desc }) => {
          lines.push(`  ${role}${company ? ' @ ' + company : ''}${dates ? ' | ' + dates : ''}`);
          if (desc) lines.push(`    ${desc.slice(0, 520)}`);
        });
        lines.push('');
      }

      if (eduItems.length) {
        lines.push('EDUCATION');
        eduItems.forEach(({ school, degree, field, dates, desc }) => {
          const deg = [degree, field].filter(Boolean).join(', ');
          lines.push(`  ${school}${deg ? ' | ' + deg : ''}${dates ? ' | ' + dates : ''}`);
          if (desc) lines.push(`    ${desc.slice(0, 320)}`);
        });
        lines.push('');
      }

      {
        const skClean = skillsList
          .map(s => String(s ?? '').trim())
          .filter(s => s && !isSkillLineNoise(s) && looksLikeSkillToken(s));
        if (skClean.length) {
          lines.push('SKILLS');
          lines.push(skClean.slice(0, 120).join(', '));
          lines.push('');
        }
      }

      if (certsList.length) {
        lines.push('LICENSES & CERTIFICATIONS');
        certsList.slice(0, 60).forEach(c => lines.push(`  ${c}`));
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

      if (coursesLines.length) {
        lines.push('COURSES');
        coursesLines.slice(0, 40).forEach(c => lines.push(`  ${c}`));
        lines.push('');
      }

      if (honorsLines.length) {
        lines.push('HONORS & AWARDS');
        honorsLines.slice(0, 35).forEach(h => lines.push(`  ${h}`));
        lines.push('');
      }

      if (publicationsLines.length) {
        lines.push('PUBLICATIONS');
        publicationsLines.slice(0, 35).forEach(p => lines.push(`  ${p}`));
        lines.push('');
      }

      if (patentsLines.length) {
        lines.push('PATENTS');
        patentsLines.slice(0, 25).forEach(p => lines.push(`  ${p}`));
        lines.push('');
      }

      if (organizationsLines.length) {
        lines.push('ORGANIZATIONS');
        organizationsLines.slice(0, 25).forEach(o => lines.push(`  ${o}`));
        lines.push('');
      }

      if (recommendationsLines.length) {
        lines.push('RECOMMENDATIONS');
        recommendationsLines.slice(0, 20).forEach(r => lines.push(`  ${r}`));
        lines.push('');
      }

      if (testScoresLines.length) {
        lines.push('TEST SCORES');
        testScoresLines.slice(0, 15).forEach(s => lines.push(`  ${s}`));
        lines.push('');
      }

      if (causesLines.length) {
        lines.push('CAUSES');
        causesLines.slice(0, 15).forEach(c => lines.push(`  ${c}`));
        lines.push('');
      }
    };

    if (profileSectionsBlock.length > 40) {
      lines.push('--- PROFILE SECTIONS (this member only) ---');
      lines.push(profileSectionsBlock);
    } else {
      appendStructuredFallback();
    }

    let fullText = lines.join('\n').trim().slice(0, 28000);

    const hasSections =
      about.length > 40 ||
      expItems.length > 0 ||
      eduItems.length > 0 ||
      skillsList.length > 0 ||
      certsList.length > 0 ||
      profileSectionsBlock.length > 40;

    /* Last resort: URL slug gives at least a searchable name line */
    if (!fullText.trim() && nameFromSlug) {
      fullText = `Name (from profile URL): ${nameFromSlug}\n\nOpen the profile in LinkedIn and scroll to load About/Experience, then click Grab LinkedIn again.`;
    }

    /* Emergency fallback when LinkedIn changed selectors or virtualization left lists empty */
    if (fullText.length < 120 && /\/in\/[^/]+/i.test(window.location.pathname || '')) {
      const parts = [];
      const push = (s, max) => {
        const t = String(s || '')
          .replace(/\s+/g, ' ')
          .trim();
        if (t.length > 8) parts.push(t.slice(0, max || 4000));
      };
      push(tx('h1.text-heading-xlarge') || tx('main h1'), 400);
      push(tx('.text-body-medium.break-words') || tx('main .text-body-medium'), 500);
      push(tx('[data-anonymize="person-name"]'), 200);
      const root = rootEl();
      if (root && (root.innerText || '').length > 80)
        push(sanitizeLinkedInNoise(cleanLines((root.innerText || '').trim())).slice(0, 9000), 9000);
      const blob = parts.filter(Boolean).join('\n\n').trim();
      if (blob.length > fullText.length) fullText = blob.slice(0, 28000);
    }

    const ok = Boolean(nameFinal || (title || '').trim() || fullText.length >= 80);

    const email_hint = email
      ? ''
      : 'LinkedIn usually hides email on public profiles. This tool only reads what appears on the page (mailto, About text, Contact info). Use InMail, your ATS, or compliant enrichment for addresses LinkedIn does not show.';

    return {
      success: true,
      extracted_ok: ok,
      name: nameFinal,
      title,
      location: profileLocation,
      email,
      email_hint,
      phone,
      website,
      skills: skillsExportLine,
      certifications: certsList.slice(0, 60).join('\n'),
      courses: coursesLines.slice(0, 40).join('\n'),
      honors_awards: honorsLines.slice(0, 35).join('\n'),
      publications: publicationsLines.slice(0, 35).join('\n'),
      patents: patentsLines.slice(0, 25).join('\n'),
      organizations: organizationsLines.slice(0, 25).join('\n'),
      recommendations: recommendationsLines.slice(0, 20).join('\n'),
      test_scores: testScoresLines.slice(0, 15).join('\n'),
      causes: causesLines.slice(0, 15).join('\n'),
      languages: langsList.join(', '),
      /* Structured rows for the pipeline (avoids mis-parsing "EXPERIENCE (from page)" + classifier swaps). */
      experience_items: expItems.map(e => ({
        role: e.role,
        company: e.company,
        dates: e.dates,
        desc: (e.desc || '').slice(0, 2000),
      })),
      education_items: eduItems.map(e => ({
        school: e.school,
        degree: e.degree,
        field: e.field,
        dates: e.dates,
        desc: (e.desc || '').slice(0, 800),
      })),
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
      /* Full list for profile_pipeline (top `Skills:` may be stricter; pipeline also reads SKILLS (from page)). */
      skills_list: skillsList.slice(0, 200),
      fullText,
    };
  };

  /**
   * Scroll profile <main> slowly so LinkedIn mounts Experience/Education/Skills, then run sync extract.
   */
  /**
   * After scrolling to Skills + opening overlays, LinkedIn often unmounts About/Experience/Education.
   * We capture `early` before that pass and merge structured text back in while keeping modal skills.
   */
  function mergeLinkedInExtractPasses(early, late) {
    if (!early || early.success === false) return late;
    if (!late || late.success === false) return early;
    const e = String(early.fullText || '');
    const l = String(late.fullText || '');
    const earlyStructured =
      e.length > 400 && /WORK\s+EXPERIENCE|SUMMARY\s*\/\s*ABOUT|\bEDUCATION\b/i.test(e);
    const lateLostStructure =
      !/WORK\s+EXPERIENCE/i.test(l) ||
      (/SUMMARY\s*\/\s*ABOUT/i.test(e) && !/SUMMARY\s*\/\s*ABOUT/i.test(l));
    if (!earlyStructured || (!lateLostStructure && l.length >= e.length - 200)) return late;

    const out = { ...late };
    const sk =
      String(late.skills || '').trim().length >= String(early.skills || '').trim().length
        ? late.skills
        : late.skills || early.skills;
    out.skills = sk || early.skills;

    let mergedFt = e;
    const earlyHdr = (e.match(/^Skills:\s*.+$/im) || [])[0] || '';
    const lateHdr = (l.match(/^Skills:\s*.+$/im) || [])[0] || '';
    const builtHdr = String(out.skills || '').trim() ? `Skills: ${String(out.skills).trim()}` : '';
    const preferredHdr = [lateHdr, builtHdr, earlyHdr].sort((a, b) => b.length - a.length)[0];
    if (preferredHdr && /^skills:/i.test(preferredHdr)) {
      if (/^skills:\s*.+$/im.test(mergedFt)) mergedFt = mergedFt.replace(/^skills:\s*.+$/im, preferredHdr);
      else {
        const idx = mergedFt.indexOf('\n\n');
        mergedFt =
          idx > 0
            ? `${mergedFt.slice(0, idx)}\n\n${preferredHdr}${mergedFt.slice(idx)}`
            : `${preferredHdr}\n\n${mergedFt}`;
      }
    }
    out.fullText = mergedFt.trim().slice(0, 28000);
    const pick = (a, b) => (String(b || '').trim() ? b : a);
    out.experience_summary = pick(early.experience_summary, late.experience_summary);
    out.education_summary = pick(early.education_summary, late.education_summary);
    out.years_experience = late.years_experience ?? early.years_experience;
    out.highest_degree = pick(early.highest_degree, late.highest_degree);
    out.name = pick(early.name, late.name);
    out.title = pick(early.title, late.title);
    out.location = pick(early.location, late.location);
    out.email = pick(early.email, late.email);
    out.phone = pick(early.phone, late.phone);
    out.website = pick(early.website, late.website);
    out.certifications = pick(early.certifications, late.certifications);
    out.courses = pick(early.courses, late.courses);
    out.honors_awards = pick(early.honors_awards, late.honors_awards);
    out.publications = pick(early.publications, late.publications);
    out.patents = pick(early.patents, late.patents);
    out.organizations = pick(early.organizations, late.organizations);
    out.recommendations = pick(early.recommendations, late.recommendations);
    out.test_scores = pick(early.test_scores, late.test_scores);
    out.causes = pick(early.causes, late.causes);
    out.languages = pick(early.languages, late.languages);
    const pickLonger = (a, b) => {
      const al = Array.isArray(a) ? a.length : 0;
      const bl = Array.isArray(b) ? b.length : 0;
      if (bl > al) return b;
      if (al > 0) return a;
      return b || a;
    };
    out.experience_items = pickLonger(early.experience_items, late.experience_items);
    out.education_items = pickLonger(early.education_items, late.education_items);
    out.skills_list = pickLonger(early.skills_list, late.skills_list);
    out.extracted_ok = Boolean(out.extracted_ok || early.extracted_ok);
    return out;
  }

  globalThis.__rezumeExtractLinkedInAsync = async function rezumeExtractLinkedInAsync(req) {
    const opts = req && typeof req === 'object' ? req : {};
    if (!isLinkedInMemberPageHostname()) return wrongPageExtractResult();
    const rescanOnly = Boolean(opts.rescanOnly);
    const main = rootEl();
    const pageScroll = document.scrollingElement || document.documentElement || document.body;
    let earlyCapture = null;

    globalThis.__rezumePrefetchedEmail = '';
    if (!rescanOnly) {
      try {
        if (main) main.scrollTop = 0;
        window.scrollTo(0, 0);
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 200));
      /* Contact overlay is opt-in — it was breaking or emptying extraction on some accounts. */
      if (opts.tryContactInfo === true) {
        try {
          globalThis.__rezumePrefetchedEmail = await tryOpenContactInfoForEmail();
        } catch { /* ignore */ }
      }
    }
    if (!rescanOnly) {
      const scrollTargets = getProfileScrollRoots();

      for (const root of scrollTargets) {
        const h = Math.max(root.scrollHeight || 0, 1400);
        for (let i = 0; i <= 14; i++) {
          try {
            root.scrollTop = (h * i) / 14;
          } catch { /* ignore */ }
          await new Promise(r => setTimeout(r, 95));
        }
      }
      try {
        const maxY = Math.min(
          Math.max(document.body?.scrollHeight || 0, pageScroll?.scrollHeight || 0, 1200),
          12000,
        );
        for (let y = 0; y <= maxY; y += Math.max(500, Math.floor(maxY / 16))) {
          window.scrollTo(0, y);
          await new Promise(r => setTimeout(r, 70));
        }
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 120));
      PROFILE_SCROLL_KEYS.forEach(sectionKey => {
        try {
          let el = getProfileAnchor(sectionKey);
          const secRoot = rootEl();
          if (!el) {
            if (sectionKey === 'experience') el = sectionExperience(secRoot);
            else if (sectionKey === 'education') el = sectionEducation(secRoot);
            else if (sectionKey === 'skills') el = sectionSkills(secRoot);
          }
          el?.scrollIntoView?.({ block: 'center' });
        } catch { /* ignore */ }
      });
      await new Promise(r => setTimeout(r, 650));
      /* One synchronous prime pass helps when <main> is missing or not the scroll container */
      try {
        primeProfileSections();
      } catch { /* ignore */ }
      await new Promise(r => setTimeout(r, 200));
      try {
        const mTop = rootEl();
        if (mTop) {
          try {
            mTop.scrollTop = 0;
          } catch { /* ignore */ }
          await new Promise(r => setTimeout(r, 200));
        }
        try {
          window.scrollTo(0, 0);
        } catch { /* ignore */ }
        for (const key of ['about', 'experience', 'education']) {
          try {
            let el = getProfileAnchor(key);
            const secRoot = rootEl();
            if (!el && secRoot) {
              if (key === 'experience') el = sectionExperience(secRoot);
              else if (key === 'education') el = sectionEducation(secRoot);
              else if (key === 'about') el = sectionAbout(secRoot);
            }
            el?.scrollIntoView?.({ block: 'center' });
          } catch { /* ignore */ }
          await new Promise(r => setTimeout(r, 320));
        }
        earlyCapture = globalThis.__rezumeExtractLinkedIn({ skipPrime: true });
      } catch {
        /* pre-expand capture is best-effort */
      }
      try {
        await expandProfileListsBeforeExtract();
      } catch {
        /* “Show all” / modal clicks must never abort the whole extract */
      }
      await new Promise(r => setTimeout(r, 550));
    } else if (rescanOnly) {
      await new Promise(r => setTimeout(r, 200));
      try {
        (getProfileAnchor('skills') || (main && sectionSkills(main)))?.scrollIntoView({ block: 'center' });
      } catch { /* ignore */ }
      await clickExpandInSectionCard('skills', 6, 720);
      await new Promise(r => setTimeout(r, 380));
    }
    let out = globalThis.__rezumeExtractLinkedIn({ skipPrime: true });
    try {
      document
        .querySelector(
          '.artdeco-modal__dismiss, button[data-test-modal-close-btn], .artdeco-modal [aria-label*="Dismiss"]',
        )
        ?.click();
    } catch { /* ignore */ }
    if (!rescanOnly && earlyCapture) out = mergeLinkedInExtractPasses(earlyCapture, out);
    return out;
  };
})();
