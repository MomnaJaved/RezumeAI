import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import ConfirmDialog from "../components/ConfirmDialog";
import DashFrame from "../DashFrame";
import ResumePreviewModal from "../components/ResumePreviewModal";
import { candidateAvatarInitials, candidateDisplayName } from "../candidateDisplayName";
import { formatCandidateExperience } from "../experienceDisplay";
import {
  deleteCandidateByExternalId,
  fetchCandidatesPage,
  normalizedBestJobMatchPercent,
  type CandidateDto,
} from "../api";
import { useToast } from "../toast";
import { getCandidatesPerPage, getDefaultCandidateSortKey } from "../settings";

function displayRoleLabel(key: string): string {
  const k = (key || "").trim().toLowerCase();
  if (!k) return "—";
  if (k === "hr") return "HR";
  if (k === "qa") return "QA";
  if (k === "devops") return "DevOps";
  return k[0].toUpperCase() + k.slice(1);
}

function escapeCsvCell(v: string): string {
  const s = String(v ?? "").replace(/"/g, '""');
  if (/[",\r\n]/.test(s)) return `"${s}"`;
  return s;
}

function exportCandidatesToExcelCsv(candidates: CandidateDto[]): void {
  const headers = [
    "Name",
    "External ID",
    "Title",
    "Role",
    "Fine role",
    "Email",
    "Years experience",
    "Status",
    "Skills",
    "Filename",
    "Created",
  ];
  const lines = [
    headers.join(","),
    ...candidates.map((c) =>
      [
        escapeCsvCell(candidateDisplayName(c)),
        escapeCsvCell(c.external_id),
        escapeCsvCell(c.title),
        escapeCsvCell(c.role_label),
        escapeCsvCell(c.role_fine ?? ""),
        escapeCsvCell(c.contact_email ?? ""),
        c.years_experience != null ? String(c.years_experience) : "",
        escapeCsvCell(c.status ?? ""),
        escapeCsvCell(c.skills),
        escapeCsvCell(c.filename),
        escapeCsvCell(c.created_at ?? ""),
      ].join(","),
    ),
  ];
  const bom = "\uFEFF";
  const csv = bom + lines.join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const stamp = new Date().toISOString().slice(0, 10);
  a.href = url;
  a.download = `candidates_export_${stamp}.csv`;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function CandidatesPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const [rows, setRows] = useState<CandidateDto[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [listFetchFailed, setListFetchFailed] = useState(false);
  const [q, setQ] = useState("");
  const [role, setRole] = useState<string>("all");
  const [exp, setExp] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [cert, setCert] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>(() => getDefaultCandidateSortKey());
  const [page, setPage] = useState(1);
  const [resumePreview, setResumePreview] = useState<{ externalId: string; filename?: string } | null>(null);
  const closeResumePreview = useCallback(() => setResumePreview(null), []);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [selectionMode, setSelectionMode] = useState(false);

  useEffect(() => {
    if (!selectionMode) {
      setSelectedIds(new Set());
      setBulkDeleteOpen(false);
    }
  }, [selectionMode]);

  useEffect(() => {
    const st = searchParams.get("status");
    if (st != null && st.trim() !== "") setStatus(st.trim());
    const sort = searchParams.get("sort");
    if (sort === "name_asc" || sort === "exp_desc" || sort === "created_desc" || sort === "score_desc") {
      setSortBy(sort);
    }
  }, [searchParams]);

  const pageSize = getCandidatesPerPage();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setListFetchFailed(false);
      setLoadingList(true);
      try {
        const res = await fetchCandidatesPage({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          q: q.trim() || undefined,
          status: status !== "all" ? status : undefined,
          role: role !== "all" ? role : undefined,
          sort: sortBy,
        });
        if (cancelled) return;
        setRows(res.items);
        setTotal(res.total);
      } catch (e) {
        if (!cancelled) {
          setListFetchFailed(true);
          setRows([]);
          setTotal(0);
          toast.error((e as Error).message);
        }
      } finally {
        if (!cancelled) setLoadingList(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast, page, q, status, role, sortBy]);

  const roles = useMemo(() => {
    // Keep aligned with backend `src/parsing/role_labels.py` (ROLE_LABELS_MULTI).
    const base = [
      "frontend",
      "backend",
      "fullstack",
      "devops",
      "qa",
      "data",
      "design",
      "product",
      "marketing",
      "hr",
      "operations",
      "other",
    ];
    const s = new Set<string>(base);
    for (const r of rows) {
      const raw = (r.role_label || "").trim().toLowerCase();
      if (raw) s.add(raw);
    }
    const extras = Array.from(s)
      .filter((x) => !base.includes(x))
      .sort((a, b) => a.localeCompare(b));
    return ["all", ...base, ...extras];
  }, [rows]);

  const statuses = useMemo(() => {
    // Canonical 7-value pipeline stages — always present in the filter dropdown.
    const base = ["new", "screened", "shortlisted", "interviewing", "selected", "hired", "rejected"];
    const s = new Set<string>(base);
    for (const r of rows) {
      const raw = (r.status || "new").trim();
      if (raw) s.add(raw);
    }
    // Prefer showing pipeline stages first, then any extra raw statuses from DB (legacy data).
    const extras = Array.from(s)
      .filter((x) => !base.includes(x))
      .sort((a, b) => a.localeCompare(b));
    return ["all", ...base, ...extras];
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

  function bestMatchFor(c: CandidateDto): number | null {
    return normalizedBestJobMatchPercent(c.best_job_match_score);
  }

  function bestJobOneLiner(c: CandidateDto): string | null {
    const title = (c.best_job_title || "").trim();
    const dept = (c.best_job_department || "").trim();
    const client = (c.best_job_client_name || c.best_job_client_company || "").trim();
    if (!title && !client) return null;
    const jobPart = [title, dept].filter(Boolean).join(" · ");
    if (jobPart && client) return `${jobPart} · ${client}`;
    return jobPart || `Hiring: ${client}`;
  }

  const filtered = useMemo(() => {
    // Server already filtered/sorted; keep only lightweight local toggles.
    const out = rows.filter((c) => {
      if (cert === "yes" && !(c.certifications || "").trim()) return false;
      if (cert === "no" && (c.certifications || "").trim()) return false;
      if (exp !== "all") {
        const b = expBucket(c.years_experience);
        if (b !== exp) return false;
      }
      return true;
    });
    return out;
  }, [rows, cert, exp]);

  const filteredIdsKey = useMemo(() => filtered.map((c) => c.id).join("\n"), [filtered]);

  useEffect(() => {
    const allowed = new Set(filtered.map((c) => c.id));
    setSelectedIds((prev) => {
      let changed = false;
      const next = new Set<string>();
      for (const id of prev) {
        if (allowed.has(id)) next.add(id);
        else changed = true;
      }
      if (!changed && next.size === prev.size) return prev;
      return next;
    });
  }, [filteredIdsKey]);

  const selectedOnFiltered = useMemo(
    () => filtered.filter((c) => selectedIds.has(c.id)),
    [filtered, selectedIds],
  );

  const allFilteredSelected = filtered.length > 0 && selectedOnFiltered.length === filtered.length;

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAllFiltered = useCallback(() => {
    setSelectedIds((prev) => {
      if (filtered.length === 0) return new Set();
      const every = filtered.every((c) => prev.has(c.id));
      if (every) return new Set();
      return new Set(filtered.map((c) => c.id));
    });
  }, [filtered]);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const exportSelectionCsv = useCallback(() => {
    if (selectedOnFiltered.length === 0) return;
    exportCandidatesToExcelCsv(selectedOnFiltered);
    toast.success(`Exported ${selectedOnFiltered.length} row${selectedOnFiltered.length === 1 ? "" : "s"} (CSV for Excel).`);
  }, [selectedOnFiltered, toast]);

  const runBulkDelete = useCallback(async () => {
    const list = selectedOnFiltered;
    if (list.length === 0) return;
    setBulkBusy(true);
    const results = await Promise.allSettled(list.map((c) => deleteCandidateByExternalId(c.external_id)));
    const removedExt = new Set<string>();
    const failedNames: string[] = [];
    list.forEach((c, i) => {
      const r = results[i];
      if (r.status === "fulfilled") removedExt.add(c.external_id);
      else failedNames.push(candidateDisplayName(c));
    });
    setRows((prev) => prev.filter((c) => !removedExt.has(c.external_id)));
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const c of list) {
        if (removedExt.has(c.external_id)) next.delete(c.id);
      }
      return next;
    });
    setBulkBusy(false);
    setBulkDeleteOpen(false);
    if (removedExt.size) toast.success(`Removed ${removedExt.size} candidate${removedExt.size === 1 ? "" : "s"}.`);
    if (failedNames.length) {
      toast.error(
        failedNames.length === 1
          ? `Could not remove ${failedNames[0]}.`
          : `Could not remove ${failedNames.length} candidates (${failedNames.slice(0, 3).join(", ")}${failedNames.length > 3 ? "…" : ""}).`,
      );
    }
  }, [selectedOnFiltered, toast]);

  useEffect(() => {
    if (bulkDeleteOpen && selectedOnFiltered.length === 0) setBulkDeleteOpen(false);
  }, [bulkDeleteOpen, selectedOnFiltered.length]);

  useEffect(() => {
    setPage(1);
  }, [q, role, exp, status, cert, sortBy]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const pageRows = filtered;

  function statusLabel(s: string | undefined): string {
    const v = (s || "new").trim();
    return v ? v[0].toUpperCase() + v.slice(1) : "New";
  }

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Candidates: {loadingList ? "…" : total}</div>
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
                  {r === "all" ? "Roles" : displayRoleLabel(r)}
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
      ) : total === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No candidates match your filters. <Link to="/upload">Upload resumes</Link> from the toolbar (+).
          </p>
        </div>
      ) : (
        <>
          {selectionMode && selectedIds.size > 0 ? (
            <div className="cand-bulk-bar" role="region" aria-label="Bulk actions">
              <span className="cand-bulk-summary">
                {selectedIds.size} selected
                {allFilteredSelected && filtered.length > pageRows.length ? (
                  <span className="muted"> (all {filtered.length} matching filters)</span>
                ) : null}
              </span>
              <div className="cand-bulk-actions">
                <button type="button" className="small-btn cand-bulk-ghost" disabled title="Coming soon">
                  Assign…
                </button>
                <button type="button" className="small-btn cand-bulk-ghost" disabled title="Coming soon">
                  Move…
                </button>
                {selectedOnFiltered.length >= 2 && selectedOnFiltered.length <= 6 ? (
                  <button
                    type="button"
                    className="small-btn cand-bulk-compare"
                    onClick={() =>
                      navigate(`/candidates/compare?ids=${selectedOnFiltered.map((x) => x.id).join(",")}`)
                    }
                    title="Open side-by-side comparison for selected candidates"
                  >
                    Compare…
                  </button>
                ) : null}
                <button type="button" className="small-btn" onClick={exportSelectionCsv} title="Download selected rows as CSV (opens in Excel)">
                  Export to Excel…
                </button>
                <button type="button" className="small-btn cand-bulk-danger" onClick={() => setBulkDeleteOpen(true)}>
                  Delete selected…
                </button>
              </div>
            </div>
          ) : null}

          <div className="cand-table-toolbar">
            <span className="cand-table-toolbar-meta muted">
              {filtered.length} in view
              {totalPages > 1 ? ` · Page ${page} of ${totalPages}` : null}
            </span>
            <div className="cand-table-toolbar-actions">
              {!selectionMode ? (
                <button
                  type="button"
                  className="cand-table-toolbar-select"
                  onClick={() => setSelectionMode(true)}
                  title="Show checkboxes and bulk actions"
                >
                  Select
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    className="cand-table-toolbar-action cand-table-toolbar-done"
                    onClick={() => setSelectionMode(false)}
                    title="Hide checkboxes and clear selection"
                  >
                    Done
                  </button>
                  {selectedIds.size > 0 ? (
                    <button type="button" className="cand-table-toolbar-action" onClick={clearSelection} title="Clear all checkboxes">
                      Clear all
                    </button>
                  ) : null}
                  {!allFilteredSelected && filtered.length > 0 ? (
                    <button
                      type="button"
                      className="cand-table-toolbar-action"
                      onClick={toggleSelectAllFiltered}
                      title={`Select all ${filtered.length} matching current filters`}
                    >
                      Select all
                    </button>
                  ) : null}
                </>
              )}
            </div>
          </div>

          <div className="cand-table-wrap">
            <table className="cand-table">
              <thead>
                <tr>
                  {selectionMode ? <th className="cand-col-select cand-col-select--head" aria-hidden="true" /> : null}
                  <th style={{ width: selectionMode ? "36%" : "40%" }}>Name</th>
                  <th style={{ width: "18%" }}>Role</th>
                  <th
                    style={{ width: "11%" }}
                    title="Best saved cross-encoder match vs a job (0–100). Only shown after you run matching / ranking and save scores."
                  >
                    Match
                  </th>
                  <th style={{ width: "14%" }}>Experience</th>
                  <th style={{ width: "12%" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((c) => {
                  const m = bestMatchFor(c);
                  const st = (c.status || "new").toLowerCase();
                  const isSel = selectionMode && selectedIds.has(c.id);
                  return (
                    <tr
                      key={c.id}
                      className={`cand-row-nav${isSel ? " cand-row-nav--selected" : ""}`}
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
                      {selectionMode ? (
                        <td
                          className="cand-col-select"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          <label className="cand-checkbox">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(c.id)}
                              onChange={() => toggleSelect(c.id)}
                              aria-label={`Select ${candidateDisplayName(c)}`}
                            />
                            <span className="cand-checkbox-ui" aria-hidden />
                          </label>
                        </td>
                      ) : null}
                      <td>
                        <div className="cand-namecell">
                          <div className="cand-avatar" aria-hidden="true">
                            {candidateAvatarInitials(c)}
                          </div>
                          <div className="cand-name-meta">
                            <div className="cand-name">{candidateDisplayName(c)}</div>
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
                            {(() => {
                              const line = bestJobOneLiner(c);
                              return line ? <div className="muted cand-bestjob-line">{line}</div> : null;
                            })()}
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
                        className={
                          m != null
                            ? m >= 80
                              ? "cand-score good"
                              : m >= 65
                                ? "cand-score mid"
                                : "cand-score low"
                            : "cand-score"
                        }
                        title={
                          m != null
                            ? "Best saved job match (cross-encoder)."
                            : "No saved job match yet. Run Matching to store a real score."
                        }
                      >
                        {m != null ? `${m}%` : "—"}
                      </td>
                      <td>{formatCandidateExperience(c)}</td>
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

      <ConfirmDialog
        open={bulkDeleteOpen}
        title="Delete selected candidates"
        message={`Remove ${selectedOnFiltered.length} candidate${selectedOnFiltered.length === 1 ? "" : "s"} from your pool? This cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        busy={bulkBusy}
        onClose={() => !bulkBusy && setBulkDeleteOpen(false)}
        onConfirm={() => void runBulkDelete()}
      />
    </DashFrame>
  );
}

