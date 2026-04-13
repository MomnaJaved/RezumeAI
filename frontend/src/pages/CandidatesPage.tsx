import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashFrame from "../DashFrame";
import {
  deleteCandidateByExternalId,
  fetchCandidates,
  fetchCandidatesScoreboard,
  type CandidateDto,
} from "../api";

export default function CandidatesPage() {
  const [rows, setRows] = useState<CandidateDto[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingScores, setLoadingScores] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<string>("all");
  const [exp, setExp] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [cert, setCert] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("score_desc");
  const [page, setPage] = useState(1);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setErr(null);
      setLoadingList(true);
      let listOk = false;
      try {
        const base = await fetchCandidates(500);
        if (cancelled) return;
        setRows(base);
        listOk = true;
      } catch (e) {
        if (!cancelled) {
          setErr((e as Error).message);
          setRows([]);
        }
      } finally {
        if (!cancelled) setLoadingList(false);
      }
      if (cancelled || !listOk) return;

      setLoadingScores(true);
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
          })
        );
      } catch {
        /* keep list; scores fall back to heuristic in scoreFor() */
      } finally {
        if (!cancelled) setLoadingScores(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
    const v = c.competition_score;
    if (v != null && !Number.isNaN(Number(v))) {
      return Math.max(0, Math.min(100, Math.round(Number(v))));
    }
    // Fallback if API omits scores (older server).
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

  async function handleDeleteCandidate(c: CandidateDto) {
    const label = (c.full_name || "").trim() || c.external_id;
    if (!window.confirm(`Delete candidate “${label}”? This cannot be undone.`)) return;
    setDeletingId(c.id);
    setErr(null);
    try {
      await deleteCandidateByExternalId(c.external_id);
      setRows((prev) => prev.filter((x) => x.id !== c.id));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDeletingId(null);
    }
  }

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
      title={
        <div className="cand-top">
          <div className="cand-count">
            Candidates: {loadingList ? "…" : filtered.length}
            {loadingScores ? (
              <span className="muted" style={{ fontWeight: 400, marginLeft: "0.5rem", fontSize: "0.85rem" }}>
                (updating scores…)
              </span>
            ) : null}
          </div>
          <div className="cand-search">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search candidates by name, skills, email…"
            />
          </div>
        </div>
      }
    >
      {err ? <p className="banner banner-error">{err}</p> : null}

      <div className="cand-filters">
        <span className="muted" style={{ alignSelf: "center" }}>
          Filter By:
        </span>
        <select value={cert} onChange={(e) => setCert(e.target.value)}>
          <option value="all">Certifications</option>
          <option value="yes">Has certifications</option>
          <option value="no">No certifications</option>
        </select>
        <select value={exp} onChange={(e) => setExp(e.target.value)}>
          <option value="all">Experience</option>
          <option value="<1">&lt; 1 year</option>
          <option value="1-3">1–3 years</option>
          <option value="3-5">3–5 years</option>
          <option value="5+">5+ years</option>
        </select>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          {roles.map((r) => (
            <option key={r} value={r}>
              {r === "all" ? "Roles" : r}
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "Status" : statusLabel(s)}
            </option>
          ))}
        </select>
        <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
          <option value="score_desc">Sort By (Score)</option>
          <option value="name_asc">Name (A–Z)</option>
          <option value="exp_desc">Experience (High→Low)</option>
          <option value="created_desc">Newest</option>
        </select>

        <div style={{ marginLeft: "auto", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <Link to="/upload" className="dash-btn">
            + Create Candidate
          </Link>
          <Link to="/ingest" className="dash-btn">
            Bulk Ingest
          </Link>
        </div>
      </div>

      {loadingList ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Loading candidates…
          </p>
        </div>
      ) : !err && rows.length === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No candidates in the database yet. <Link to="/upload">Upload a resume</Link> or use{" "}
            <Link to="/ingest">Ingest</Link>. If you already added some, the API may be using a different database
            (check <code className="muted">DATABASE_URL</code> in <code className="muted">.env</code>).
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No candidates match your filters. <Link to="/upload">Upload a resume</Link> or use{" "}
            <Link to="/ingest">Ingest</Link>.
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
                    title="Competition score: percentile rank vs other candidates on experience, skills, education & certs, combined with average resume–job match across all open jobs."
                  >
                    Score
                  </th>
                  <th style={{ width: "11%" }}>Experience</th>
                  <th style={{ width: "10%" }}>Status</th>
                  <th style={{ width: "10%", textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((c) => {
                  const sc = scoreFor(c);
                  const st = (c.status || "new").toLowerCase();
                  return (
                    <tr key={c.id}>
                      <td>
                        <div className="cand-namecell">
                          <div className="cand-avatar" aria-hidden="true">
                            {initials(c.full_name || c.external_id)}
                          </div>
                          <div className="cand-name-meta">
                            <div className="cand-name">{c.full_name || "—"}</div>
                            <div className="cand-sub">
                              {c.filename ? (
                                <a
                                  href={`/api/v1/candidates/by-external/${encodeURIComponent(c.external_id)}/file`}
                                  target="_blank"
                                  rel="noreferrer"
                                  title="Open uploaded resume"
                                >
                                  View resume
                                </a>
                              ) : (
                                c.external_id
                              )}
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
                      <td style={{ textAlign: "right", verticalAlign: "middle" }}>
                        <button
                          type="button"
                          className="cand-delete-btn"
                          disabled={deletingId === c.id}
                          title="Remove candidate from database"
                          onClick={() => void handleDeleteCandidate(c)}
                        >
                          {deletingId === c.id ? "…" : "Delete"}
                        </button>
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
    </DashFrame>
  );
}

