import type { CandidateDto } from "./api";

/**
 * Human-readable experience for profile/list cells.
 * Fresher profiles should never show a blank "—" for years when title is Fresher.
 */
export function formatCandidateExperience(c: Pick<CandidateDto, "title" | "years_experience">): string {
  const title = (c.title || "").trim().toLowerCase();
  const y = c.years_experience;
  if (title === "fresher") {
    if (y != null && Number.isFinite(Number(y)) && Number(y) > 0) {
      return `${Number(y)} years`;
    }
    return "Fresher";
  }
  if (y != null && Number.isFinite(Number(y))) {
    const n = Number(y);
    if (n === 0) return "0 years";
    return `${n} years`;
  }
  return "—";
}
