/**
 * RezumeAI — content-script profile pipeline (runs after extract_core.js).
 * Waits for DOM stability, runs legacy extract, normalizes to structured JSON,
 * applies rule-based cleaning, returns legacy fields + profile_json for the popup.
 */
(function initRezumeProfilePipeline() {
  if (typeof globalThis.__rezumeRunProfilePipeline === 'function') return;

  const PIPELINE_VERSION = '2.2.13';

  /** ── XPath (fallback when CSS misses) ─────────────────────────────── */
  function xpathFirst(expression, contextNode) {
    const ctx = contextNode || document;
    try {
      const r = document.evaluate(expression, ctx, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      return r.singleNodeValue;
    } catch {
      return null;
    }
  }

  /** Try CSS list then a single XPath string; returns first non-empty innerText. */
  function probeHeadline(cssList, xpathFallback) {
    for (const sel of cssList || []) {
      const n = document.querySelector(sel);
      const t = String((n && (n.innerText ?? n.textContent)) ?? '').trim();
      if (t && t.length < 512) return t;
    }
    if (xpathFallback) {
      const n = xpathFirst(xpathFallback, document);
      const t = String((n && (n.innerText ?? n.textContent)) ?? '').trim();
      if (t && t.length < 512) return t;
    }
    return '';
  }

  /** ── DOM stability (LinkedIn virtualizes / mutates profile cards) ─── */
  function pickObserveRoot() {
    return (
      document.querySelector('main[role="main"]') ||
      document.querySelector('main.scaffold-layout__main') ||
      document.querySelector('.scaffold-layout__main') ||
      document.querySelector('main') ||
      document.body
    );
  }

  /**
   * Resolves after `idleMs` with no mutations, or `timeoutMs`, or `maxMutations` bursts (feeds still updating).
   */
  function waitForDomStability(options) {
    const idleMs = Math.max(200, options?.idleMs ?? 720);
    const timeoutMs = Math.max(1500, options?.timeoutMs ?? 14000);
    const maxMutations = Math.max(12, options?.maxMutations ?? 120);
    const root = pickObserveRoot();

    return new Promise(resolve => {
      let timer;
      let mutationCount = 0;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try {
          obs.disconnect();
        } catch {
          /* ignore */
        }
        resolve();
      };

      const obs = new MutationObserver(() => {
        mutationCount += 1;
        if (mutationCount >= maxMutations) return finish();
        clearTimeout(timer);
        timer = setTimeout(finish, idleMs);
      });

      try {
        obs.observe(root, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
          attributeFilter: ['class', 'style', 'hidden', 'aria-hidden'],
        });
      } catch {
        return resolve();
      }

      timer = setTimeout(finish, idleMs);
      setTimeout(finish, timeoutMs);
    });
  }

  function requestIdlePolyfill(ms) {
    return new Promise(r => {
      const cb = () => r();
      if (typeof requestIdleCallback === 'function') requestIdleCallback(cb, { timeout: ms });
      else setTimeout(cb, Math.min(ms, 400));
    });
  }

  function isLinkedInMemberProfileUrl() {
    try {
      const u = new URL(location.href);
      if (!/linkedin\.com$/i.test(u.hostname) && !u.hostname.endsWith('.linkedin.com')) return false;
      return /^\/in\/[^/]+/i.test(u.pathname);
    } catch {
      return false;
    }
  }

  /** ── Parse extension fullText into coarse sections (keyword heuristics) ─ */
  function sliceSection(text, startRe, endRes) {
    const t = String(text || '');
    const m = t.match(startRe);
    if (!m || m.index == null) return '';
    const start = m.index + m[0].length;
    let end = t.length;
    const tail = t.slice(start);
    for (const er of endRes || []) {
      const n = tail.search(er);
      if (n !== -1 && n < end - start) end = start + n;
    }
    return t
      .slice(start, end)
      .replace(/^\s+/, '')
      .trim();
  }

  /**
   * Experience / education cards sometimes concatenate sidebar + footer + language picker.
   * Truncate at first strong anchor and trim comma-separated junk (names, “skills (from page)”, etc.).
   */
  function stripLinkedInNoiseFromBlob(text) {
    let s = String(text || '')
      .replace(/\r\n/g, '\n')
      .replace(/\s+/g, ' ')
      .replace(/â€™|â€˜/g, "'")
      .replace(/â€œ|â€\s*"/g, '"')
      .trim();
    if (!s) return '';
    const cutRes = [
      /\bdon['\u2019\u2018]?\s*t\s+want\s+to\s+see\b/i,
      /\bon['\u2019\u2018]?\s*t\s+want\s+to\s+see\b/i,
      /\bn['\u2019\u2018]\s*t\s+want\s+to\s+see\b/i,
      /\b['\u2019]t\s+want\s+to\s+see\b/i,
      /\bit['\u2019]s\s+annoying\s+or\s+not\s+interesting\b/i,
      /\byour\s+feedback\s+will\s+help\b/i,
      /\bsame\s+ad\s+too\s+often\b/i,
      /\bplease\s+let\s+us\s+know\b/i,
      /\bad\s+choices\b/i,
      /\bselect\s+language\b/i,
      /\bvisit\s+our\s+help\s+center\b/i,
      /\bmanage\s+your\s+account\s+and\s+privacy\b/i,
      /\bgo\s+to\s+your\s+settings\b/i,
      /\brecommendation\s+transparency\b/i,
      /\blearn\s+more\s+about\s+recommended\s+content\b/i,
      /\bcommunity\s+guidelines\b/i,
      /\bmarketing\s+solutions\b/i,
      /\bsales\s+solutions\b/i,
      /\bsmall\s+business\b/i,
      /\bsafety\s+center\b/i,
      /\bquestions\?\b/i,
      /\bclients\s+include\b/i,
      /\b\(arabic\)|\(bangla\)|\(czech\)|\(danish\)|\(deutsch|\(german\)|\(greek\)|\(english\)\s*\(english\)|\(spanish\)|\(hindi\)|\(japanese\)|\(korean\)|\(polish\)|\(portuguese\)|\(russian\)|\(thai\)|\(turkish\)|\(ukrainian\)|\(vietnamese\)|chinese\s*\(simplified\)|chinese\s*\(traditional\)/i,
      /\bskills\s*\(from\s*page\)\b/i,
      /\btalent\s+solutions\b/i,
      /\babout\s*,\s*accessibility\b/i,
      /\bespa[ñn]?ol\s*\(\s*spanish\b/i,
      /\bsuomi\s*\(\s*finnish\b/i,
      /\bfran[cç]ais\s*\(\s*french\b/i,
      /\bmagyar\s*\(\s*hungarian\b/i,
      /\bbahasa\s+indonesia\s*\(\s*indonesian\b/i,
      /\bitaliano\s*\(\s*italian\b/i,
      /\bportugu[eê]s\s*\(\s*portuguese\b/i,
      /\brom[aâ]n[aă]\s*\(\s*romanian\b/i,
      /\bsvenska\s*\(\s*swedish\b/i,
      /\bnederlands\s*\(\s*dutch\b/i,
      /\bnorsk\s*\(\s*norwegian\b/i,
      /\btagalog\s*\(\s*tagalog\b/i,
      /\(\s*persian\s*\)/i,
      /\(\s*hebrew\s*\)/i,
      /\(\s*marathi\s*\)/i,
      /\(\s*malay\s*\)/i,
      /\(\s*punjabi\s*\)/i,
      /\(\s*telugu\s*\)/i,
    ];
    let cut = s.length;
    for (const re of cutRes) {
      const m = re.exec(s);
      if (m && m.index >= 24 && m.index < cut) cut = m.index;
    }
    s = s.slice(0, cut).trim();
    s = s.replace(/\s*,\s*(about|accessibility|careers|mobile)\s*,/gi, ', ').replace(/^[,;\s·]+|[,;\s·]+$/g, '');
    if (s.length > 320 && (s.match(/,/g) || []).length >= 6) {
      const parts = s.split(',').map(p => p.trim()).filter(Boolean);
      const kept = [];
      for (const p of parts) {
        const low = p.toLowerCase();
        if (/^(about|accessibility|careers|mobile|advertising)$/.test(low)) continue;
        if (
          /talent solutions|ad choices|select language|visit our help|community guidelines|marketing solutions|sales solutions|safety center|recommendation transparency/.test(
            low,
          )
        )
          break;
        if (/^\(?[a-zà-ÿ%]{2,35}\)?\s*\(\s*arabic\s*\)/i.test(p)) continue;
        if (/^skills\s*\(from page\)$/i.test(low)) continue;
        if (/^don['\u2019]?\s*t want to see/i.test(p)) break;
        kept.push(p);
      }
      if (kept.length) s = kept.join(', ');
    }
    return s.replace(/\s*,\s*,+/g, ', ').replace(/^[,;\s·]+|[,;\s·]+$/g, '').trim();
  }

  function chunkLooksLikeLinkedInFooterOrAdBlob(s) {
    const t = String(s || '').toLowerCase();
    if (t.length < 120) return false;
    return (
      /\bselect\s+language\b/.test(t) ||
      /\bad\s+choices\b/.test(t) ||
      /\bdon['\u2019]?\s*t\s+want\s+to\s+see\b/.test(t) ||
      /\bvisit\s+our\s+help\s+center\b/.test(t) ||
      (/\bclients\s+include\b/.test(t) && /\bportland\b|\bgfuel\b|\bcro\b/i.test(t))
    );
  }

  function experienceItemsFromLegacy(legacy) {
    const items = legacy?.experience_items;
    if (!Array.isArray(items) || !items.length) return [];
    const out = [];
    for (const e of items) {
      const title = String(e?.role ?? e?.title ?? '').replace(/\s+/g, ' ').trim();
      if (!title) continue;
      const org = String(e?.company ?? e?.organization ?? '').replace(/\s+/g, ' ').trim();
      const dates = String(e?.dates ?? e?.dates_or_location ?? '').replace(/\s+/g, ' ').trim();
      const desc = String(e?.desc ?? '')
        .replace(/\s+/g, ' ')
        .trim();
      const raw = [title, org && `@ ${org}`, dates && `| ${dates}`].filter(Boolean).join(' ').trim();
      const blob = stripLinkedInNoiseFromBlob((raw + (desc ? ` — ${desc.slice(0, 500)}` : '')).trim()).slice(0, 700);
      if (!blob || blob.length < 4) continue;
      out.push({
        title: title.slice(0, 220),
        organization: org.slice(0, 300),
        dates_or_location: dates.slice(0, 160),
        raw: blob,
      });
    }
    return out.slice(0, 45);
  }

  function educationItemsFromLegacy(legacy) {
    const items = legacy?.education_items;
    if (!Array.isArray(items) || !items.length) return [];
    return items
      .map(e => {
        const school = String(e?.school ?? '').replace(/\s+/g, ' ').trim();
        const deg = [e?.degree, e?.field].map(x => String(x ?? '').trim()).filter(Boolean).join(', ');
        const d = String(e?.dates ?? '').replace(/\s+/g, ' ').trim();
        if (!school && !deg && !d) return null;
        const raw = stripLinkedInNoiseFromBlob([school, deg, d].filter(Boolean).join(' | ').trim()).slice(0, 520);
        if (!raw || raw.length < 3) return null;
        return { raw };
      })
      .filter(Boolean)
      .slice(0, 25);
  }

  function parseExperienceLines(block) {
    const lines = String(block || '')
      .split('\n')
      .map(l => String(l ?? '').trim())
      .filter(Boolean);
    const items = [];
    for (const line of lines) {
      if (/^(WORK EXPERIENCE|EDUCATION|SKILLS|CERTIFICATION|LICENSES|--- PROFILE)/i.test(line)) break;
      if (line.startsWith('  ') && line.length > 4) {
        const raw = line.replace(/^\s+/, '');
        const cleaned = stripLinkedInNoiseFromBlob(raw).slice(0, 600);
        if (cleaned.length < 4) continue;
        const m = cleaned.match(/^(.+?)(?:\s+@\s+(.+?))?(?:\s*\|\s*(.+))?$/);
        if (m) {
          items.push({
            title: String(m[1] ?? '').trim(),
            organization: String(m[2] ?? '').trim(),
            dates_or_location: String(m[3] ?? '').trim(),
            raw: cleaned,
          });
        } else items.push({ title: cleaned, organization: '', dates_or_location: '', raw: cleaned });
      }
    }
    return items.slice(0, 40);
  }

  function parseEducationLines(block) {
    const lines = String(block || '')
      .split('\n')
      .map(l => String(l ?? '').trim())
      .filter(Boolean);
    const items = [];
    for (const line of lines) {
      if (/^(WORK\s+EXPERIENCE|SKILLS|CERTIFICATION|LICENSES|--- PROFILE)/i.test(line)) break;
      if (/^education\s*\(from page\)$/i.test(line)) continue;
      if (/^education$/i.test(line) && line.length < 16) continue;
      const raw = line.replace(/^\s+/, '').trim();
      if (!raw || raw.length < 4) continue;
      const cleaned = stripLinkedInNoiseFromBlob(raw).slice(0, 520);
      if (cleaned.length >= 4) items.push({ raw: cleaned });
    }
    return items.slice(0, 24);
  }

  /**
   * Text chunks that the keyword classifier put in "experience" but are really comma/endorsement skill
   * lists (should move to skills, not show in Experience).
   */
  function chunkLooksLikeSkillListOrEndorsementBlob(s) {
    const t = String(s || '');
    if (t.length < 90) return false;
    const com = (t.match(/,/g) || []).length;
    if (com >= 4 && t.length > 200) {
      const hasEmploymentCues = /\b(20\d{2}|present|full[-\s]?time|part[-\s]?time|intern|@\s*[\w.]+| at [\w&]|january|february|march|april|may|june|july|august|september|october|november|december)\b/i.test(
        t,
      );
      const hasDateRange = /\b20\d{2}\s*[-–]\s*(20\d{2}|present)\b/i.test(t);
      const designUiHits = (
        t.match(
          /\b(figma|adobe\s+(photoshop|illustrator|xd)|sketch|invision|interface\s+design|user\s+experience|web\s+design|mobile\s+interface|ued)\b/gi,
        ) || []
      ).length;
      if (!hasEmploymentCues) return true;
      if (com >= 5 && designUiHits >= 4 && t.length > 180 && !hasDateRange) return true;
    }
    if (/\b\d+\s+endorsements?\b/i.test(t) && !/\b20\d{2}\s*[-–]\s*(20\d{2}|present)\b/i.test(t) && t.length < 2000) return true;
    return false;
  }

  /** LinkedIn soft / generic “keywords” (not concrete tools or domains). */
  function isSoftSkillKeywordNoiseToken(text) {
    const t = String(text || '').trim();
    if (!t) return true;
    const low = t.toLowerCase();
    const words = t.split(/\s+/).filter(Boolean);
    const singles = new Set([
      'communication',
      'communications',
      'teamwork',
      'leadership',
      'collaboration',
      'adaptability',
      'flexibility',
      'creativity',
      'innovation',
      'empathy',
      'accountability',
      'initiative',
      'mentoring',
      'coaching',
      'negotiation',
      'negotiations',
      'multitasking',
      'presentation',
      'presentations',
      'networking',
      'storytelling',
      'brainstorming',
      'facilitation',
      'resilience',
      'positivity',
      'enthusiasm',
      'dedication',
      'motivation',
      'reliability',
      'professionalism',
      'patience',
      'resourcefulness',
      'curiosity',
      'listening',
      'writing',
      'reading',
      'scheduling',
      'budgeting',
      'forecasting',
      'recruiting',
      'hiring',
      'training',
      'onboarding',
      'consulting',
      'advisory',
      'organization',
      'moderation',
      'inclusion',
      'equity',
      'diversity',
      'culture',
      'ethics',
      'integrity',
      'honesty',
    ]);
    if (words.length === 1 && singles.has(low)) return true;
    if (words.length >= 2) {
      const phrases = new Set([
        'problem solving',
        'problem-solving',
        'time management',
        'critical thinking',
        'customer service',
        'public speaking',
        'conflict resolution',
        'stakeholder management',
        'strategic planning',
        'business development',
        'team building',
        'organizational skills',
        'presentation skills',
        'listening skills',
        'writing skills',
        'analytical skills',
        'interpersonal skills',
        'leadership skills',
        'communication skills',
        'management skills',
        'team management',
        'people management',
        'emotional intelligence',
        'cross functional collaboration',
        'cross-functional collaboration',
        'attention to detail',
        'detail orientation',
        'positive attitude',
        'self motivation',
        'self-motivation',
        'work ethic',
        'client relations',
        'relationship building',
        'decision making',
        'decision-making',
        'strategic thinking',
        'creative thinking',
        'cultural awareness',
        'open mindedness',
        'open-mindedness',
      ]);
      if (phrases.has(words.map(w => w.toLowerCase()).join(' '))) return true;
    }
    return false;
  }

  /** When merging classifier "skills" fragments into out.skills — drop experience/job blobs. */
  function classifierSkillTokenOk(s) {
    const t = String(s || '')
      .replace(/\s+/g, ' ')
      .trim();
    if (t.length < 2 || t.length > 92) return false;
    if (isSoftSkillKeywordNoiseToken(t)) return false;
    if (isSkillSplitNoise(t)) return false;
    const words = t.split(/\s+/);
    if (words.length > 8) return false;
    if (/\b(i\s+am|i\s+have|we\s+are|our\s+team|years?\s+of|managed\s+|\b20\d{2}\b.*\b20\d{2})/i.test(t)) return false;
    if (/\b(full[-\s]?time|part[-\s]?time|intern|contract|freelance|present)\b/i.test(t) && t.length > 32) return false;
    if (/\s+at\s+[\w.].{3,80}$/i.test(t)) return false; /* "Engineer at Acme" */
    if (/\b(designer|developer|engineer|manager|researcher|lead|intern|head|coordinator|analyst|architect|consultant|director|officer|specialist|executive|strategist)\s*$/i.test(t)) return false;
    if (/\b(dev|devops)\s*$/i.test(t) && words.length <= 3) return false;
    return true;
  }

  function skillsTextBodyToTokens(body) {
    if (!body || String(body).length < 2) return [];
    const t = String(stripLinkedInNoiseFromBlob(String(body).slice(0, 14000)))
      .replace(/\r\n/g, '\n')
      .replace(/\s*,\s*/g, ',');
    const parts = t.split(/[,\n·•|;]+/g);
    const out = [];
    for (const part of parts) {
      const s = part.replace(/\s+/g, ' ').trim();
      if (s.length < 2) continue;
      if (s.length > 100) continue;
      if (isSkillSplitNoise(s) || isSoftSkillKeywordNoiseToken(s)) continue;
      if (/^skills?$/i.test(s)) continue;
      out.push(s);
    }
    return out.slice(0, 180);
  }

  function isSkillSplitNoise(x) {
    const t = String(x || '')
      .replace(/â€™|â€˜/g, "'")
      .replace(/\s+/g, ' ')
      .trim();
    if (!t || t.length > 100) return true;
    const low = t.toLowerCase();
    const footerExact = new Set([
      'about',
      'accessibility',
      'talent solutions',
      'community guidelines',
      'careers',
      'marketing solutions',
      'ad choices',
      'advertising',
      'sales solutions',
      'mobile',
      'small business',
      'safety center',
      'questions?',
      'visit our help center',
      'manage your account and privacy',
      'go to your settings',
      'recommendation transparency',
      'learn more about recommended content',
      'select language',
      'skills (from page)',
      'other',
    ]);
    if (footerExact.has(low)) return true;
    if (
      /\(arabic\)|\(bangla\)|\(czech\)|\(danish\)|\(german\)|\(greek\)|\(hindi\)|\(japanese\)|\(korean\)|\(polish\)|\(russian\)|\(thai\)|\(turkish\)|\(ukrainian\)|\(vietnamese\)|chinese\s*\(simplified\)|chinese\s*\(traditional\)|english\s*\(\s*english/i.test(
        t,
      )
    )
      return true;
    if (/\bclients\s+include\b/i.test(t)) return true;
    if (/\d+\s*years?\s+.*\b(turning|clicks|customers|cro)\b/i.test(t)) return true;
    if (/\bturning\s+clicks\s+into\s+customers\b/i.test(low) && /\bcro\b/.test(low)) return true;
    if (/\bportland\s+leather\b|\bgfuel\b|\bboom!\s*by\s+cindy\b/i.test(t)) return true;
    if (
      low === 'web design' ||
      low === 'mobile interface design' ||
      low === 'user interface design' ||
      low === 'user experience design' ||
      /^user experience design\s*\(ued\)?$/i.test(low)
    )
      return true;
    if (
      /^don'?t\s+want\s+to\s+see|on'?t\s+want\s+to\s+see|n['\u2019]?\s*t\s+want\s+to\s+see|['\u2019]t\s+want\s+to\s+see|it'?s\s+annoying|your\s+feedback\s+will\s+help|same\s+ad\s+too\s+often|please\s+let\s+us\s+know/i.test(
        low,
      )
    )
      return true;
    if (
      /\bespa[ñn]?ol\s*\(\s*spanish\b|\bsuomi\s*\(\s*finnish\b|\bfran[cç]ais\s*\(\s*french\b|\bmagyar\s*\(\s*hungarian\b|\bbahasa\s+indonesia\s*\(\s*indonesian\b|\bitaliano\s*\(\s*italian\b|\bportugu[eê]s\s*\(\s*portuguese\b|\brom[aâ]n[aă]\s*\(\s*romanian\b|\bsvenska\s*\(\s*swedish\b|\bnederlands\s*\(\s*dutch\b|\bnorsk\s*\(\s*norwegian\b|\btagalog\s*\(\s*tagalog\b|\(\s*persian\s*\)|\(\s*hebrew\s*\)|\(\s*marathi\s*\)|\(\s*malay\s*\)|\(\s*punjabi\s*\)|\(\s*telugu\s*\)/i.test(
        t,
      )
    )
      return true;
    if (/\b\d+\s*\+?\s*yrs?\b/i.test(low) && /\b(design|designing|dashboard|websites|conversion|high[-\s]?conversion|cro|figma)\b/i.test(low))
      return true;
    if (/\bhappyv\b|\band\s+many\s+more\b|^many\s+more\b/i.test(low)) return true;
    if (
      ['oliver kenyon', 'haseeb ali', 'saad farooq', 'sibtain shah', 'ruhma tariq'].includes(
        low.replace(/[.!?…]+$/g, '').trim(),
      )
    )
      return true;
    if (/^skills?$/i.test(t)) return true;
    if (/^(all|submit|endorse)$/i.test(t)) return true;
    if (/^industry\s+knowledge$/i.test(t)) return true;
    if (/^tools\s+(&|and)\s+technologies$/i.test(t)) return true;
    if (/^other\s+skills$/i.test(t)) return true;
    if (/^interpersonal\s+skills$/i.test(t)) return true;
    if (/^ad\s+options?$/i.test(t)) return true;
    if (
      /why\s+am\s+i\s+seeing|manage\s+your\s+ad\s+preferences|report\s+this\s+ad|hide\s+or\s+report|don'?t\s+want\s+to\s+see|more\s+profiles\s+for\s+you|sponsored|promoted\s+post/i.test(
        t,
      )
    )
      return true;
    if (
      /\b(people you may know|mutual connections?|suggested for you|similar profiles?|profiles similar|also viewed|who to follow|because you follow|because you view)\b/i.test(
        t,
      )
    )
      return true;
    if (/·\s*\d+(st|nd|rd|th)\b/i.test(t) && t.length < 72) return true;
    if (/^.+\s+@\s+[A-Za-z0-9][\w.&\s-]{2,60}$/i.test(t) && !/\b(node|react|next|vue|nest)\.(js|ts)\b/i.test(t)) return true;
    if (/^\d+\s+endorsements?$/i.test(t)) return true;
    if (/^(follow|message|connect)$/i.test(t)) return true;
    if (/\s+at\s+/i.test(t)) return true;
    {
      const open = t.lastIndexOf('(');
      if (open >= 0 && t.indexOf(')', open) < 0) {
        const inner = t.slice(open + 1).trim().toLowerCase();
        if (
          /^(software|tool|application|app|ued)\w{0,8}$/.test(inner) ||
          /^softwar\w{0,6}$/.test(inner) ||
          /^(arabic|bangla|czech|danish|german|greek|spanish|french|hindi|japanese|korean|polish|portuguese|russian|thai|turkish|ukrainian|vietnamese|hebrew|hungarian|indonesian|italian|norwegian|dutch|swedish|finnish|romanian|tagalog|telugu|marathi|malay|punjabi|persian|filipino|simplified|traditional)\w{0,10}$/.test(
            inner,
          )
        )
          return true;
      }
    }
    return false;
  }

  function splitSkills(s) {
    return String(s || '')
      .split(/[,|;\n]+/)
      .map(x => String(x ?? '').replace(/\s+/g, ' ').trim())
      .filter(
        x => x.length > 1 && x.length < 120 && !isSkillSplitNoise(x) && !isSoftSkillKeywordNoiseToken(x),
      )
      .slice(0, 200);
  }

  /** ── Whole-page visible text (LinkedIn main column) ───────────────── */
  function scrapeWholePageMainText(maxChars) {
    if (!isLinkedInMemberProfileUrl()) return '';
    const max = Math.min(Math.max(8000, maxChars || 100000), 150000);
    const root =
      document.querySelector('main[role="main"]') ||
      document.querySelector('main.scaffold-layout__main') ||
      document.querySelector('.scaffold-layout__main') ||
      document.querySelector('main') ||
      document.body;
    if (!root) return '';
    const parts = [];
    const seen = new Set();
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let node;
    while ((node = walker.nextNode())) {
      try {
        const el = node.parentElement;
        if (!el) continue;
        const st = window.getComputedStyle(el);
        if (st.visibility === 'hidden' || st.display === 'none' || parseFloat(st.opacity || '1') < 0.05) continue;
        const tag = (el.tagName || '').toUpperCase();
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
        let t = String(node.textContent || '')
          .replace(/\s+/g, ' ')
          .trim();
        if (t.length < 3 || t.length > 900) continue;
        if (/^[\d\s·•|]+$/.test(t)) continue;
        const k = t.slice(0, 200);
        if (seen.has(k)) continue;
        seen.add(k);
        parts.push(t);
      } catch {
        /* ignore */
      }
    }
    return parts.join('\n').slice(0, max);
  }

  /** Score a text chunk for each recruiter-relevant “role” bucket (local, no network). */
  function scoreChunkRoles(chunk) {
    const c = String(chunk || '').trim();
    if (c.length < 12) return { best: 'other', scores: {} };
    const low = c.toLowerCase();
    const scores = {
      header: 0,
      about: 0,
      experience: 0,
      education: 0,
      skills: 0,
      certifications: 0,
      other: 0.01,
    };
    if (c.length <= 100 && !/\n/.test(c)) scores.header += 2.5;
    /* Avoid lone “about” — LinkedIn nav / chrome repeats it in full-page scrapes and steals the bucket. */
    if (/\b(summary|about me|overview|mission|passionate|i love to|i enjoy|professional with)\b/i.test(low))
      scores.about += 4;
    if (
      /^skills?\s*$/im.test(c) ||
      /\b(technical skills|core competencies|expertise in|industry knowledge|tools\s*&\s*technologies)\b/i.test(low)
    )
      scores.skills += 3.5;
    if (/\b\d+\s+endorsements?\b/i.test(low)) scores.skills += 2.5;
    if (
      /\b(university|college|bachelor|master|ph\.?d|doctorate|diploma|degree|gpa|graduated|thesis|academic)\b/i.test(
        low,
      )
    )
      scores.education += 4;
    if (
      /\b(january|february|march|april|may|june|july|august|september|october|november|december)\b.*\b20\d{2}\b/i.test(
        low,
      ) ||
      /\b(20\d{2}\s*[–-]\s*(20\d{2}|present))\b/i.test(low) ||
      /\b(full[\s-]?time|part[\s-]?time|contract|internship|employment)\b/i.test(low)
    )
      scores.experience += 3.5;
    if (/\b(@\s*\w+| at \w+ inc| llc| ltd|corp\.|company)\b/i.test(low)) scores.experience += 2;
    if (
      /\b(certified|certificate|license|credential|pmp|aws certified|scrum master|clearance)\b/i.test(low)
    )
      scores.certifications += 4;
    if (
      /\b(python|java|react|angular|vue|node|sql|aws|gcp|azure|kubernetes|docker|typescript|javascript|machine learning|data science)\b/i.test(
        low,
      )
    )
      scores.skills += 2;
    if (/\b(years?\s+of\s+experience|yoe\b|managed team|led a team|built|shipped|delivered)\b/i.test(low))
      scores.experience += 1.5;
    if (/\b20\d{2}\s*[–-]\s*(20\d{2}|present)\b/i.test(low) && /\b(full|part)[\s-]?time|contract|internship|freelance|@| at [A-Za-z0-9]/i.test(low))
      scores.experience += 3;
    if (/\b(designer|developer|engineer|lead|manager|consultant|analyst)\s+at\s+\w/i.test(low)) scores.experience += 2.5;
    if (/\b(honors|awards|publications|volunteer)\b/i.test(low)) scores.about += 1;
    let best = 'other';
    let top = 0;
    for (const k of Object.keys(scores)) {
      if (scores[k] > top) {
        top = scores[k];
        best = k;
      }
    }
    /* “about” often wins on a stray keyword in a flat scrape; prefer stronger structural signals. */
    if (best === 'about') {
      if (scores.experience > scores.about + 0.5) best = 'experience';
      else if (scores.skills > scores.about + 0.5) best = 'skills';
      else if (scores.education > scores.about + 0.5) best = 'education';
      else if (scores.certifications > scores.about + 0.5) best = 'certifications';
    }
    if (top < 1.2) best = 'other';
    return { best, scores };
  }

  /**
   * `scrapeWholePageMainText` joins text nodes with single newlines, so “paragraph” split often yields
   * one giant chunk. Split again on LinkedIn section headers / our structured markers so each bucket
   * can be scored separately.
   */
  function splitFlatProfileBlobIntoChunks(raw) {
    const t = String(raw || '').replace(/\r\n/g, '\n').trim();
    if (!t) return [];
    const STRUCT =
      /\n(?=(?:---\s*PROFILE|WORK\s+EXPERIENCE|EXPERIENCE\s*\(from page\)|SUMMARY\s*\/\s*ABOUT|EDUCATION\b|EDUCATION\s*\(from page\)|SKILLS\b|SKILLS\s*\(from page\)|LICENSES|CERTIFICATIONS)\b)/i;
    let pieces = t.split(STRUCT).map(s => s.trim()).filter(s => s.length > 15);
    const LINE_HEADER =
      /^(?:skills?|all\b|industry knowledge|tools\s*&\s*technologies|work\s+experience|experience|education|licenses|certifications?|projects?|languages?|volunteer|honors|recommendations|activity|services)\s*$/i;
    const refine = arr => {
      const out = [];
      for (const chunk of arr) {
        if (chunk.length < 3200) {
          out.push(chunk);
          continue;
        }
        const lines = chunk.split('\n');
        let cur = [];
        const flush = () => {
          const j = cur.join('\n').trim();
          if (j.length > 15) out.push(j);
          cur = [];
        };
        for (const line of lines) {
          if (LINE_HEADER.test(line.trim()) && cur.length) flush();
          cur.push(line);
        }
        flush();
      }
      return out.length ? out : arr;
    };
    pieces = refine(pieces);
    const out = [];
    for (const p of pieces) {
      if (p.length < 8000) out.push(p);
      else out.push(...p.split(/\n{3,}/).map(s => s.trim()).filter(s => s.length > 60));
    }
    return out.filter(s => s.length > 15).slice(0, 500);
  }

  /** Split big text into paragraphs / blocks, classify each, aggregate by role. */
  function classifyTextIntoRoles(bigText) {
    const raw = String(bigText || '').replace(/\r\n/g, '\n');
    let chunks = raw
      .split(/\n{2,}|\n(?=\s{0,3}[A-Z][a-z]+ \d{4})/)
      .map(s => String(s ?? '').trim())
      .filter(s => s.length > 15);
    if (chunks.length <= 2 && raw.length > 3200) chunks = splitFlatProfileBlobIntoChunks(raw);
    if (!chunks.length && raw.trim().length > 15) chunks = [raw.trim()];
    const roles = {
      header: [],
      about: [],
      experience: [],
      education: [],
      skills: [],
      certifications: [],
      other: [],
    };
    for (const ch of chunks.slice(0, 400)) {
      const { best } = scoreChunkRoles(ch);
      const slice = ch.slice(0, 8000);
      if (roles[best]) roles[best].push(slice);
      else roles.other.push(slice);
    }
    return roles;
  }

  /** Merge page-wide classified buckets into structured profile (fills gaps). */
  function mergeRoleSections(structured, roles) {
    const out = structured && typeof structured === 'object' ? JSON.parse(JSON.stringify(structured)) : {};
    const joinBlocks = arr => (arr || []).filter(Boolean).join('\n\n').trim();
    const meta = out._meta && typeof out._meta === 'object' ? out._meta : {};
    const experienceFromDom = Boolean(meta.experienceFromItems);
    const skSeen = new Set((out.skills || []).map(s => String(s ?? '').toLowerCase()));
    const addSkill = raw => {
      const s = String(raw ?? '')
        .trim();
      if (s.length < 2) return;
      if (!classifierSkillTokenOk(s)) return;
      const k = s.toLowerCase();
      if (skSeen.has(k)) return;
      skSeen.add(k);
      out.skills = out.skills || [];
      out.skills.push(s);
    };

    if (!String(out.summary || '').trim() && roles.about.length)
      out.summary = joinBlocks(roles.about).slice(0, 12000);
    else if (roles.about.length && String(out.summary || '').length < 120) {
      out.summary = [out.summary, joinBlocks(roles.about)].filter(Boolean).join('\n\n').slice(0, 12000);
    }

    if (!experienceFromDom) {
      if ((!out.experience || !out.experience.length) && roles.experience.length) {
        out.experience = roles.experience
          .filter(r => !chunkLooksLikeLinkedInFooterOrAdBlob(r))
          .map(raw => {
            const r = String(raw ?? '');
            const cleaned = stripLinkedInNoiseFromBlob(r).slice(0, 700);
            if (cleaned.length < 8) return null;
            return {
              title: r.split('\n')[0].slice(0, 220),
              organization: '',
              dates_or_location: '',
              raw: cleaned,
            };
          })
          .filter(Boolean);
      } else if (roles.experience.length && (out.experience || []).length < 2) {
        const extra = roles.experience
          .filter(r => !chunkLooksLikeLinkedInFooterOrAdBlob(r))
          .filter(r =>
            !(out.experience || []).some(x => (x.raw || '').includes(String(r ?? '').slice(0, 40))),
          )
          .map(raw => {
            const r = String(raw ?? '');
            const cleaned = stripLinkedInNoiseFromBlob(r).slice(0, 700);
            if (cleaned.length < 8) return null;
            return {
              title: r.split('\n')[0].slice(0, 220),
              organization: '',
              dates_or_location: '',
              raw: cleaned,
            };
          })
          .filter(Boolean);
        out.experience = [...(out.experience || []), ...extra].slice(0, 45);
      }
    }

    if ((!out.education || !out.education.length) && roles.education.length) {
      out.education = roles.education
        .map(raw => {
          const cleaned = stripLinkedInNoiseFromBlob(String(raw ?? '')).slice(0, 520);
          return cleaned.length >= 4 ? { raw: cleaned } : null;
        })
        .filter(Boolean);
    }

    for (const block of roles.skills) {
      for (const s of splitSkills(block)) addSkill(s);
    }
    /* Re-route comma-heavy "experience" chunks that are really skills into out.skills */
    for (const c of roles.experience || []) {
      if (!chunkLooksLikeSkillListOrEndorsementBlob(c)) continue;
      for (const t of skillsTextBodyToTokens(c)) addSkill(t);
    }
    if (out.skills) out.skills = out.skills.slice(0, 160);

    if (roles.certifications.length) {
      let cur = out.certifications;
      if (typeof cur === 'string')
        cur = cur.split(/\n/).map(s => s.trim()).filter(Boolean);
      else cur = [].concat(cur || []).map(String).filter(Boolean);
      for (const line of roles.certifications) {
        const bits = String(line ?? '')
          .split(/\n/)
          .map(s => String(s ?? '').trim())
          .filter(s => s.length > 3);
        for (const b of bits) {
          if (!cur.some(c => c.toLowerCase() === b.toLowerCase())) cur.push(b);
        }
      }
      out.certifications = cur.slice(0, 80);
    }

    const expSectionLines = (out.experience || [])
      .map(
        x =>
          stripLinkedInNoiseFromBlob(
            String(
              (x.raw && String(x.raw).length > 8
                ? x.raw
                : [x.title, x.organization, x.dates_or_location]
                    .map(t => (t == null ? '' : String(t).trim()))
                    .filter(Boolean)
                    .join(' | ')) || '',
            )
              .replace(/\s+/g, ' ')
              .trim(),
          ),
      )
      .filter(s => s.length > 4)
      .slice(0, 50);
    const eduSectionLines = (out.education || [])
      .map(e => stripLinkedInNoiseFromBlob(String(e.raw || '').trim()))
      .filter(s => s.length > 4)
      .slice(0, 25);
    const expForDisplay =
      experienceFromDom || expSectionLines.length
        ? expSectionLines
        : (roles.experience || [])
            .filter(c => !chunkLooksLikeSkillListOrEndorsementBlob(c) && !chunkLooksLikeLinkedInFooterOrAdBlob(c))
            .map(c => stripLinkedInNoiseFromBlob(String(c)))
            .filter(s => s.length > 8)
            .slice(0, 50);
    out.role_sections = {
      about: (roles.about || []).slice(0, 35),
      experience: expForDisplay,
      education: (
        out.education && out.education.length
          ? eduSectionLines
          : (roles.education || []).map(e => stripLinkedInNoiseFromBlob(String(e))).filter(s => s.length > 4)
      ).slice(0, 25),
      skills: (out.skills && out.skills.length
        ? (out.skills || []).map(s => String(s).trim()).filter(s => s.length)
        : (roles.skills || [])).slice(0, 40),
      certifications: (roles.certifications || []).slice(0, 25),
      header: (roles.header || []).slice(0, 15),
      other: (roles.other || []).slice(0, 15),
    };
    return out;
  }

  /** Map legacy extractor output → structured job-schema–oriented JSON */
  function legacyExtractToStructured(legacy) {
    const fullText = String(legacy?.fullText || '');
    const about =
      sliceSection(fullText, /SUMMARY\s*\/\s*ABOUT\s*\n/i, [
        /\n---\s*PROFILE\s+SECTIONS/i,
        /\nWORK EXPERIENCE/i,
        /\nEDUCATION\b/i,
        /\nSKILLS\b/i,
      ]) || '';

    const workBlock =
      sliceSection(fullText, /WORK EXPERIENCE\s*\n/i, [/\nEDUCATION\b/i, /\nSKILLS\b/i, /\n---\s*PROFILE/i]) ||
      sliceSection(fullText, /EXPERIENCE\s*\(from page\)\s*\n/i, [
        /\nEDUCATION\s*\(from page\)/i,
        /\nSKILLS\s*\(from page\)/i,
        /\n---/i,
      ]);

    const eduBlock =
      sliceSection(fullText, /\bEDUCATION\s*\n/i, [/\nSKILLS\b/i, /\nWORK EXPERIENCE/i, /\n---\s*PROFILE/i]) ||
      sliceSection(fullText, /EDUCATION\s*\(from page\)\s*\n/i, [/\nSKILLS\s*\(from page\)/i, /\n---/i]);

    const certBlob = [legacy?.certifications, legacy?.honors_awards, legacy?.publications]
      .filter(Boolean)
      .join('\n');

    const skillsFromField = splitSkills(stripLinkedInNoiseFromBlob(String(legacy?.skills || '')));
    const skillsLine = (fullText.match(/^Skills:\s*(.+)$/im) || [])[1] || '';
    const skillsFromText = splitSkills(stripLinkedInNoiseFromBlob(skillsLine));
    const seenSk = new Set();
    const skills = [];
    const pushSk = raw => {
      const t = stripLinkedInNoiseFromBlob(String(raw ?? '').trim());
      if (!t || t.length > 120 || isSkillSplitNoise(t) || isSoftSkillKeywordNoiseToken(t)) return;
      const k = t.toLowerCase();
      if (seenSk.has(k)) return;
      seenSk.add(k);
      skills.push(t);
    };
    for (const s of [...skillsFromField, ...skillsFromText]) pushSk(s);
    if (Array.isArray(legacy?.skills_list) && legacy.skills_list.length) {
      for (const s of legacy.skills_list) pushSk(s);
    }
    for (const t of skillsTextBodyToTokens(
      sliceSection(fullText, /SKILLS\s*\(from page\)\s*\n/i, [
        /\nLICENSES\s*&\s*CERTIFICATIONS\s*\(from page\)/i,
        /\nCERTIFICATIONS\s*\(from page\)/i,
        /\nPROJECTS\s*\(from page\)/i,
        /\nLANGUAGES\s*\(from page\)/i,
        /\nVOLUNTEER\s+EXPERIENCE\s*\(from page\)/i,
        /\nCOURSES\s*\(from page\)/i,
        /\nHONORS\s*&\s*AWARDS\s*\(from page\)/i,
        /\nPUBLICATIONS\s*\(from page\)/i,
        /\nPATENTS\s*\(from page\)/i,
        /\nORGANIZATIONS\s*\(from page\)/i,
        /\nRECOMMENDATIONS\s*\(from page\)/i,
        /\nTEST\s+SCORES\s*\(from page\)/i,
        /\nCAUSES\s*\(from page\)/i,
        /\n---/,
      ]),
    ))
      pushSk(t);
    /* Fallback block from appendStructuredFallback: "SKILLS" + comma list (not the header line) */
    for (const t of skillsTextBodyToTokens(
      sliceSection(fullText, /(?:^|\n)SKILLS\s*\n/i, [/\nLICENSES/i, /\nWORK EXPERIENCE/i, /\nEDUCATION/i, /\n---/i]),
    ))
      pushSk(t);

    const fromItems = experienceItemsFromLegacy(legacy);
    const fromEduItems = educationItemsFromLegacy(legacy);
    const xp = fromItems.length ? fromItems : parseExperienceLines(workBlock);
    const edu = fromEduItems.length ? fromEduItems : parseEducationLines(eduBlock);

    const headlineFallback = probeHeadline(
      ['.text-body-medium.break-words', 'main .text-body-medium', '.top-card-layout__headline'],
      '//main//h2[contains(@class,"text-body-medium") or contains(@class,"break-words")][1]',
    );

    return {
      schema_version: 1,
      source: 'linkedin',
      profile_url: legacy?.profile_url || location.href.split('?')[0],
      captured_at: new Date().toISOString(),
      _meta: {
        experienceFromItems: fromItems.length > 0,
      },
      identity: {
        full_name: String(legacy?.name || '').trim(),
        headline: String(legacy?.title || headlineFallback || '').trim(),
        location: String(legacy?.location || '').trim(),
        email: String(legacy?.email || '').trim() || null,
        phone: String(legacy?.phone || '').trim() || null,
        website: String(legacy?.website || '').trim() || null,
      },
      summary: about.slice(0, 12000),
      skills: skills.slice(0, 160),
      experience: xp,
      education: edu,
      certifications: String(certBlob || '')
        .split(/\n+/)
        .map(s => String(s ?? '').trim())
        .filter(s => s.length > 2)
        .slice(0, 80),
      metrics: {
        years_experience: legacy?.years_experience ?? null,
        highest_degree: legacy?.highest_degree ?? null,
      },
      experience_summary: String(legacy?.experience_summary || '').trim(),
      education_summary: String(legacy?.education_summary || '').trim(),
      languages: String(legacy?.languages || '')
        .split(/[,]+/)
        .map(s => String(s ?? '').trim())
        .filter(Boolean)
        .slice(0, 40),
      raw_text_excerpt: fullText.slice(0, 24000),
    };
  }

  /** Rule-based noise removal + dedupe (lightweight “classification”) */
  function classifyAndCleanStructured(profile) {
    const p = profile && typeof profile === 'object' ? JSON.parse(JSON.stringify(profile)) : {};
    const noiseLine = /^(show all|show more|message|connect|follow|linkedin|privacy|cookie)/i;

    const clean = arr => {
      const src = Array.isArray(arr) ? arr : typeof arr === 'string' && arr ? arr.split(/\n+|,+/) : [];
      return [
        ...new Set(
          src.map(s => String(s ?? '').trim()).filter(s => s && !noiseLine.test(s) && s.length < 500),
        ),
      ];
    };

    p.skills = clean(p.skills).slice(0, 160);
    p.certifications = clean(p.certifications).slice(0, 80);
    p.languages = clean(p.languages).slice(0, 40);

    if (p.summary) {
      p.summary = String(p.summary)
        .split('\n')
        .map(l => String(l ?? '').trim())
        .filter(l => l && !noiseLine.test(l))
        .join('\n')
        .slice(0, 12000);
    }

    if (p.identity) {
      for (const k of Object.keys(p.identity)) {
        if (typeof p.identity[k] === 'string') p.identity[k] = p.identity[k].replace(/\s+/g, ' ').trim();
      }
    }

    /* Simple inferred family from keywords (local, no network) */
    const blob = `${p.identity?.headline || ''} ${p.summary || ''} ${(p.skills || []).join(' ')}`.toLowerCase();
    let inferred_track = 'general';
    if (/\b(ui|ux|user experience|figma|sketch)\b/.test(blob)) inferred_track = 'ui_ux';
    else if (/\b(frontend|react|vue|angular|typescript|javascript)\b/.test(blob)) inferred_track = 'frontend';
    else if (/\b(backend|api|java|python|go|rust|node)\b/.test(blob)) inferred_track = 'backend';
    else if (/\b(data|machine learning|ml|ai|analytics|sql)\b/.test(blob)) inferred_track = 'data_ml';
    p.inferred_track = inferred_track;

    if (p._meta) delete p._meta;

    return p;
  }

  /** Canonical plain text for ML / preview API */
  function structuredToCandidateText(p) {
    if (!p) return '';
    const lines = [];
    if (p.identity?.full_name) lines.push(`Name: ${p.identity.full_name}`);
    if (p.identity?.headline) lines.push(`Current Title: ${p.identity.headline}`);
    if (p.identity?.location) lines.push(`Location: ${p.identity.location}`);
    if (p.identity?.email) lines.push(`Email: ${p.identity.email}`);
    if (p.skills?.length) lines.push(`Skills: ${p.skills.join(', ')}`);
    if (p.summary) lines.push(`SUMMARY / ABOUT\n${p.summary}`);
    if (p.experience?.length) {
      lines.push('WORK EXPERIENCE');
      p.experience.forEach(x => {
        const bits = [x.title, x.organization && `@ ${x.organization}`, x.dates_or_location && `| ${x.dates_or_location}`]
          .filter(Boolean)
          .join(' ');
        lines.push(`  ${bits}`);
      });
    }
    if (p.education?.length) {
      lines.push('EDUCATION');
      p.education.forEach(e => lines.push(`  ${e.raw || ''}`));
    }
    if (p.certifications?.length) {
      lines.push('CERTIFICATIONS');
      p.certifications.forEach(c => lines.push(`  ${c}`));
    }
    if (p.raw_text_excerpt && lines.join('\n').length < 400)
      lines.push('--- SOURCE EXCERPT ---', p.raw_text_excerpt.slice(0, 12000));
    return lines.join('\n').trim().slice(0, 28000);
  }

  async function runProfilePipeline(req) {
    const opts = req && typeof req === 'object' ? req : {};
    const skipDomWait = Boolean(opts.skipDomWait);
    const rescanOnly = Boolean(opts.rescanOnly);

    if (!isLinkedInMemberProfileUrl()) {
      return {
        success: false,
        extracted_ok: false,
        fullText: '',
        error:
          'This tab is not a LinkedIn member profile (linkedin.com/in/…). The extension was about to read another site (for example RezumeAI). Open the candidate’s LinkedIn profile in a tab and run the extension from there.',
        profile_json: null,
        pipeline_version: PIPELINE_VERSION,
      };
    }

    if (!skipDomWait && !rescanOnly) {
      await waitForDomStability({});
      await requestIdlePolyfill(380);
    }

    const asyncFn = globalThis.__rezumeExtractLinkedInAsync;
    const syncFn = globalThis.__rezumeExtractLinkedIn;

    let legacy;
    if (typeof asyncFn === 'function') legacy = await asyncFn(req);
    else if (typeof syncFn === 'function') legacy = syncFn(req);
    else {
      return {
        success: false,
        fullText: '',
        extracted_ok: false,
        error:
          globalThis.__rezumeExtractInitError ||
          'Extractor not loaded. Reload the extension and hard-refresh LinkedIn.',
        profile_json: null,
        pipeline_version: PIPELINE_VERSION,
      };
    }

    if (!legacy || legacy.success === false) {
      return {
        ...(legacy || {}),
        profile_json: null,
        pipeline_version: PIPELINE_VERSION,
      };
    }

    let structured;
    let pageBlob = '';
    let roles = {};
    try {
      if (isLinkedInMemberProfileUrl()) {
        try {
          pageBlob = scrapeWholePageMainText(100000);
        } catch {
          /* ignore */
        }
      }
      const combinedForClassify = [pageBlob, String(legacy.fullText || '')].filter(Boolean).join('\n\n');
      roles = classifyTextIntoRoles(combinedForClassify);
      structured = classifyAndCleanStructured(
        mergeRoleSections(legacyExtractToStructured(legacy), roles),
      );
    } catch (e) {
      structured = classifyAndCleanStructured(legacyExtractToStructured(legacy));
      try {
        roles = classifyTextIntoRoles(String(legacy.fullText || ''));
      } catch {
        roles = {};
      }
    }
    const canonical = structuredToCandidateText(structured);
    const prev = String(legacy.fullText || '');
    if (canonical.length > prev.length + 80)
      legacy = { ...legacy, fullText: canonical.slice(0, 28000) };
    else if (prev.length < 200 && canonical.length > prev.length + 40)
      legacy = { ...legacy, fullText: canonical.slice(0, 28000) };

    return {
      ...legacy,
      profile_json: structured,
      candidate_text_canonical: canonical,
      pipeline_version: PIPELINE_VERSION,
      scrape_chars: pageBlob.length,
      classified_roles: Object.fromEntries(
        Object.entries(roles).map(([k, v]) => [k, Array.isArray(v) ? v.length : 0]),
      ),
    };
  }

  globalThis.__rezumeRunProfilePipeline = runProfilePipeline;
  globalThis.__rezumePipelineVersion = PIPELINE_VERSION;
})();
