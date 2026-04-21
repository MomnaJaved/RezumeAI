import React, { useEffect, useMemo, useState } from "react";
import DashFrame from "../DashFrame";
import ResumePreviewModal from "../components/ResumePreviewModal";
import {
  fetchJobByExternalId,
  fetchJobsPage,
  fetchSavedRankings,
  fetchStage1Pool,
  logActivity,
  triggerMatchCandidates,
  updateJobShortlist,
  type Job,
  type JobSavedRankingRow,
  type Stage1PoolRow,
} from "../api";
import { useSearchParams } from "react-router-dom";
import { useToast } from "../toast";
import { getAutoRankCandidates, getAutoRejectLowMatches, getDefaultTopMatches, getMinMatchScore, getNotifSettings, getShowOnlyTopMatches } from "../settings";
import { useT } from "../i18n";

// Top-K options: covers the settings choices (3,5,10,20) plus extended options
const TOP_K_OPTIONS = [3, 5, 10, 20, 25, 50] as const;

/** After a match run, log a low_match activity if any candidates scored below threshold. */
async function checkAndLogLowMatch(
  rankings: JobSavedRankingRow[],
  jobTitle: string,
  jobExternalId: string,
): Promise<void> {
  if (!getNotifSettings().lowMatchWarning || getNotifSettings().lowMatchWarning !== "ON") return;
  const threshold = getMinMatchScore() / 100;
  if (threshold <= 0) return;
  const lowCount = rankings.filter((r) => {
    const score = r.cross_encoder_score ?? r.sbert_similarity ?? 0;
    return score < threshold;
  }).length;
  if (lowCount === 0) return;
  try {
    await logActivity(
      "low_match",
      `Low match warning: ${lowCount} candidate${lowCount > 1 ? "s" : ""} scored below ${getMinMatchScore()}% for "${jobTitle || jobExternalId}"`,
      `/jobs?job=${encodeURIComponent(jobExternalId)}`,
    );
  } catch {
    // Non-critical — never block the UI
  }
}

type SortKey = "rank_asc" | "score_desc" | "match_desc" | "name_asc";

function pct(score: number) {
  const x = Math.max(0, Math.min(1, Number(score) || 0));
  return `${Math.round(x * 100)}%`;
}

function sbertPct(score: number) {
  const x = Math.max(0, Math.min(1, Number(score) || 0));
  return x.toFixed(2);
}

export default function MatchingPage() {
  const toast = useToast();
  const t = useT();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobLoading, setJobLoading] = useState(false);

  const selectedJob = (sp.get("job") || "").trim();
  const [job, setJob] = useState<Job | null>(null);
  const [rankings, setRankings] = useState<JobSavedRankingRow[]>([]);
  const [topInsight, setTopInsight] = useState<string | null>(null);
  const [loadingRankings, setLoadingRankings] = useState(false);
  const [topK, setTopK] = useState<number>(() => {
    const fromUrl = Number(sp.get("top"));
    // Minimum 3 must always be shown; URL param overrides default when present
    return fromUrl > 0 ? Math.max(3, fromUrl) : Math.max(3, getDefaultTopMatches());
  });
  const [sortBy, setSortBy] = useState<SortKey>((sp.get("sort") as SortKey) || "rank_asc");
  const [busyRefresh] = useState(false);
  const [pool, setPool] = useState<Stage1PoolRow[]>([]);
  const [loadingPool, setLoadingPool] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [resumeExternalId, setResumeExternalId] = useState<string>("");
  const [matchingAll, setMatchingAll] = useState(false);
  // Compare candidates
  const [compareCount, setCompareCount] = useState<number>(2);
  const [compareFields, setCompareFields] = useState<Set<string>>(new Set(["skills", "experience"]));
  const [showCompare, setShowCompare] = useState(false);
  const [shortlistedIds, setShortlistedIds] = useState<Set<string>>(new Set());
  const [poolFilter, setPoolFilter] = useState<"all" | "public" | "private">("all");

  // Read settings once per render — must be before any useEffect that references them
  const minScorePct = getMinMatchScore();
  const showOnlyTop = getShowOnlyTopMatches();
  const autoReject = getAutoRejectLowMatches();
  const autoRank = getAutoRankCandidates();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setJobLoading(true);
      try {
        // Matching dropdown must only show active/eligible jobs.
        const res = await fetchJobsPage({
          skip: 0,
          limit: 50,
          q: q.trim() || undefined,
          status: "active",
          sort: "created_desc",
        });
        if (cancelled) return;
        // Safety: filter again client-side.
        const safe = (res.items || []).filter(
          (j) => !["cancelled", "completed", "inactive", "on_hold"].includes(String(j.status || "").toLowerCase()),
        );
        setJobs(safe);
      } catch (e) {
        if (!cancelled) toast.error((e as Error).message || "Failed to load jobs");
      } finally {
        if (!cancelled) setJobLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [q, toast]);

  useEffect(() => {
    if (!selectedJob) {
      setJob(null);
      setRankings([]);
      setTopInsight(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingRankings(true);
      try {
        const j = await fetchJobByExternalId(selectedJob);
        if (cancelled) return;
        setJob(j);
      } catch (e) {
        if (!cancelled) toast.error((e as Error).message || "Failed to load job");
      } finally {
        if (!cancelled) setLoadingRankings(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedJob, toast]);

  const loadStoredRankings = async () => {
    if (!selectedJob) return;
    setLoadingRankings(true);
    try {
      const res = await fetchSavedRankings(selectedJob);
      setRankings(res.rankings || []);
      setTopInsight(res.top_candidate_insight ?? null);
    } catch (e) {
      setRankings([]);
      setTopInsight(null);
      // If there are no stored matches yet, user can refresh; keep UI quiet unless it's a real error.
    } finally {
      setLoadingRankings(false);
    }
  };

  useEffect(() => {
    void loadStoredRankings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedJob]);

  useEffect(() => {
    if (!selectedJob) {
      setPool([]);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingPool(true);
      try {
        const res = await fetchStage1Pool(selectedJob, 50);
        if (!cancelled) {
          setPool(res.items || []);
        }
      } catch (e) {
        if (!cancelled) toast.error((e as Error).message || "Failed to load candidates pool");
      } finally {
        if (!cancelled) setLoadingPool(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedJob, toast]);

  // Auto Rank: when enabled in Screening settings, trigger matching automatically
  // whenever a new job is selected (rankings are empty = no previous run).
  useEffect(() => {
    if (!selectedJob || !autoRank || rankings.length > 0) return;
    let cancelled = false;
    (async () => {
      try {
        setMatchingAll(true);
        const res = await triggerMatchCandidates(selectedJob, topK);
        if (cancelled) return;
        const newRankings = res.rankings || [];
        setRankings(newRankings);
        setTopInsight((res.top_candidate_insight || "").trim() || null);
        setSortBy("rank_asc");
        void checkAndLogLowMatch(newRankings, job?.title ?? "", selectedJob);
      } catch {
        // Fail silently for auto-rank; user can still click Match manually
      } finally {
        if (!cancelled) setMatchingAll(false);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedJob, autoRank]);

  const rankByCandidateId = useMemo(() => {
    const m = new Map<string, JobSavedRankingRow>();
    for (const r of rankings || []) {
      if (r?.candidate_external_id) m.set(r.candidate_external_id, r);
    }
    return m;
  }, [rankings]);

  const visibleRows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return [...pool]
      .filter((r) => {
        // Text search
        if (needle) {
          const hay = `${r.candidate_name || ""} ${r.candidate_title || ""} ${r.candidate_role || ""} ${r.skills_summary || ""}`.toLowerCase();
          if (!hay.includes(needle)) return false;
        }
        // Minimum match score filter — only active when Auto Reject is ON
        if (autoReject) {
          const rankRow = rankByCandidateId.get(r.candidate_id);
          if (rankRow) {
            const scorePct = Math.round((rankRow.cross_encoder_score ?? 0) * 100);
            if (scorePct < minScorePct) return false;
          }
        }
        // Pool type filter
        if (poolFilter !== "all") {
          const wantPublic = poolFilter === "public";
          if (Boolean(r.is_public) !== wantPublic) return false;
        }
        return true;
      })
      .sort((a, b) => {
        if (sortBy === "name_asc") return (a.candidate_name || "").localeCompare(b.candidate_name || "");
        if (sortBy === "rank_asc") {
          const ra = rankByCandidateId.get(a.candidate_id)?.rank_position ?? Number.POSITIVE_INFINITY;
          const rb = rankByCandidateId.get(b.candidate_id)?.rank_position ?? Number.POSITIVE_INFINITY;
          if (ra !== rb) return ra - rb;
          return (b.sbert_score || 0) - (a.sbert_score || 0);
        }
        if (sortBy === "match_desc") {
          const sa = rankByCandidateId.get(a.candidate_id)?.cross_encoder_score ?? -1;
          const sb = rankByCandidateId.get(b.candidate_id)?.cross_encoder_score ?? -1;
          if (sb !== sa) return sb - sa;
          return (b.sbert_score || 0) - (a.sbert_score || 0);
        }
        // score_desc: retrieval score
        return (b.sbert_score || 0) - (a.sbert_score || 0);
      })
      .slice(0, showOnlyTop ? topK : undefined);
  }, [pool, q, sortBy, topK, rankByCandidateId, poolFilter]);

  const rankOneRow = useMemo(() => {
    if (!rankings.length) return null;
    const withPos = rankings.filter((r) => r.rank_position != null && r.rank_position > 0);
    if (withPos.length) {
      return withPos.reduce((a, b) => ((a.rank_position ?? 99) <= (b.rank_position ?? 99) ? a : b));
    }
    return [...rankings].sort((a, b) => (b.cross_encoder_score || 0) - (a.cross_encoder_score || 0))[0] ?? null;
  }, [rankings]);

  const skillsList = useMemo(() => {
    const raw = (job?.skills || "").trim();
    if (!raw) return [];
    return raw
      .split(/[,;\n]/g)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 12);
  }, [job?.skills]);

  const exportPdf = () => {
    const rows = (rankings || []).slice(0, topK);
    const jobTitle = job?.title || selectedJob || "Job";
    const date = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

    const tableRows = rows
      .map(
        (r) => `
        <tr>
          <td>${r.rank_position ?? "—"}</td>
          <td>
            <strong>${r.candidate_name || r.candidate_external_id}</strong>
            ${r.candidate_title ? `<br/><span class="sub">${r.candidate_title}</span>` : ""}
          </td>
          <td class="score">${pct(r.cross_encoder_score)}</td>
          <td>${r.years_experience != null ? `${r.years_experience} yrs` : "—"}</td>
          <td>${r.highest_degree || "—"}</td>
          <td class="skills">${r.skills_summary || "—"}</td>
        </tr>`,
      )
      .join("");

    const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Match Results – ${jobTitle}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 12px; color: #0f172a; padding: 32px 36px; }
    h1 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
    .meta { font-size: 11px; color: #64748b; margin-bottom: 20px; }
    table { width: 100%; border-collapse: collapse; }
    thead tr { background: #0f172a; color: #fff; }
    thead th { padding: 8px 10px; text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; }
    tbody tr:nth-child(even) { background: #f1f5f9; }
    tbody td { padding: 7px 10px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
    .score { font-weight: 700; color: #0369a1; }
    .sub { font-size: 11px; color: #64748b; }
    .skills { font-size: 11px; color: #334155; max-width: 220px; }
    @media print { body { padding: 0; } }
  </style>
</head>
<body>
  <h1>Match Results – ${jobTitle}</h1>
  <div class="meta">Generated on ${date} · Top ${rows.length} candidates</div>
  <table>
    <thead>
      <tr>
        <th style="width:5%">#</th>
        <th style="width:22%">Candidate</th>
        <th style="width:9%">Match</th>
        <th style="width:10%">Experience</th>
        <th style="width:14%">Degree</th>
        <th>Skills</th>
      </tr>
    </thead>
    <tbody>${tableRows}</tbody>
  </table>
</body>
</html>`;

    const win = window.open("", "_blank", "width=900,height=700");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => { win.print(); }, 400);
  };

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">{t("matching.title")}</div>
            <div className="cand-search">
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by job title…" />
            </div>
            <select
              value={selectedJob || "all"}
              onChange={(e) => {
                const v = e.target.value;
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  if (v && v !== "all") next.set("job", v);
                  else next.delete("job");
                  return next;
                });
              }}
              aria-label="Job picker"
              disabled={jobLoading}
            >
              <option value="all">{jobLoading ? t("matching.loadingJobs") : t("matching.selectJob")}</option>
              {jobs.map((j) => (
                <option key={j.external_id} value={j.external_id}>
                  {j.title || j.external_id}
                </option>
              ))}
            </select>
          </div>

          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">{t("matching.filterBy")}</span>
            <select
              value={String(topK)}
              onChange={(e) => {
                const v = Math.max(3, Number(e.target.value) || 3);
                setTopK(v);
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("top", String(v));
                  return next;
                });
              }}
              aria-label="Top matches"
            >
              {TOP_K_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {t("matching.topMatches")} {n}
                </option>
              ))}
            </select>
            <select
              value={sortBy}
              onChange={(e) => {
                const v = (e.target.value as SortKey) || "score_desc";
                setSortBy(v);
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("sort", v);
                  return next;
                });
              }}
              aria-label="Sort by"
            >
              <option value="rank_asc">{t("matching.sortByRank")}</option>
              <option value="score_desc">{t("matching.sortByScore")}</option>
              <option value="match_desc">{t("matching.sortByMatch")}</option>
              <option value="name_asc">{t("matching.sortByName")}</option>
            </select>
            <select
              value={poolFilter}
              onChange={(e) => setPoolFilter(e.target.value as "all" | "public" | "private")}
              aria-label="Pool type filter"
            >
              <option value="all">All Candidates</option>
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
            <span style={{ marginLeft: "auto" }} />
            <button
              type="button"
              className="small-btn cand-primary-btn"
              disabled={busyRefresh || matchingAll || !selectedJob}
              onClick={async () => {
                if (!selectedJob) return;
                try {
                  setMatchingAll(true);
                  const res = await triggerMatchCandidates(selectedJob, topK);
                  const newRankings = res.rankings || [];
                  setRankings(newRankings);
                  setTopInsight((res.top_candidate_insight || "").trim() || null);
                  setSortBy("rank_asc");
                  setSp((prev) => {
                    const nextSp = new URLSearchParams(prev);
                    nextSp.set("sort", "rank_asc");
                    return nextSp;
                  });
                  toast.success("Matches saved — scores updated across all views.");
                  void checkAndLogLowMatch(newRankings, job?.title ?? "", selectedJob);
                } catch (e) {
                  const msg = (e as Error).message || "";
                  const friendly = msg.toLowerCase().includes("no sbert shortlist") || msg.toLowerCase().includes("match filters")
                    ? "No matching candidate in the pool."
                    : msg || "Failed to match candidates";
                  toast.error(friendly);
                } finally {
                  setMatchingAll(false);
                }
              }}
            >
              {matchingAll ? t("matching.matching") : t("matching.match")}
            </button>
            <button
              type="button"
              className="small-btn"
              disabled={loadingRankings || rankings.length === 0}
              onClick={exportPdf}
            >
              {t("matching.exportResults")}
            </button>
          </div>
        </div>
      }
    >
      {!selectedJob ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            {t("matching.selectJobPrompt")}
          </p>
        </div>
      ) : (
        <div className="job-overview-grid" style={{ gridTemplateColumns: "180px 1fr", alignItems: "stretch" }}>
          <div className="job-card" style={{ display: "flex", flexDirection: "column" }}>
            <div className="job-card-title">{t("matching.jobDescription")}</div>
            <div className="muted" style={{ marginBottom: 10 }}>
              <div>
                <strong>Job Title:</strong> {job?.title || "—"}
              </div>
              <div>
                <strong>Department:</strong> {job?.department || "—"}
              </div>
              <div>
                <strong>Experience:</strong> {job?.min_experience ?? "—"} Years
              </div>
              <div>
                <strong>Hiring Priority:</strong>{" "}
                {(job as any)?.recruitment_urgency ? String((job as any).recruitment_urgency)[0].toUpperCase() + String((job as any).recruitment_urgency).slice(1) : "—"}
              </div>
            </div>

            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ fontWeight: 700, marginBottom: 6 }}>
                Required Skills
              </div>
              {skillsList.length ? (
                <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                  {skillsList.map((s) => (
                    <li key={s} className="muted">
                      {s}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="muted">—</div>
              )}
            </div>
          </div>

          <div className="job-card" style={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
            <div className="job-card-title">{t("matching.candidates")}</div>

            {loadingPool ? (
              <div className="muted" style={{ flex: 1 }}>{t("common.loading")}</div>
            ) : pool.length === 0 ? (
              <div className="muted" style={{ flex: 1 }}>{t("matching.noPool")}</div>
            ) : (
              <div className="job-table-wrap job-table-wrap--scroll" style={{ flex: 1 }}>
                <table className="job-table">
                  <thead>
                    <tr>
                      <th style={{ width: "6%" }}>Rank</th>
                      <th style={{ width: "20%" }}>Name</th>
                      <th style={{ width: "9%" }}>Score</th>
                      <th style={{ width: "12%" }}>Experience</th>
                      <th>Certifications</th>
                      <th style={{ width: "10%" }}>Match</th>
                      <th style={{ width: "16%" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRows.map((r) => {
                        const rr = rankByCandidateId.get(r.candidate_id);
                        const pos = rr?.rank_position ?? null;
                        const ce = rr?.cross_encoder_score ?? null;
                        return (
                          <tr key={r.candidate_id}>
                            <td className="muted">{pos ?? "—"}</td>
                            <td>{r.candidate_name || r.candidate_id}</td>
                            <td style={{ color: "rgba(148, 163, 184, 0.95)", fontWeight: 800 }}>{sbertPct(r.sbert_score)}</td>
                            <td className="muted">{r.years_experience != null ? `${r.years_experience} Years` : "—"}</td>
                            <td className="muted">{(() => {
                                const raw = (r.certifications || "").trim();
                                if (!raw) return "0";
                                return String(raw.split(",").filter(Boolean).length);
                              })()}</td>
                            <td style={{ color: "rgba(56, 189, 248, 0.95)", fontWeight: 800 }}>
                              {ce != null ? pct(ce) : "—"}
                            </td>
                            <td>
                              <div style={{ display: "flex", gap: "0.45rem", alignItems: "center", flexWrap: "wrap" }}>
                                <button
                                  type="button"
                                  className="job-link-btn"
                                  onClick={() => {
                                    setResumeExternalId(r.candidate_id);
                                    setResumeOpen(true);
                                  }}
                                >
                                  {t("matching.viewResume")}
                                </button>
                                <a className="job-link-btn" href={`/candidates/lookup/${encodeURIComponent(r.candidate_id)}`}>
                                  {t("matching.viewProfile")}
                                </a>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            )}

            {/* ── Bottom section ── */}
            {(rankings.length > 0 || topInsight || rankOneRow) && (
              <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.08)" }}>

                {/* Comparison bar */}
                {rankings.length >= 2 && (
                  <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap", marginBottom: 12 }}>
                    <span style={{ fontSize: "0.82rem", fontWeight: 600, color: "rgba(203,213,225,0.85)", whiteSpace: "nowrap" }}>
                      {t("matching.compareTop")}
                    </span>
                    <select
                      value={String(compareCount)}
                      onChange={(e) => { setCompareCount(Number(e.target.value)); setShowCompare(false); }}
                      style={{
                        background: "rgba(2,6,23,0.4)",
                        color: "rgba(226,232,240,0.9)",
                        border: "1px solid rgba(255,255,255,0.14)",
                        borderRadius: "8px",
                        padding: "0.2rem 0.45rem",
                        fontSize: "0.82rem",
                        cursor: "pointer",
                      }}
                    >
                      {[2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                    {(["experience", "certifications", "skills", "education"] as const).map((field) => (
                      <label
                        key={field}
                        style={{ display: "flex", alignItems: "center", gap: "0.3rem", cursor: "pointer", fontSize: "0.82rem", color: "rgba(203,213,225,0.85)" }}
                      >
                        <input
                          type="checkbox"
                          checked={compareFields.has(field)}
                          onChange={() => {
                            setShowCompare(false);
                            setCompareFields((prev) => {
                              const next = new Set(prev);
                              if (next.has(field)) next.delete(field);
                              else next.add(field);
                              return next;
                            });
                          }}
                          style={{ accentColor: "rgba(56,189,248,0.9)", cursor: "pointer" }}
                        />
                        {field.charAt(0).toUpperCase() + field.slice(1)}
                      </label>
                    ))}
                    <button
                      type="button"
                      className="match-compare-btn"
                      disabled={compareFields.size === 0}
                      onClick={() => setShowCompare(true)}
                    >
                      {t("matching.compareCandidates")}
                    </button>
                  </div>
                )}

                {/* Bottom panels: compare table + insight */}
                <div style={{ display: "flex", gap: "0.85rem", alignItems: "flex-start" }}>

                  {/* Compare table */}
                  {showCompare && (() => {
                    const topCands = rankings.slice(0, Math.min(compareCount, rankings.length));
                    if (topCands.length < 2) return null;
                    const fields = (["experience", "certifications", "skills", "education"] as const).filter((f) => compareFields.has(f));
                    const fieldLabel: Record<string, string> = { experience: "Experience", certifications: "Certifications", skills: "Skills", education: "Education" };
                    return (
                      <div style={{ flex: 1, minWidth: 0, overflowX: "auto" }}>
                        <table className="match-compare-table">
                          <tbody>
                            {/* Name + score row — no heading */}
                            <tr>
                              {topCands.map((c) => (
                                <td key={c.candidate_external_id} className="match-compare-name-cell">
                                  <div className="match-compare-cand-name">{c.candidate_name || c.candidate_external_id}</div>
                                  <div className="match-compare-cand-score">{pct(c.cross_encoder_score)} match</div>
                                  {c.candidate_title && <div className="match-compare-cand-sub">{c.candidate_title}</div>}
                                </td>
                              ))}
                            </tr>
                            {/* Field sections */}
                            {fields.map((field) => (
                              <React.Fragment key={field}>
                                <tr className="match-compare-section-header">
                                  <td colSpan={topCands.length}>{fieldLabel[field]}</td>
                                </tr>
                                <tr>
                                  {topCands.map((c) => {
                                    let value = "—";
                                    if (field === "experience") value = c.years_experience != null ? `${c.years_experience} years` : "—";
                                    else if (field === "certifications") value = pool.find((p) => p.candidate_id === c.candidate_external_id)?.certifications?.trim() || "—";
                                    else if (field === "skills") value = c.skills_summary || "—";
                                    else if (field === "education") value = c.highest_degree || "—";
                                    return <td key={c.candidate_external_id} className="match-compare-data-cell">{value}</td>;
                                  })}
                                </tr>
                              </React.Fragment>
                            ))}
                            {/* Shortlist row */}
                            <tr>
                              {topCands.map((c) => (
                                <td key={c.candidate_external_id} className="match-compare-action-cell">
                                  <button
                                    type="button"
                                    className={`match-compare-btn${shortlistedIds.has(c.candidate_external_id) ? " match-compare-btn--done" : ""}`}
                                    disabled={!selectedJob || shortlistedIds.has(c.candidate_external_id)}
                                    onClick={async () => {
                                      if (!selectedJob) return;
                                      try {
                                        await updateJobShortlist(selectedJob, { add: [c.candidate_external_id] });
                                        setShortlistedIds((prev) => new Set([...prev, c.candidate_external_id]));
                                        toast.success(`${c.candidate_name || c.candidate_external_id} shortlisted.`);
                                      } catch (e) {
                                        toast.error((e as Error).message || "Failed to shortlist");
                                      }
                                    }}
                                  >
                                    {shortlistedIds.has(c.candidate_external_id) ? "Shortlisted ✓" : "Shortlist"}
                                  </button>
                                </td>
                              ))}
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    );
                  })()}

                  {/* Top candidate insight */}
                  {(topInsight || rankOneRow) && (
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="job-card-title" style={{ marginBottom: 6 }}>{t("matching.topInsight")}</div>
                      <p className="muted" style={{ lineHeight: 1.65, margin: 0, fontSize: "0.88rem" }}>
                        {topInsight ||
                          (rankOneRow
                            ? `${rankOneRow.candidate_name || rankOneRow.candidate_external_id} is ranked #1 for ${job?.title || selectedJob} with a match score of ${pct(rankOneRow.cross_encoder_score)}. Click "Match" to re-run and load the full narrative insight.`
                            : null)}
                      </p>
                    </div>
                  )}

                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <ResumePreviewModal
        open={resumeOpen}
        externalId={resumeExternalId}
        onClose={() => {
          setResumeOpen(false);
          setResumeExternalId("");
        }}
      />
    </DashFrame>
  );
}

