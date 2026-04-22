import type { CandidateDto } from "./api";

/** Shown in lists/detail when we have no parsed name (backend stores an empty `full_name`). */
export const NO_CANDIDATE_NAME_DISPLAY = "—";

const LEGACY_BAD_NAMES = new Set(["", "candidate", "unknown candidate", "unknown"]);

function normalizedDisplayName(raw: string): string {
  const t = raw.trim();
  if (!t) return NO_CANDIDATE_NAME_DISPLAY;
  if (LEGACY_BAD_NAMES.has(t.toLowerCase())) return NO_CANDIDATE_NAME_DISPLAY;
  return t;
}

export function candidateDisplayName(c: { full_name?: string | null }): string {
  return normalizedDisplayName(c.full_name ?? "");
}

export function candidateAvatarInitials(c: { full_name?: string | null }): string {
  const raw = (c.full_name ?? "").trim();
  if (!raw || LEGACY_BAD_NAMES.has(raw.toLowerCase())) return "?";
  const parts = raw.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const a = parts[0]?.[0] ?? "";
  const b = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (a + b).toUpperCase();
}

export function candidateMailtoSubjectLine(c: CandidateDto): string {
  const t = (c.full_name ?? "").trim();
  if (!t || LEGACY_BAD_NAMES.has(t.toLowerCase())) {
    return "Rezume AI";
  }
  return `Rezume AI — ${t}`;
}
