import type { CandidateDto } from "./api";

/**
 * Score shown on the candidates list, dashboard candidate summary, and profile header:
 * cohort-relative profile strength (same backend field as dashboard preview).
 * Per-job match percentages live on job ranking views.
 */
export function candidateListProfileScore(c: CandidateDto): number {
  const p = c.profile_percentile_score;
  if (p != null && !Number.isNaN(Number(p))) {
    return Math.max(0, Math.min(100, Math.round(Number(p))));
  }
  const v = c.competition_score;
  if (v != null && !Number.isNaN(Number(v))) {
    return Math.max(0, Math.min(100, Math.round(Number(v))));
  }
  const years = Math.min(20, Math.max(0, c.years_experience ?? 0));
  const skillsCount = (c.skills || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean).length;
  const hasDegree = Boolean((c.highest_degree || "").trim());
  const hasCerts = Boolean((c.certifications || "").trim());
  const s = years * 4 + Math.min(skillsCount, 30) * 1.6 + (hasDegree ? 6 : 0) + (hasCerts ? 4 : 0);
  return Math.max(0, Math.min(100, Math.round(s)));
}
