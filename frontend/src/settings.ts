/**
 * Typed accessors for all user-saved settings stored in localStorage.
 * Every getter returns a typed value with a sensible default.
 */

function getLS<T>(key: string, defaults: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return defaults;
    return { ...defaults, ...JSON.parse(raw) } as T;
  } catch {
    return defaults;
  }
}

// ── Account settings ──────────────────────────────────────────────────────────

export type AccountSettings = {
  defaultDashboard: string;
  candidatesPerPage: string;
  defaultTopMatches: string;
  dateFormat: string;
  timeZone: string;
  language: string;
};

export function getAccountSettings(): AccountSettings {
  return getLS("rezume.settings.account", {
    defaultDashboard: "Dashboard Overview",
    candidatesPerPage: "10",
    defaultTopMatches: "3",
    dateFormat: "DD/MM/YYYY",
    timeZone: "GMT +05:00",
    language: "English",
  });
}

export function getCandidatesPerPage(): number {
  const v = parseInt(getAccountSettings().candidatesPerPage, 10);
  return isNaN(v) || v < 1 ? 10 : v;
}

export function getDefaultTopMatches(): number {
  const v = parseInt(getAccountSettings().defaultTopMatches, 10);
  return isNaN(v) || v < 1 ? 3 : v;
}

// ── Screening settings ────────────────────────────────────────────────────────

export type ScreeningSettings = {
  minMatchScore: string;
  showOnlyTopMatches: string;
  skillsImportance: string;
  experienceImportance: string;
  certifications: string;
  autoRankCandidates: string;
  autoRejectLowMatches: string;
};

export function getScreeningSettings(): ScreeningSettings {
  return getLS("rezume.settings.screening", {
    minMatchScore: "70%",
    showOnlyTopMatches: "ON",
    skillsImportance: "High",
    experienceImportance: "Medium",
    certifications: "Low",
    autoRankCandidates: "ON",
    autoRejectLowMatches: "OFF",
  });
}

/** Returns the minimum match score as a 0–100 number (e.g. "70%" → 70). */
export function getMinMatchScore(): number {
  const raw = getScreeningSettings().minMatchScore;
  const v = parseInt(raw, 10);
  return isNaN(v) ? 70 : v;
}

export function getShowOnlyTopMatches(): boolean {
  return getScreeningSettings().showOnlyTopMatches === "ON";
}

// ── Preferences settings ──────────────────────────────────────────────────────

export type PrefSettings = {
  theme: string;
  fontSize: string;
  defaultCandidateSort: string;
  defaultClientSort: string;
  defaultJobSort: string;
};

export function getPrefSettings(): PrefSettings {
  return getLS("rezume.settings.pref", {
    theme: "Light / Dark",
    fontSize: "Medium",
    defaultCandidateSort: "Match Score",
    defaultClientSort: "Newest",
    defaultJobSort: "Priority Based",
  });
}

/** Maps the human sort label → CandidatesPage sort key. */
export function getDefaultCandidateSortKey(): string {
  const label = getPrefSettings().defaultCandidateSort;
  const map: Record<string, string> = {
    "Match Score": "score_desc",
    "Name": "name_asc",
    "Date Added": "created_desc",
    "Status": "score_desc",
  };
  return map[label] ?? "score_desc";
}

/** Maps the font size preference to a CSS font-size multiplier. */
export function getFontSizeScale(): string {
  const s = getPrefSettings().fontSize;
  if (s === "Small") return "0.9";
  if (s === "Large") return "1.1";
  return "1";
}

/** Returns the theme identifier: "dark" | "light" | "system" */
export function getTheme(): "dark" | "light" | "system" {
  const t = getPrefSettings().theme;
  if (t === "Dark") return "dark";
  if (t === "Light") return "light";
  return "system"; // "Light / Dark" follows system preference
}

/** Applies the current theme and font-size to the document root immediately. */
export function applyAppSettings(): void {
  const root = document.documentElement;

  // Font size
  const scale = getFontSizeScale();
  root.style.setProperty("--font-scale", scale);

  // Theme
  const theme = getTheme();
  root.removeAttribute("data-theme");
  if (theme === "light") {
    root.setAttribute("data-theme", "light");
  } else if (theme === "dark") {
    root.setAttribute("data-theme", "dark");
  }
  // "system" → no attribute, CSS uses prefers-color-scheme
}
