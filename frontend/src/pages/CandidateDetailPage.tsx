import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import DashFrame from "../DashFrame";
import ConfirmDialog from "../components/ConfirmDialog";
import ResumePreviewModal from "../components/ResumePreviewModal";
import { useToast } from "../toast";
import { candidateAvatarInitials, candidateDisplayName, candidateMailtoSubjectLine } from "../candidateDisplayName";
import { formatCandidateExperience } from "../experienceDisplay";
import {
  deleteCandidateByExternalId,
  fetchCandidate,
  fetchCandidateFileBlob,
  fetchCandidateJobEvaluations,
  fetchCandidateWithScores,
  updateCandidate,
  normalizedBestJobMatchPercent,
  type CandidateDto,
  type CandidateJobEvaluationRow,
  type CandidateUpdatePayload,
} from "../api";

function displayRoleFine(v: string | undefined): string {
  const x = (v || "").trim().toLowerCase();
  if (x === "intern" || x === "mobile") return "software";
  return (v || "").trim();
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

function scoreClass(sc: number): string {
  if (sc >= 80) return "cand-score good";
  if (sc >= 65) return "cand-score mid";
  return "cand-score low";
}

function bestMatchScore(c: CandidateDto): number | null {
  return normalizedBestJobMatchPercent(c.best_job_match_score);
}

function IconBtn({
  title,
  onClick,
  children,
  disabled,
}: {
  title: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="cand-detail-toolbtn"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

const svgProps = {
  width: "100%" as const,
  height: "100%" as const,
  viewBox: "0 0 24 24",
  fill: "none" as const,
  stroke: "currentColor" as const,
  strokeWidth: 1.8,
  "aria-hidden": true as const,
};

function buildDraft(row: CandidateDto): CandidateUpdatePayload {
  return {
    full_name: row.full_name,
    title: row.title,
    role_label: row.role_label,
    role_fine: row.role_fine,
    skills: row.skills,
    years_experience: row.years_experience,
    highest_degree: row.highest_degree,
    certifications: row.certifications ?? "",
    education_lines: row.education_lines ?? "",
    status: row.status,
    contact_email: row.contact_email ?? "",
  };
}

/** Full PATCH body so JSON never omits `skills` / `certifications` (undefined keys are stripped by stringify). */
function buildSavePayload(d: CandidateUpdatePayload): CandidateUpdatePayload {
  return {
    full_name: d.full_name ?? "",
    title: d.title ?? "",
    role_label: d.role_label ?? "",
    role_fine: (d.role_fine ?? "unknown").trim() || "unknown",
    skills: d.skills ?? "",
    years_experience: d.years_experience ?? null,
    highest_degree: d.highest_degree ?? "",
    certifications: d.certifications ?? "",
    education_lines: d.education_lines ?? "",
    status: d.status ?? "new",
    contact_email: d.contact_email ?? "",
  };
}

function safeDownloadName(filename: string | undefined, externalId: string): string {
  const base = (filename || `${externalId}.bin`).trim() || "resume";
  return base.replace(/[/\\?%*:|"<>]/g, "_");
}

function splitPipeFields(text: string | undefined): string[] {
  if (!text?.trim()) return [];
  return text
    .split("|")
    .map((s) => s.trim())
    .filter(Boolean);
}

function pipeToMultiline(text: string | undefined): string {
  return splitPipeFields(text).join("\n");
}

function multilineToPipe(text: string): string {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean)
    .join(" | ");
}

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "new", label: "New" },
  { value: "screened", label: "Screened" },
  { value: "shortlisted", label: "Shortlisted" },
  { value: "interviewing", label: "Interviewing" },
  { value: "selected", label: "Selected" },
  { value: "hired", label: "Hired" },
  { value: "rejected", label: "Rejected" },
];

function PipeFieldList({ text }: { text: string | undefined }) {
  const items = splitPipeFields(text);
  if (!items.length) return <p className="cand-detail-body">—</p>;
  return (
    <ul className="cand-detail-pipe-list">
      {items.map((line, i) => (
        <li key={`${i}-${line.slice(0, 48)}`}>{line}</li>
      ))}
    </ul>
  );
}

function CandidateHeroToolbar({
  canUseResume,
  deleting,
  editOpen,
  onToggleEdit,
  onPreview,
  onDownload,
  onMessage,
  onDelete,
}: {
  canUseResume: boolean;
  deleting: boolean;
  editOpen: boolean;
  onToggleEdit: () => void;
  onPreview: () => void;
  onDownload: () => void;
  onMessage: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="cand-detail-toolbar" role="toolbar" aria-label="Candidate actions">
      <IconBtn title="Preview resume" disabled={!canUseResume} onClick={onPreview}>
        <svg {...svgProps}>
          <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </IconBtn>
      <IconBtn title="Download resume file" disabled={!canUseResume} onClick={onDownload}>
        <svg {...svgProps}>
          <path d="M12 3v12" strokeLinecap="round" />
          <path d="M8 11l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M5 21h14" strokeLinecap="round" />
        </svg>
      </IconBtn>
      <IconBtn title="Draft email (adds contact email to To when known)" onClick={onMessage}>
        <svg {...svgProps}>
          <rect x="3" y="5" width="18" height="14" rx="2" strokeLinejoin="round" />
          <path d="M3 7l9 6 9-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </IconBtn>
      <IconBtn title={editOpen ? "Close editor" : "Edit profile fields"} onClick={onToggleEdit}>
        <svg {...svgProps}>
          <path d="M12 20h9" strokeLinecap="round" />
          <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4 11.5-11.5z" strokeLinejoin="round" />
        </svg>
      </IconBtn>
      <IconBtn title="Delete candidate from database" disabled={deleting} onClick={onDelete}>
        <svg {...svgProps}>
          <path d="M3 6h18" strokeLinecap="round" />
          <path d="M8 6V4h8v2" strokeLinecap="round" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" strokeLinejoin="round" />
          <path d="M10 11v6M14 11v6" strokeLinecap="round" />
        </svg>
      </IconBtn>
    </div>
  );
}

export default function CandidateDetailPage() {
  const { candidateId = "" } = useParams<{ candidateId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [c, setC] = useState<CandidateDto | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [draft, setDraft] = useState<CandidateUpdatePayload>({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [jobEvals, setJobEvals] = useState<CandidateJobEvaluationRow[]>([]);
  const editOpenRef = useRef(false);
  const cRef = useRef<CandidateDto | null>(null);
  const editFormRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    editOpenRef.current = editOpen;
  }, [editOpen]);

  useEffect(() => {
    cRef.current = c;
  }, [c]);

  useLayoutEffect(() => {
    if (!editOpen) return;
    editFormRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [editOpen]);

  const closeResumePreview = useCallback(() => setPreviewOpen(false), []);

  const load = useCallback(async () => {
    if (!candidateId) return;
    setLoading(true);
    try {
      const quick = await fetchCandidate(candidateId);
      setC(quick);
      setDraft(buildDraft(quick));
    } catch (e) {
      toast.error((e as Error).message);
      setC(null);
      setLoading(false);
      return;
    } finally {
      setLoading(false);
    }

    fetchCandidateWithScores(candidateId)
      .then((full) => {
        setC((cur) => {
          if (!cur) return full;
          if (editOpenRef.current) {
            return {
              ...cur,
              profile_percentile_score: full.profile_percentile_score,
              avg_job_match_score: full.avg_job_match_score,
              competition_score: full.competition_score,
              best_job_match_score: full.best_job_match_score ?? cur.best_job_match_score,
              best_job_external_id: full.best_job_external_id ?? cur.best_job_external_id,
              best_job_title: full.best_job_title ?? cur.best_job_title,
              best_job_department: full.best_job_department ?? cur.best_job_department,
              best_job_client_name: full.best_job_client_name ?? cur.best_job_client_name,
              best_job_client_company: full.best_job_client_company ?? cur.best_job_client_company,
              best_job_client_contact: full.best_job_client_contact ?? cur.best_job_client_contact,
              best_job_client_email: full.best_job_client_email ?? cur.best_job_client_email,
              status_effective: full.status_effective ?? cur.status_effective,
              skills_role_hint: full.skills_role_hint ?? cur.skills_role_hint,
            };
          }
          return full;
        });
        setDraft((d) => (editOpenRef.current ? d : buildDraft(full)));
      })
      .catch(() => {
        /* keep quick row; score chip uses heuristic */
      });
  }, [candidateId, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!c?.id) {
      setJobEvals([]);
      return;
    }
    let cancelled = false;
    fetchCandidateJobEvaluations(c.id)
      .then((res) => {
        if (!cancelled) setJobEvals(res.items || []);
      })
      .catch(() => {
        if (!cancelled) setJobEvals([]);
      });
    return () => {
      cancelled = true;
    };
  }, [c?.id]);

  function scoreFor(row: CandidateDto): number {
    const bm = bestMatchScore(row);
    return bm ?? 0;
  }

  function onMessage() {
    if (!c) return;
    const subject = candidateMailtoSubjectLine(c);
    const params = new URLSearchParams({ subject });
    const to = (c.contact_email || "").trim();
    window.location.href = to ? `mailto:${to}?${params}` : `mailto:?${params}`;
  }

  async function onDownloadResume() {
    if (!c) return;
    try {
      const { blob } = await fetchCandidateFileBlob(c.external_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = safeDownloadName(c.filename, c.external_id);
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
    } catch (e) {
      toast.error((e as Error).message || "Could not download file.");
    }
  }

  function requestDelete() {
    if (!c || deleting) return;
    setDeleteConfirmOpen(true);
  }

  async function performDelete() {
    if (!c) return;
    const label = candidateDisplayName(c);
    setDeleteConfirmOpen(false);
    setDeleting(true);
    try {
      await deleteCandidateByExternalId(c.external_id);
      toast.success(`${label} has been deleted`);
      navigate("/candidates", { replace: true });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  async function onSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!c) return;
    setSaving(true);
    try {
      const next = await updateCandidate(c.id, buildSavePayload(draft));
      setC({
        ...next,
        competition_score: c.competition_score,
        profile_percentile_score: c.profile_percentile_score,
        avg_job_match_score: c.avg_job_match_score,
      });
      setEditOpen(false);
      toast.success("Saved.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const bm = c ? bestMatchScore(c) : null;
  const sc = c ? scoreFor(c) : 0;
  const st = ((c?.status_effective || c?.status || "new") as string).toLowerCase();
  const canUseResume = Boolean(c?.external_id);

  return (
    <DashFrame
      topExtra={
        <div className="cand-detail-breadcrumb">
          <Link to="/candidates" className="dash-widget-link">
            ← Candidates
          </Link>
        </div>
      }
    >
      {loading ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Loading candidate…
          </p>
        </div>
      ) : !c ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Candidate not found. <Link to="/candidates">Back to list</Link>
          </p>
        </div>
      ) : (
        <>
          {editOpen ? (
            <form
              ref={editFormRef}
              className="cand-detail-edit-wrap"
              onSubmit={(e) => void onSaveEdit(e)}
            >
              <p className="cand-detail-edit-banner" role="status">
                Editing profile — fields below are editable. Save or cancel when done.
              </p>
              <div className="cand-detail-hero">
                <div className="cand-detail-hero-main">
                  <div className="cand-detail-avatar" aria-hidden="true">
                    {initials((draft.full_name || "").trim() || candidateDisplayName(c))}
                  </div>
                  <div className="cand-detail-hero-text">
                    <input
                      className="cand-detail-name-input"
                      aria-label="Full name"
                      value={draft.full_name ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, full_name: e.target.value }))}
                    />
                    <input
                      className="cand-detail-headline-input"
                      aria-label="Title"
                      value={draft.title ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
                    />
                    <input
                      className="cand-detail-rolefine-input muted"
                      aria-label="Role fine"
                      placeholder="Role fine (e.g. software, data)"
                      value={draft.role_fine ?? ""}
                      onChange={(e) => setDraft((d) => ({ ...d, role_fine: e.target.value }))}
                    />
                    <div className="cand-detail-meta-row cand-detail-meta-row-edit">
                      <span className={`${scoreClass(sc)} cand-detail-score-chip`} title={buildScoreTitle(c)}>
                        {bm == null ? "—" : `${sc}%`}
                      </span>
                      <label className="cand-detail-status-select-wrap">
                        <span className="visually-hidden">Status</span>
                        <select
                          className="cand-detail-status-select"
                          value={(draft.status ?? "new").toLowerCase()}
                          onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}
                        >
                          {STATUS_OPTIONS.map((o) => (
                            <option key={o.value} value={o.value}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <input
                        className="cand-detail-pill-input"
                        aria-label="Role label"
                        placeholder="Role label"
                        value={draft.role_label ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, role_label: e.target.value }))}
                      />
                    </div>
                  </div>
                </div>
                <CandidateHeroToolbar
                  canUseResume={canUseResume}
                  deleting={deleting}
                  editOpen={editOpen}
                  onToggleEdit={() => {
                    setEditOpen((was) => {
                    if (was) {
                      return false;
                    }
                      const cur = cRef.current;
                      if (cur) setDraft(buildDraft(cur));
                      return true;
                    });
                  }}
                  onPreview={() => setPreviewOpen(true)}
                  onDownload={() => void onDownloadResume()}
                  onMessage={onMessage}
                  onDelete={requestDelete}
                />
              </div>

              <div className="cand-detail-grid">
                <section className="cand-detail-card">
                  <h2>Profile</h2>
                  <dl className="cand-detail-dl cand-detail-dl-edit">
                    <dt>Experience (years)</dt>
                    <dd>
                      <input
                        type="number"
                        step="0.1"
                        aria-label="Years of experience"
                        value={
                          draft.years_experience != null
                            ? draft.years_experience
                            : (draft.title || "").trim().toLowerCase() === "fresher"
                              ? 0
                              : ""
                        }
                        onChange={(e) =>
                          setDraft((d) => ({
                            ...d,
                            years_experience: e.target.value === "" ? null : Number(e.target.value),
                          }))
                        }
                      />
                      {(draft.title || "").trim().toLowerCase() === "fresher" ? (
                        <p className="muted" style={{ marginTop: "0.35rem", marginBottom: 0, fontSize: "0.85rem" }}>
                          Fresher profiles use 0 professional years unless you set a value.
                        </p>
                      ) : null}
                    </dd>
                    <dt>Highest degree</dt>
                    <dd>
                      <input
                        aria-label="Highest degree"
                        value={draft.highest_degree ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, highest_degree: e.target.value }))}
                      />
                    </dd>
                    <dt>Contact email</dt>
                    <dd>
                      <input
                        type="email"
                        autoComplete="email"
                        aria-label="Contact email"
                        value={draft.contact_email ?? ""}
                        onChange={(e) => setDraft((d) => ({ ...d, contact_email: e.target.value }))}
                      />
                    </dd>
                    <dt>External ID</dt>
                    <dd className="cand-detail-mono">{c.external_id}</dd>
                    <dt>Added</dt>
                    <dd>{c.created_at ? new Date(c.created_at).toLocaleString() : "—"}</dd>
                    <dt>Resume file</dt>
                    <dd className="cand-detail-resume-dd">
                      {c.filename?.trim() || canUseResume ? (
                        <>
                          <span className="cand-detail-filename">{c.filename?.trim() || "Stored resume"}</span>
                          {canUseResume ? (
                            <button
                              type="button"
                              className="cand-detail-inline-download"
                              onClick={() => void onDownloadResume()}
                            >
                              Download
                            </button>
                          ) : null}
                        </>
                      ) : (
                        "—"
                      )}
                    </dd>
                  </dl>
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Skills</h2>
                  <textarea
                    className="cand-detail-card-textarea"
                    rows={5}
                    aria-label="Skills"
                    value={draft.skills ?? ""}
                    onChange={(e) => setDraft((d) => ({ ...d, skills: e.target.value }))}
                  />
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Certifications</h2>
                  <textarea
                    className="cand-detail-card-textarea"
                    rows={5}
                    aria-label="Certifications"
                    value={pipeToMultiline(draft.certifications ?? "")}
                    onChange={(e) => setDraft((d) => ({ ...d, certifications: multilineToPipe(e.target.value) }))}
                  />
                  <p className="cand-detail-form-hint" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                    One certification per line (stored as entries separated by &quot; | &quot;).
                  </p>
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Education</h2>
                  <textarea
                    className="cand-detail-card-textarea"
                    rows={5}
                    aria-label="Education"
                    value={pipeToMultiline(draft.education_lines ?? "")}
                    onChange={(e) => setDraft((d) => ({ ...d, education_lines: multilineToPipe(e.target.value) }))}
                  />
                  <p className="cand-detail-form-hint" style={{ marginTop: "0.5rem", marginBottom: 0 }}>
                    One school or degree line per row (stored as &quot; | &quot;-separated text).
                  </p>
                </section>
              </div>

              <div className="cand-detail-form-actions cand-detail-edit-footer">
                <button type="button" className="small-btn" onClick={() => setEditOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="dash-btn" disabled={saving}>
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </div>
            </form>
          ) : (
            <>
              <div className="cand-detail-hero">
                <div className="cand-detail-hero-main">
                  <div className="cand-detail-avatar" aria-hidden="true">
                    {candidateAvatarInitials(c)}
                  </div>
                  <div className="cand-detail-hero-text">
                    <h1 className="cand-detail-name">{candidateDisplayName(c)}</h1>
                    <div className="cand-detail-headline">{c.title || "—"}</div>
                    {(c.skills_role_hint || "").trim() ? (
                      <div className="muted" style={{ fontSize: "0.88rem", marginTop: "0.15rem" }}>
                        Skills-aligned role: {c.skills_role_hint}
                      </div>
                    ) : null}
                    {(c.role_fine || "").trim() && (c.role_fine || "").trim().toLowerCase() !== "unknown" ? (
                      <div className="cand-detail-rolefine muted">{displayRoleFine(c.role_fine)}</div>
                    ) : null}
                    <div className="cand-detail-meta-row">
                      <span className={`${scoreClass(sc)} cand-detail-score-chip`} title={buildScoreTitle(c)}>
                        {bm == null ? "—" : `${sc}%`}
                      </span>
                      <span className={`cand-status ${st}`} title="Includes automatic transition from New after 7 days.">
                        {statusLabel(c.status_effective || c.status)}
                      </span>
                      <span
                        className={`cand-pool-badge ${c.is_public ? "pool-public" : "pool-private"}`}
                        title={c.is_public ? "Applied via candidate portal" : "Uploaded by recruiter"}
                      >
                        {c.is_public ? "Public" : "Private"}
                      </span>
                      {(c.role_label || "").trim() ? (
                        <span className="cand-detail-pill muted">{c.role_label}</span>
                      ) : null}
                    </div>
                    {(() => {
                      const title = (c.best_job_title || "").trim();
                      const dept = (c.best_job_department || "").trim();
                      const client = (c.best_job_client_name || c.best_job_client_company || "").trim();
                      if (!title && !client) return null;
                      const jobPart = [title, dept].filter(Boolean).join(" · ");
                      const line = jobPart && client ? `${jobPart} · ${client}` : jobPart || `Hiring: ${client}`;
                      return (
                        <div className="muted cand-detail-bestjob" style={{ marginTop: "0.35rem", fontSize: "0.88rem" }}>
                          Best match job: {line}
                        </div>
                      );
                    })()}
                  </div>
                </div>
                <CandidateHeroToolbar
                  canUseResume={canUseResume}
                  deleting={deleting}
                  editOpen={editOpen}
                  onToggleEdit={() => {
                    setEditOpen((was) => {
                    if (was) {
                      return false;
                    }
                      const cur = cRef.current;
                      if (cur) setDraft(buildDraft(cur));
                      return true;
                    });
                  }}
                  onPreview={() => setPreviewOpen(true)}
                  onDownload={() => void onDownloadResume()}
                  onMessage={onMessage}
                  onDelete={requestDelete}
                />
              </div>

              <div className="cand-detail-grid">
                <section className="cand-detail-card">
                  <h2>Profile</h2>
                  <dl className="cand-detail-dl">
                    <dt>Experience</dt>
                    <dd>{formatCandidateExperience(c)}</dd>
                    <dt>Highest degree</dt>
                    <dd>{c.highest_degree?.trim() ? c.highest_degree : "—"}</dd>
                    <dt>Contact email</dt>
                    <dd>{(c.contact_email || "").trim() ? c.contact_email : "—"}</dd>
                    <dt>External ID</dt>
                    <dd className="cand-detail-mono">{c.external_id}</dd>
                    <dt>Added</dt>
                    <dd>{c.created_at ? new Date(c.created_at).toLocaleString() : "—"}</dd>
                    <dt>Resume file</dt>
                    <dd className="cand-detail-resume-dd">
                      {c.filename?.trim() || canUseResume ? (
                        <>
                          <span className="cand-detail-filename">{c.filename?.trim() || "Stored resume"}</span>
                          {canUseResume ? (
                            <button
                              type="button"
                              className="cand-detail-inline-download"
                              onClick={() => void onDownloadResume()}
                            >
                              Download
                            </button>
                          ) : null}
                        </>
                      ) : (
                        "—"
                      )}
                    </dd>
                  </dl>
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Skills</h2>
                  <p className="cand-detail-body">{c.skills?.trim() ? c.skills : "—"}</p>
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Certifications</h2>
                  <PipeFieldList text={c.certifications} />
                </section>

                <section className="cand-detail-card cand-detail-card-wide">
                  <h2>Education</h2>
                  <PipeFieldList text={c.education_lines} />
                </section>

                {jobEvals.length > 0 ? (
                  <section className="cand-detail-card cand-detail-card-wide">
                    <h2>Job match transparency</h2>
                    <p className="muted cand-detail-body" style={{ marginTop: 0 }}>
                      Scores for roles you were evaluated against, including retrieval matches that did not reach the final ranked list.
                    </p>
                    <div className="job-table-wrap" style={{ marginTop: "0.5rem" }}>
                      <table className="job-table">
                        <thead>
                          <tr>
                            <th>Job</th>
                            <th>Pipeline</th>
                            <th>Match</th>
                            <th>Similarity</th>
                            <th>Notes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {jobEvals.map((row) => (
                            <tr key={row.job_external_id}>
                              <td>
                                <Link to={`/jobs?job=${encodeURIComponent(row.job_external_id)}`}>
                                  {row.job_title?.trim() || row.job_external_id}
                                </Link>
                              </td>
                              <td>{statusLabel(row.applicant_status_effective || row.applicant_status || "—")}</td>
                              <td>
                                {row.cross_encoder_score != null && Number.isFinite(row.cross_encoder_score)
                                  ? `${Math.round(Math.max(0, Math.min(1, row.cross_encoder_score)) * 100)}%`
                                  : "—"}
                              </td>
                              <td>
                                {row.retrieval_similarity != null && Number.isFinite(row.retrieval_similarity)
                                  ? `${Math.round(Math.max(0, Math.min(1, row.retrieval_similarity)) * 100)}%`
                                  : "—"}
                              </td>
                              <td className="muted" style={{ maxWidth: 280 }}>
                                {row.brief_reason ||
                                  (row.in_saved_ranking ? "Included in saved ranking run." : "Not in saved shortlist ranking.")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                ) : null}
              </div>
            </>
          )}

          <ConfirmDialog
            open={deleteConfirmOpen}
            title="Remove this candidate?"
            message={`“${candidateDisplayName(c)}” will be removed from your pool. This cannot be undone.`}
            cancelLabel="Keep"
            confirmLabel="Remove"
            danger
            busy={deleting}
            onClose={() => {
              if (!deleting) setDeleteConfirmOpen(false);
            }}
            onConfirm={() => void performDelete()}
          />

          <ResumePreviewModal
            open={previewOpen}
            externalId={c.external_id}
            filename={c.filename}
            onClose={closeResumePreview}
          />
        </>
      )}
    </DashFrame>
  );
}

function buildScoreTitle(c: CandidateDto): string | undefined {
  const bm = bestMatchScore(c);
  if (bm == null) return "No job match score yet (candidate not ranked/matched to any job).";
  const jid = (c.best_job_external_id || "").trim();
  const jt = (c.best_job_title || "").trim();
  if (jt && jid) return `Best match: ${bm}% — ${jt} (${jid})`;
  if (jid) return `Best match: ${bm}% (job ${jid})`;
  return `Best match: ${bm}%`;
}
