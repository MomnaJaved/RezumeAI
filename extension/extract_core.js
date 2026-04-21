/**
 * LinkedIn profile scrape — runs in the extension isolated world (content script).
 * Exposed for: chrome.tabs.sendMessage (via content.js) and programmatic executeScript fallback.
 */
(function initRezumeExtract() {
  if (typeof globalThis.__rezumeExtractLinkedIn === 'function') return;

  function rootEl() {
    return document.querySelector('main[role="main"]') || document.querySelector('main') || document.body;
  }

  /**
   * LinkedIn virtualizes Experience / Education / Skills until those regions scroll into view.
   * Drive the profile <main> scroller + anchor ids so list nodes mount before we read the DOM.
   */
  function primeProfileSections() {
    const main = document.querySelector('main[role="main"]') || document.querySelector('main');
    if (main && main.scrollHeight > (main.clientHeight || 0) + 50) {
      const h = main.scrollHeight;
      for (let i = 0; i <= 10; i++) {
        try {
          main.scrollTop = (h * i) / 10;
        } catch { /* ignore */ }
      }
    }
    try {
      window.scrollTo(0, Math.min(document.body.scrollHeight, 8000));
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
    ].forEach(id => {
      const el = document.getElementById(id);
      try {
        el?.scrollIntoView({ block: 'center', inline: 'nearest' });
      } catch { /* ignore */ }
    });
    try {
      main?.scrollTo?.(0, 0);
    } catch { /* ignore */ }
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
      const t = (h.innerText || '').replace(/\s+/g, ' ').trim();
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
    const el = document.getElementById(slug);
    if (!el) return null;
    return (
      el.closest('section.artdeco-card') ||
      el.closest('div.artdeco-card') ||
      el.closest('section') ||
      el.closest('[data-view-name]') ||
      el.parentElement
    );
  }

  function sectionExperience(root) {
    return (
      sectionFor('experience') ||
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
      sectionByHeading(root, [/^Skills$/i, /^Compétences$/i, /^Kenntnisse$/i, /^Habilidades$/i])
    );
  }

  function sectionEducation(root) {
    return (
      sectionFor('education') ||
      sectionByHeading(root, [/^Education$/i, /^Ausbildung$/i, /^Formation$/i, /^Educación$/i])
    );
  }

  function arHidden(item) {
    return txs('span[aria-hidden="true"]', item);
  }

  /** When LinkedIn omits aria-hidden spans, fall back to visible line chunks. */
  function rowTextParts(item) {
    let parts = arHidden(item);
    if (parts.length) return parts;
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
    sec
      .querySelectorAll(
        [
          'li[class*="pvs-list__paged-list-item"]',
          'li[class*="pvs-list__item--two-column"]',
          'li[class*="pvs-list__item--one-column"]',
          'li[class*="pvs-entity"]',
          'li.artdeco-list__item',
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

  globalThis.__rezumeExtractLinkedIn = function rezumeExtractLinkedIn() {
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

    const skillsList = [];
    const skillsSec = sectionSkills(main);
    if (skillsSec) {
      const bold = txs('.t-bold span[aria-hidden="true"]', skillsSec);
      if (bold.length) {
        bold.forEach(s => {
          if (s.length <= 80 && !skillsList.includes(s)) skillsList.push(s);
        });
      } else {
        txs('a[data-field="skill_card_skill_topic"] span[aria-hidden="true"]', skillsSec).forEach(s => {
          if (s.length <= 80 && !skillsList.includes(s)) skillsList.push(s);
        });
      }
    }

    const certsList = [];
    const certSec = sectionFor('licenses_and_certifications') || sectionFor('certifications');
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
      lines.push(skillsList.slice(0, 50).join(', '));
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

    let fullText = lines.join('\n').trim();

    const structuredLen = fullText.length;
    const hasIdentity = Boolean(nameFinal || (title || '').trim());
    const hasSections =
      about.length > 40 ||
      expItems.length > 0 ||
      eduItems.length > 0 ||
      skillsList.length > 0;

    const mainRaw = cleanLines((main.innerText || '').trim());
    const missingLists = expItems.length === 0 && eduItems.length === 0 && skillsList.length === 0;

    /*
     * If structured cards parsed empty (common when lists were not mounted yet), append the
     * profile <main> text so recruiters still get Experience/Education/Skills content.
     */
    if (mainRaw.length > (fullText?.length || 0) + 80) {
      if (!fullText || fullText.length < 200 || missingLists) {
        fullText =
          `${fullText ? fullText + '\n\n' : ''}--- FULL PROFILE (LinkedIn main) ---\n${mainRaw}`.slice(0, 16000);
      }
    }

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
      skills: skillsList.slice(0, 50).join(', '),
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
  };

  /**
   * Scroll profile <main> slowly so LinkedIn mounts Experience/Education/Skills, then run sync extract.
   */
  globalThis.__rezumeExtractLinkedInAsync = async function rezumeExtractLinkedInAsync() {
    const main = document.querySelector('main[role="main"]') || document.querySelector('main');
    if (main) {
      const h = Math.max(main.scrollHeight || 0, 1200);
      for (let i = 0; i <= 12; i++) {
        try {
          main.scrollTop = (h * i) / 12;
        } catch { /* ignore */ }
        await new Promise(r => setTimeout(r, 70));
      }
      ['experience', 'education', 'skills', 'licenses_and_certifications', 'projects'].forEach(id => {
        try {
          document.getElementById(id)?.scrollIntoView({ block: 'center' });
        } catch { /* ignore */ }
      });
      await new Promise(r => setTimeout(r, 320));
      try {
        main.scrollTop = 0;
      } catch { /* ignore */ }
    }
    return globalThis.__rezumeExtractLinkedIn();
  };
})();
