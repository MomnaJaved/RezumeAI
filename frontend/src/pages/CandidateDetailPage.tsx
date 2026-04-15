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
import { candidateListProfileScore } from "../candidateListScore";
import {
  deleteCandidateByExternalId,
  fetchCandidate,
  fetchCandidateFileBlob,
  fetchCandidateWithScores,
  updateCandidate,
  type CandidateDto,
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
  const v = c.best_job_match_score;
  if (v == null || Number.isNaN(Number(v))) return null;
  return Math.max(0, Math.min(100, Math.round(Number(v))));
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
  { value: "interviewed", label: "Interviewed" },
  { value: "hired", label: "Hired" },
  { value: "rejected", label: "Rejected" },
  { value: "selected", label: "Selected" },
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

  function scoreFor(row: CandidateDto): number {
    const bm = bestMatchScore(row);
    return bm ?? candidateListProfileScore(row);
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
      const next = await updateCandidate(c.id, draft);
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

  const sc = c ? scoreFor(c) : 0;
  const st = (c?.status || "new").toLowerCase();
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
                        {sc}%
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
                        value={draft.years_experience ?? ""}
                        onChange={(e) =>
                          setDraft((d) => ({
                            ...d,
                            years_experience: e.target.value === "" ? null : Number(e.target.value),
                          }))
                        }
                      />
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
                    {(c.role_fine || "").trim() && (c.role_fine || "").trim().toLowerCase() !== "unknown" ? (
                      <div className="cand-detail-rolefine muted">{displayRoleFine(c.role_fine)}</div>
                    ) : null}
                    <div className="cand-detail-meta-row">
                      <span className={`${scoreClass(sc)} cand-detail-score-chip`} title={buildScoreTitle(c)}>
                        {sc}%
                      </span>
                      <span className={`cand-status ${st}`}>{statusLabel(c.status)}</span>
                      {(c.role_label || "").trim() ? (
                        <span className="cand-detail-pill muted">{c.role_label}</span>
                      ) : null}
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
                  <dl className="cand-detail-dl">
                    <dt>Experience</dt>
                    <dd>{c.years_experience != null ? `${c.years_experience} years` : "—"}</dd>
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
  if (bm == null) return "Match score not available (no jobs in database).";
  const jid = (c.best_job_external_id || "").trim();
  return jid ? `Best match: ${bm}% (job ${jid})` : `Best match: ${bm}%`;
}
