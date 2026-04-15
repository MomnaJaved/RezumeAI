import type { CandidateDto } from "./api";

/** Matches backend `UNKNOWN_CANDIDATE` for people we could not name confidently. */
export const UNKNOWN_CANDIDATE_LABEL = "Unknown Candidate";

export function candidateDisplayName(c: { full_name?: string | null }): string {
  const raw = (c.full_name ?? "").trim();
  if (!raw) return UNKNOWN_CANDIDATE_LABEL;
  if (raw.toLowerCase() === "candidate") return UNKNOWN_CANDIDATE_LABEL;
  return raw;
}

export function candidateAvatarInitials(c: { full_name?: string | null }): string {
  const n = candidateDisplayName(c);
  if (n === UNKNOWN_CANDIDATE_LABEL) return "?";
  const parts = n.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  const a = parts[0]?.[0] ?? "";
  const b = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (a + b).toUpperCase();
}

export function candidateMailtoSubjectLine(c: CandidateDto): string {
  return `Rezume AI — ${candidateDisplayName(c)}`;
}
