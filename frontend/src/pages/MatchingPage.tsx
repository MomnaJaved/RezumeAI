import { useEffect, useMemo, useState } from "react";
import DashFrame from "../DashFrame";
import {
  fetchJobByExternalId,
  fetchJobsPage,
  fetchJobShortlist,
  fetchSavedRankings,
  fetchStage1Pool,
  rankShortlist,
  updateJobShortlist,
  type Job,
  type ShortlistRow,
  type Stage1PoolRow,
} from "../api";
import { useSearchParams } from "react-router-dom";
import { useToast } from "../toast";

type SortKey = "score_desc" | "name_asc";

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
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobLoading, setJobLoading] = useState(false);

  const selectedJob = (sp.get("job") || "").trim();
  const [job, setJob] = useState<Job | null>(null);
  const [rankings, setRankings] = useState<
    Array<{
      rank_position: number;
      cross_encoder_score: number;
      candidate_external_id: string;
      candidate_name: string;
      candidate_title: string;
      years_experience: number | null;
      highest_degree: string;
      skills_summary: string;
    }>
  >([]);
  const [loadingRankings, setLoadingRankings] = useState(false);
  const [topK, setTopK] = useState<number>(Number(sp.get("top") || 5) || 5);
  const [sortBy, setSortBy] = useState<SortKey>((sp.get("sort") as SortKey) || "score_desc");
  const [busyRefresh, setBusyRefresh] = useState(false);
  const [tab, setTab] = useState<"pool" | "shortlisted">("pool");
  const [pool, setPool] = useState<Stage1PoolRow[]>([]);
  const [shortlisted, setShortlisted] = useState<ShortlistRow[]>([]);
  const [loadingPool, setLoadingPool] = useState(false);
  const [loadingShortlist, setLoadingShortlist] = useState(false);

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
    } catch (e) {
      setRankings([]);
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
      setShortlisted([]);
      setTab("pool");
      return;
    }
    let cancelled = false;
    (async () => {
      setLoadingPool(true);
      try {
        const res = await fetchStage1Pool(selectedJob, 50);
        if (!cancelled) setPool(res.items || []);
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

  useEffect(() => {
    if (!selectedJob) return;
    let cancelled = false;
    (async () => {
      setLoadingShortlist(true);
      try {
        const res = await fetchJobShortlist(selectedJob);
        if (!cancelled) setShortlisted(res.items || []);
      } catch {
        if (!cancelled) setShortlisted([]);
      } finally {
        if (!cancelled) setLoadingShortlist(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedJob]);

  const doRankShortlist = async () => {
    if (!selectedJob) return;
    setBusyRefresh(true);
    try {
      await rankShortlist(selectedJob);
      toast.success("Matches refreshed.");
      setTab("shortlisted");
      await loadStoredRankings();
    } catch (e) {
      toast.error((e as Error).message || "Failed to refresh matches");
    } finally {
      setBusyRefresh(false);
    }
  };

  const sortedRows = useMemo(() => {
    const rows = [...rankings];
    if (sortBy === "name_asc") rows.sort((a, b) => (a.candidate_name || "").localeCompare(b.candidate_name || ""));
    else rows.sort((a, b) => (b.cross_encoder_score || 0) - (a.cross_encoder_score || 0));
    return rows;
  }, [rankings, sortBy]);

  const skillsList = useMemo(() => {
    const raw = (job?.skills || "").trim();
    if (!raw) return [];
    return raw
      .split(/[,;\n]/g)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 12);
  }, [job?.skills]);

  const exportCsv = () => {
    const headers = ["Rank", "Candidate", "Title", "Score", "Years experience", "Degree", "Skills summary"];
    const lines = [headers.join(",")];
    for (const r of sortedRows.slice(0, topK)) {
      const esc = (v: string) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      lines.push(
        [
          String(r.rank_position),
          esc(r.candidate_name || r.candidate_external_id),
          esc(r.candidate_title || ""),
          esc(pct(r.cross_encoder_score)),
          esc(r.years_experience == null ? "" : String(r.years_experience)),
          esc(r.highest_degree || ""),
          esc(r.skills_summary || ""),
        ].join(","),
      );
    }
    const blob = new Blob(["\uFEFF" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `matches_${selectedJob || "job"}.csv`;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Matching</div>
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
              <option value="all">{jobLoading ? "Loading jobs…" : "Select job"}</option>
              {jobs.map((j) => (
                <option key={j.external_id} value={j.external_id}>
                  {j.title || j.external_id}
                </option>
              ))}
            </select>
          </div>

          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">Filter By</span>
            <select
              value={String(topK)}
              onChange={(e) => {
                const v = Number(e.target.value) || 5;
                setTopK(v);
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  next.set("top", String(v));
                  return next;
                });
              }}
              aria-label="Top matches"
            >
              {[5, 10, 25, 50].map((n) => (
                <option key={n} value={n}>
                  Top Matches {n}
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
              <option value="score_desc">Sort by Match Score</option>
              <option value="name_asc">Sort by Name (A–Z)</option>
            </select>

            <div className="cand-toolbar-actions" style={{ marginLeft: "auto" }}>
              <button type="button" className={tab === "pool" ? "small-btn cand-primary-btn" : "small-btn"} disabled={!selectedJob} onClick={() => setTab("pool")}>
                Pool
              </button>
              <button type="button" className={tab === "shortlisted" ? "small-btn cand-primary-btn" : "small-btn"} disabled={!selectedJob} onClick={() => setTab("shortlisted")}>
                Shortlisted ({shortlisted.length})
              </button>
            </div>
          </div>
        </div>
      }
    >
      {!selectedJob ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Select a job to view matches.
          </p>
        </div>
      ) : (
        <div className="job-overview-grid" style={{ gridTemplateColumns: "320px 1fr" }}>
          <div className="job-card">
            <div className="job-card-title">Job Description</div>
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

          <div className="job-card job-card-wide">
            <div className="job-card-title">
              {tab === "pool"
                ? "Pool"
                : "Shortlisted"}
            </div>

            {tab === "pool" ? (
              loadingPool ? (
                <div className="muted">Loading…</div>
              ) : pool.length === 0 ? (
                <div className="muted">No candidates in pool yet (SBERT stage-1 cache empty).</div>
              ) : (
                <div className="job-table-wrap">
                  <table className="job-table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Title</th>
                        <th>Experience</th>
                        <th>Retrieval score</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pool.map((r) => (
                        <tr key={r.candidate_id}>
                          <td>{r.candidate_name || r.candidate_id}</td>
                          <td className="muted">{r.candidate_title || "—"}</td>
                          <td className="muted">{r.years_experience != null ? `${r.years_experience} Years` : "—"}</td>
                          <td style={{ color: "rgba(148, 163, 184, 0.95)", fontWeight: 700 }}>
                            {sbertPct((r as any).sbert_score)}
                          </td>
                          <td>
                            <button
                              type="button"
                              className="small-btn"
                              disabled={busyRefresh}
                              onClick={async () => {
                                try {
                                  const res = await updateJobShortlist(selectedJob, { add: [r.candidate_id] });
                                  setShortlisted(res.items || []);
                                  setPool((prev) => prev.map((x) => (x.candidate_id === r.candidate_id ? { ...x, is_shortlisted: true } : x)));
                                  toast.success("Added to shortlist.");
                                } catch (e) {
                                  toast.error((e as Error).message || "Failed to shortlist");
                                }
                              }}
                            >
                              {r.is_shortlisted ? "Shortlisted" : "Shortlist"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : (
              loadingShortlist ? (
                <div className="muted">Loading…</div>
              ) : shortlisted.length === 0 ? (
                <div className="muted">No shortlisted candidates yet. Add candidates from the pool.</div>
              ) : (
                <>
                  <div className="cand-toolbar-actions" style={{ marginBottom: 10 }}>
                    <button type="button" className="small-btn" disabled={busyRefresh || shortlisted.length === 0} onClick={() => void doRankShortlist()}>
                      {busyRefresh ? "Refreshing…" : "Refresh Matches (Cross‑Encoder)"}
                    </button>
                    <button
                      type="button"
                      className="small-btn"
                      disabled={loadingRankings || rankings.length === 0}
                      onClick={exportCsv}
                      style={{ marginLeft: "0.5rem" }}
                    >
                      Export Results
                    </button>
                  </div>
                  <div className="job-table-wrap">
                    <table className="job-table">
                      <thead>
                        <tr>
                          <th style={{ width: "8%" }}>Rank</th>
                          <th>Name</th>
                          <th>Title</th>
                          <th>Experience</th>
                          <th style={{ width: "14%" }}>Match</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shortlisted
                          .map((r) => {
                            const rr = rankings.find((x) => x.candidate_external_id === r.candidate_id);
                            return { r, rr };
                          })
                          .sort((a, b) => {
                            // If ranked, sort by cross-encoder score desc; else keep as-is.
                            const sa = a.rr?.cross_encoder_score ?? -1;
                            const sb = b.rr?.cross_encoder_score ?? -1;
                            return sb - sa;
                          })
                          .map(({ r, rr }, idx) => (
                          <tr key={r.candidate_id}>
                            <td className="muted">{rr ? rr.rank_position : idx + 1}</td>
                            <td>{r.candidate_name || r.candidate_id}</td>
                            <td className="muted">{r.candidate_title || "—"}</td>
                            <td className="muted">{r.years_experience != null ? `${r.years_experience} Years` : "—"}</td>
                            <td style={{ color: "rgba(56, 189, 248, 0.95)", fontWeight: 800 }}>
                              {rr ? pct(rr.cross_encoder_score) : "—"}
                            </td>
                            <td>
                              <div style={{ display: "flex", gap: "0.45rem", alignItems: "center", flexWrap: "wrap" }}>
                                <a className="job-link-btn" href={`/candidates/lookup/${encodeURIComponent(r.candidate_id)}`}>
                                  View Profile »
                                </a>
                                <button
                                  type="button"
                                  className="small-btn cand-bulk-danger"
                                  disabled={busyRefresh}
                                  onClick={async () => {
                                    try {
                                      const res = await updateJobShortlist(selectedJob, { remove: [r.candidate_id] });
                                      setShortlisted(res.items || []);
                                      setPool((prev) =>
                                        prev.map((x) => (x.candidate_id === r.candidate_id ? { ...x, is_shortlisted: false } : x)),
                                      );
                                      toast.success("Removed from shortlist.");
                                    } catch (e) {
                                      toast.error((e as Error).message || "Failed to remove");
                                    }
                                  }}
                                >
                                  Remove
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )
            )}

            {tab === "shortlisted" && sortedRows.length > 0 ? (
              <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                <div className="job-card-title" style={{ marginBottom: 6 }}>
                  Top Candidate Insight
                </div>
                <div className="muted" style={{ lineHeight: 1.55 }}>
                  {sortedRows[0].candidate_name || "Candidate"} is ranked #1 for {job?.title || selectedJob} with a match score of{" "}
                  {pct(sortedRows[0].cross_encoder_score)} based on the cross-encoder re-ranking of the SBERT shortlist.
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </DashFrame>
  );
}

