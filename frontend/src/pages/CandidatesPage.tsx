import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import DashFrame from "../DashFrame";
import ResumePreviewModal from "../components/ResumePreviewModal";
import { candidateListProfileScore } from "../candidateListScore";
import { fetchCandidates, fetchCandidatesScoreboard, type CandidateDto } from "../api";
import { useToast } from "../toast";

export default function CandidatesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [rows, setRows] = useState<CandidateDto[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listFetchFailed, setListFetchFailed] = useState(false);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<string>("all");
  const [exp, setExp] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [cert, setCert] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("score_desc");
  const [page, setPage] = useState(1);
  const [resumePreview, setResumePreview] = useState<{ externalId: string; filename?: string } | null>(null);
  const closeResumePreview = useCallback(() => setResumePreview(null), []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setListFetchFailed(false);
      setLoadingList(true);
      let listOk = false;
      try {
        const base = await fetchCandidates(500);
        if (cancelled) return;
        setRows(base);
        listOk = true;
      } catch (e) {
        if (!cancelled) {
          setListFetchFailed(true);
          setRows([]);
          toast.error((e as Error).message);
        }
      } finally {
        if (!cancelled) setLoadingList(false);
      }
      if (cancelled || !listOk) return;

      try {
        const scored = await fetchCandidatesScoreboard(500);
        if (cancelled) return;
        const byId = new Map(scored.map((c) => [c.id, c]));
        setRows((prev) =>
          prev.map((row) => {
            const s = byId.get(row.id);
            if (!s) return row;
            return {
              ...row,
              profile_percentile_score: s.profile_percentile_score,
              avg_job_match_score: s.avg_job_match_score,
              competition_score: s.competition_score,
            };
          }),
        );
      } catch {
        /* keep list; candidateListProfileScore uses heuristic until scores load */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast]);

  const roles = useMemo(() => {
    const s = new Set(rows.map((r) => (r.role_label || "").trim()).filter(Boolean));
    return ["all", ...Array.from(s).sort((a, b) => a.localeCompare(b))];
  }, [rows]);

  const statuses = useMemo(() => {
    const s = new Set(rows.map((r) => (r.status || "new").trim()).filter(Boolean));
    return ["all", ...Array.from(s).sort((a, b) => a.localeCompare(b))];
  }, [rows]);

  function displayRoleFine(v: string | undefined): string {
    const x = (v || "").trim().toLowerCase();
    if (x === "intern" || x === "mobile") return "software";
    return (v || "").trim();
  }

  function expBucket(y: number | null | undefined): string {
    const v = y ?? 0;
    if (v < 1) return "<1";
    if (v < 3) return "1-3";
    if (v < 5) return "3-5";
    return "5+";
  }

  function scoreFor(c: CandidateDto): number {
    return candidateListProfileScore(c);
  }

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const out = rows.filter((c) => {
      const st = (c.status || "new").toLowerCase();
      if (role !== "all" && (c.role_label || "").toLowerCase() !== role.toLowerCase()) return false;
      if (status !== "all" && st !== status.toLowerCase()) return false;
      if (cert === "yes" && !(c.certifications || "").trim()) return false;
      if (cert === "no" && (c.certifications || "").trim()) return false;
      if (exp !== "all") {
        const b = expBucket(c.years_experience);
        if (b !== exp) return false;
      }
      if (!needle) return true;
      const hay = `${c.full_name} ${c.title} ${c.role_label} ${c.skills} ${c.filename}`.toLowerCase();
      return hay.includes(needle);
    });

    const sorted = [...out].sort((a, b) => {
      if (sortBy === "name_asc") return (a.full_name || "").localeCompare(b.full_name || "");
      if (sortBy === "exp_desc") return (b.years_experience ?? -1) - (a.years_experience ?? -1);
      if (sortBy === "created_desc") return (b.created_at || "").localeCompare(a.created_at || "");
      // default: score desc
      return scoreFor(b) - scoreFor(a);
    });
    return sorted;
  }, [rows, q, role, exp, status, cert, sortBy]);

  useEffect(() => {
    setPage(1);
  }, [q, role, exp, status, cert, sortBy]);

  const pageSize = 10;
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  function initials(name: string): string {
    const parts = name
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (parts.length === 0) return "?";
    const a = parts[0]?.[0] ?? "";
    const b = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
    return (a + b).toUpperCase();
  }

  function statusLabel(s: string | undefined): string {
    const v = (s || "new").trim();
    return v ? v[0].toUpperCase() + v.slice(1) : "New";
  }

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Candidates: {loadingList ? "…" : filtered.length}</div>
            <div className="cand-search">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search candidates by name, skills, email…"
              />
            </div>
            <Link
              to="/candidates/add"
              className="cand-add-btn"
              title="Add candidates from files or pasted text"
              aria-label="Add candidates from files or pasted text"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
            </Link>
          </div>
          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">Filter by</span>
            <select value={cert} onChange={(e) => setCert(e.target.value)} aria-label="Certifications filter">
              <option value="all">Certifications</option>
              <option value="yes">Has certifications</option>
              <option value="no">No certifications</option>
            </select>
            <select value={exp} onChange={(e) => setExp(e.target.value)} aria-label="Experience filter">
              <option value="all">Experience</option>
              <option value="<1">&lt; 1 year</option>
              <option value="1-3">1–3 years</option>
              <option value="3-5">3–5 years</option>
              <option value="5+">5+ years</option>
            </select>
            <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role filter">
              {roles.map((r) => (
                <option key={r} value={r}>
                  {r === "all" ? "Roles" : r}
                </option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {s === "all" ? "Status" : statusLabel(s)}
                </option>
              ))}
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sort order">
              <option value="score_desc">Sort by (score)</option>
              <option value="name_asc">Name (A–Z)</option>
              <option value="exp_desc">Experience (high→low)</option>
              <option value="created_desc">Newest</option>
            </select>
          </div>
        </div>
      }
    >
      {loadingList ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Loading candidates…
          </p>
        </div>
      ) : listFetchFailed ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Could not load the candidate list. Check your connection and try again.
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No candidates yet. Use <Link to="/candidates/add">Add candidate</Link> to upload résumés.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No candidates match your filters. <Link to="/upload">Upload resumes</Link> from the toolbar (+).
          </p>
        </div>
      ) : (
        <>
          <div className="cand-table-wrap">
            <table className="cand-table">
              <thead>
                <tr>
                  <th style={{ width: "40%" }}>Name</th>
                  <th style={{ width: "18%" }}>Role</th>
                  <th
                    style={{ width: "11%" }}
                    title="Profile strength vs your candidate pool (same as dashboard candidate summary). Job-specific match % appears when ranking against a job."
                  >
                    Score
                  </th>
                  <th style={{ width: "14%" }}>Experience</th>
                  <th style={{ width: "12%" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((c) => {
                  const sc = scoreFor(c);
                  const st = (c.status || "new").toLowerCase();
                  return (
                    <tr
                      key={c.id}
                      className="cand-row-nav"
                      tabIndex={0}
                      role="link"
                      title="Open candidate profile"
                      onClick={() => navigate(`/candidates/${c.id}`)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          navigate(`/candidates/${c.id}`);
                        }
                      }}
                    >
                      <td>
                        <div className="cand-namecell">
                          <div className="cand-avatar" aria-hidden="true">
                            {initials(c.full_name || c.external_id)}
                          </div>
                          <div className="cand-name-meta">
                            <div className="cand-name">{c.full_name || "—"}</div>
                            <div className="cand-sub">
                              <button
                                type="button"
                                className="cand-view-resume"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setResumePreview({ externalId: c.external_id, filename: c.filename });
                                }}
                              >
                                View resume
                              </button>
                            </div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 700, color: "rgba(255,255,255,0.92)" }}>{c.title || "—"}</div>
                        {(c.role_fine || "").trim() && (c.role_fine || "").trim().toLowerCase() !== "unknown" ? (
                          <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.15rem" }}>
                            {displayRoleFine(c.role_fine)}
                          </div>
                        ) : null}
                      </td>
                      <td
                        className={sc >= 80 ? "cand-score good" : sc >= 65 ? "cand-score mid" : "cand-score low"}
                        title={
                          c.profile_percentile_score != null
                            ? (c.avg_job_match_score ?? 0) > 0
                              ? `Profile (cohort): ${Math.round(c.profile_percentile_score)} · Avg job match (all jobs): ${Math.round(Number(c.avg_job_match_score))}`
                              : `Profile (cohort): ${Math.round(c.profile_percentile_score)}`
                            : undefined
                        }
                      >
                        {sc}%
                      </td>
                      <td>{c.years_experience !== null && c.years_experience !== undefined ? `${c.years_experience} Years` : "—"}</td>
                      <td>
                        <span className={`cand-status ${st}`}>{statusLabel(c.status)}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="cand-pager">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              « Previous
            </button>
            <div className="cand-pages">
              {Array.from({ length: Math.min(totalPages, 7) }).map((_, i) => {
                const p = i + 1;
                return (
                  <button
                    type="button"
                    key={p}
                    className={p === page ? "primary" : ""}
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </button>
                );
              })}
              {totalPages > 7 ? <span className="muted">…</span> : null}
              {totalPages > 7 ? (
                <button type="button" className={page === totalPages ? "primary" : ""} onClick={() => setPage(totalPages)}>
                  {totalPages}
                </button>
              ) : null}
            </div>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next »
            </button>
          </div>
        </>
      )}

      <ResumePreviewModal
        open={resumePreview !== null}
        externalId={resumePreview?.externalId ?? ""}
        filename={resumePreview?.filename}
        onClose={closeResumePreview}
      />
    </DashFrame>
  );
}

