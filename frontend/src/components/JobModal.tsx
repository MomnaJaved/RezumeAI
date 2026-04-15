import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteJobByExternalId,
  deleteJobAttachment,
  fetchClients,
  fetchJobByExternalId,
  fetchJobApplicantStats,
  fetchJobAttachments,
  fetchSavedRankings,
  downloadJobAttachmentBlob,
  updateJobApplicantStatus,
  updateJobByExternalId,
  uploadJobAttachment,
  type Job,
  type JobAttachmentDto,
  type RankedCandidate,
} from "../api";
import { useToast } from "../toast";
import ConfirmDialog from "./ConfirmDialog";

type TabKey = "overview" | "applicants" | "matching" | "notes" | "attachments";

function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  const x = new Date(d);
  if (Number.isNaN(x.getTime())) return "—";
  return x.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

function dateInputValue(d: string | null | undefined): string {
  if (!d) return "";
  const x = new Date(d);
  if (Number.isNaN(x.getTime())) return "";
  const yyyy = x.getFullYear();
  const mm = String(x.getMonth() + 1).padStart(2, "0");
  const dd = String(x.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function scorePct(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  if (!Number.isFinite(x)) return "—";
  const pct = Math.max(0, Math.min(100, Math.round(x * 100)));
  return `${pct}%`;
}

function mapSavedRow(row: {
  candidate_external_id: string;
  cross_encoder_score: number;
  sbert_similarity: number;
  candidate_name: string;
  candidate_title: string;
  candidate_role: string;
  years_experience: number | null;
  highest_degree: string;
  skills_summary: string;
}): RankedCandidate {
  return {
    candidate_id: row.candidate_external_id,
    cross_encoder_score: row.cross_encoder_score,
    sbert_similarity: row.sbert_similarity,
    candidate_name: row.candidate_name,
    candidate_title: row.candidate_title,
    candidate_role: row.candidate_role,
    years_experience: row.years_experience,
    highest_degree: row.highest_degree,
    skills_summary: row.skills_summary,
  };
}

function notesKey(jobExternalId: string) {
  return `rezume.jobs.notes.${jobExternalId}`;
}

type LocalNote = { id: string; body: string; created_at: string };

function readLocalNotes(jobExternalId: string): LocalNote[] {
  try {
    const raw = localStorage.getItem(notesKey(jobExternalId));
    if (!raw) return [];
    const j = JSON.parse(raw) as LocalNote[];
    return Array.isArray(j) ? j : [];
  } catch {
    return [];
  }
}

function writeLocalNotes(jobExternalId: string, notes: LocalNote[]) {
  try {
    localStorage.setItem(notesKey(jobExternalId), JSON.stringify(notes));
  } catch {
    /* ignore */
  }
}

export default function JobModal({
  open,
  externalId,
  onClose,
  onJobUpdated,
  onJobDeleted,
}: {
  open: boolean;
  externalId: string;
  onClose: () => void;
  onJobUpdated?: (job: Job) => void;
  onJobDeleted?: (externalId: string) => void;
}) {
  const toast = useToast();
  const [tab, setTab] = useState<TabKey>("overview");
  const [job, setJob] = useState<Job | null>(null);
  const [rankings, setRankings] = useState<RankedCandidate[] | null>(null);
  const [clients, setClients] = useState<{ id: string; name: string }[]>([]);
  const [appStats, setAppStats] = useState<{ total: number; new: number; screened: number; shortlisted: number; interviewed: number; hired: number } | null>(
    null,
  );
  const [appStatusByCandidate, setAppStatusByCandidate] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [, setError] = useState<string | null>(null);
  const [savingJob, setSavingJob] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<Partial<Job>>({});
  const [attachments, setAttachments] = useState<JobAttachmentDto[]>([]);
  const [attLoading, setAttLoading] = useState(false);
  const [attBusy, setAttBusy] = useState(false);
  const [deleteJobOpen, setDeleteJobOpen] = useState(false);
  const [deleteAtt, setDeleteAtt] = useState<JobAttachmentDto | null>(null);

  const [notes, setNotes] = useState<LocalNote[]>([]);
  const [noteDraft, setNoteDraft] = useState("");

  useEffect(() => {
    if (!open) return;
    setTab("overview");
    setEditMode(false);
    setEditDraft({});
  }, [open, externalId]);

  useEffect(() => {
    if (!open || !externalId) return;
    setError(null);
    setJob(null);
    setRankings(null);
    setAttachments([]);
    setAppStats(null);
    setAppStatusByCandidate({});
    setLoading(true);
    Promise.allSettled([fetchJobByExternalId(externalId), fetchSavedRankings(externalId)])
      .then((parts) => {
        const [j, r] = parts;
        if (j.status === "fulfilled") {
          setJob(j.value);
          setEditDraft({});
        }
        if (r.status === "fulfilled") setRankings(r.value.rankings.map(mapSavedRow));
      })
      .catch(() => {
        /* no-op */
      })
      .finally(() => setLoading(false));
  }, [open, externalId]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await fetchClients({ status: "active" });
        if (cancelled) return;
        setClients((rows || []).map((c) => ({ id: c.id, name: c.name })));
      } catch {
        if (!cancelled) setClients([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open || !externalId) return;
    let cancelled = false;
    (async () => {
      try {
        const s = await fetchJobApplicantStats(externalId);
        if (cancelled) return;
        setAppStats({ total: s.total, new: s.new, screened: s.screened, shortlisted: s.shortlisted, interviewed: s.interviewed, hired: s.hired });
      } catch {
        if (!cancelled) setAppStats(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, externalId]);

  useEffect(() => {
    if (!open || !externalId) return;
    setAttLoading(true);
    fetchJobAttachments(externalId)
      .then(setAttachments)
      .catch(() => setAttachments([]))
      .finally(() => setAttLoading(false));
  }, [open, externalId]);

  useEffect(() => {
    if (!open || !externalId) return;
    setNotes(readLocalNotes(externalId));
  }, [open, externalId]);

  useEffect(() => {
    if (!open || !externalId) return;
    writeLocalNotes(externalId, notes);
  }, [open, externalId, notes]);

  const escClose = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (!open) return;
    window.addEventListener("keydown", escClose);
    return () => window.removeEventListener("keydown", escClose);
  }, [open, escClose]);

  const applicantsCounts = useMemo(() => {
    if (appStats) return appStats;
    const total = rankings?.length ?? 0;
    return { total, new: total, screened: 0, shortlisted: 0, interviewed: 0, hired: 0 };
  }, [rankings, appStats]);

  const canMutate = Boolean(externalId.trim());

  const runUpdate = useCallback(
    async (patch: Record<string, unknown>) => {
      if (!canMutate) return;
      setSavingJob(true);
      setError(null);
      try {
        const updated = await updateJobByExternalId(externalId, patch as any);
        setJob(updated);
        onJobUpdated?.(updated);
        const keys = Object.keys(patch);
        if (keys.length === 1 && keys[0] === "status") {
          const s = String((patch as any).status || "").toLowerCase();
          toast.success(s === "active" ? "Job marked active." : "Job removed from active pool.");
        } else {
          toast.success("Job updated.");
        }
      } catch (e) {
        toast.error((e as Error).message);
      } finally {
        setSavingJob(false);
      }
    },
    [canMutate, externalId, onJobUpdated, toast],
  );

  const saveEdits = useCallback(async () => {
    if (!job) return;
    const patch: Record<string, unknown> = {};
    for (const k of [
      "client_id",
      "title",
      "department",
      "description",
      "skills",
      "salary_range",
      "work_location",
      "job_type",
      "recruitment_urgency",
      "preferred_onboarding_date",
      "status",
      "education_required",
      "min_experience",
    ] as const) {
      const next = (editDraft as any)[k];
      if (next !== undefined && (job as any)[k] !== next) patch[k] = next;
    }
    if (Object.keys(patch).length === 0) {
      setEditMode(false);
      return;
    }
    await runUpdate(patch);
    setEditMode(false);
  }, [editDraft, job, runUpdate]);

  const doDeleteJob = useCallback(async () => {
    if (!canMutate) return;
    setSavingJob(true);
    setError(null);
    try {
      await deleteJobByExternalId(externalId);
      toast.success("Job deleted.");
      onJobDeleted?.(externalId);
      onClose();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSavingJob(false);
      setDeleteJobOpen(false);
    }
  }, [canMutate, externalId, onClose, onJobDeleted, toast]);

  if (!open) return null;

  return (
    <div className="job-modal-overlay" role="dialog" aria-modal="true" aria-label="Job details">
      {/* Backdrop must be behind modal; otherwise it blocks clicks. */}
      <button type="button" className="job-modal-backdrop" aria-label="Close" onClick={onClose} />
      <div className="job-modal" onClick={(e) => e.stopPropagation()}>
        <div className="job-modal-top">
          <div className="job-modal-head">
            <div className="job-modal-title">
              {job?.title || `Job ${externalId}`}
              <span className="job-modal-sub">| {job?.department || "—"}</span>
            </div>
            <div className="job-modal-meta">
              <span className="job-pill">Posted: {fmtDate(job?.created_at)}</span>
              <span className="job-pill">Min exp: {job?.min_experience ?? "—"}</span>
              <span className="job-pill">Education: {job?.education_required || "—"}</span>
            </div>
          </div>
          <div className="job-modal-actions">
            {!editMode ? (
              <button
                type="button"
                className="small-btn job-action-btn job-action-btn--primary"
                disabled={savingJob || loading || !job}
                onClick={() => {
                  if (!job) return;
                  setEditDraft({
                    title: job.title,
                    department: job.department,
                    description: job.description,
                    skills: job.skills,
                    salary_range: (job as any).salary_range ?? "",
                    work_location: (job as any).work_location ?? "",
                    job_type: (job as any).job_type ?? "",
                    recruitment_urgency: (job as any).recruitment_urgency ?? "",
                    preferred_onboarding_date: (job as any).preferred_onboarding_date ?? null,
                    status: (job as any).status ?? "active",
                    min_experience: job.min_experience,
                    education_required: job.education_required,
                  });
                  setEditMode(true);
                  setTab("overview");
                }}
              >
                Edit Job
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="small-btn job-action-btn job-action-btn--primary"
                  disabled={savingJob}
                  onClick={() => void saveEdits()}
                >
                  Save
                </button>
                <button
                  type="button"
                  className="small-btn job-action-btn"
                  disabled={savingJob}
                  onClick={() => {
                    setEditMode(false);
                    setEditDraft({});
                  }}
                >
                  Cancel
                </button>
              </>
            )}
            <button
              type="button"
              className="small-btn job-action-btn job-action-btn--danger"
              disabled={savingJob || loading}
              onClick={() => setDeleteJobOpen(true)}
            >
              Delete Job
            </button>
            <button type="button" className="job-modal-close" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        <div className="job-tabs">
          {(
            [
              ["overview", "Overview"],
              ["applicants", "Applicants"],
              ["matching", "Matching"],
              ["notes", "Notes"],
              ["attachments", "Attachments"],
            ] as Array<[TabKey, string]>
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              className={tab === k ? "job-tab active" : "job-tab"}
              onClick={() => setTab(k)}
            >
              {label}
            </button>
          ))}
        </div>

        {loading ? <div className="job-modal-body muted">Loading…</div> : null}

        {!loading ? (
          <div className="job-modal-body">
            {tab === "overview" ? (
              <div className="job-overview-grid">
                <div className="job-card">
                  <div className="job-card-title">Job Information</div>
                  <div className="job-kv">
                    <div className="job-kv-row">
                      <div className="muted">Status</div>
                      <div>
                        {editMode ? (
                          <select
                            value={String((editDraft as any).status ?? "active")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, status: e.target.value } as any))}
                          >
                            <option value="active">Active</option>
                            <option value="on_hold">On hold</option>
                            <option value="completed">Completed</option>
                            <option value="cancelled">Cancelled</option>
                          </select>
                        ) : (
                          <span className={`job-status ${(job?.status || "active").toLowerCase()}`}>
                            {(job?.status || "active").toLowerCase() === "on_hold"
                              ? "On hold"
                              : (job?.status || "active")[0].toUpperCase() + (job?.status || "active").slice(1)}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Client</div>
                      <div>
                        {editMode ? (
                          <select
                            value={String((editDraft as any).client_id ?? (job as any)?.client_id ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...(d as any), client_id: e.target.value || null }))}
                          >
                            <option value="">Select client</option>
                            {clients.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                        ) : (
                          ((job as any)?.client_name || "—")
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Title</div>
                      <div>
                        {editMode ? (
                          <input
                            value={String(editDraft.title ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, title: e.target.value }))}
                            placeholder="Job title"
                          />
                        ) : (
                          job?.title || "—"
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Department</div>
                      <div>
                        {editMode ? (
                          <input
                            value={String(editDraft.department ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, department: e.target.value }))}
                            placeholder="Department"
                          />
                        ) : (
                          job?.department || "—"
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Experience Required</div>
                      <div>
                        {editMode ? (
                          <input
                            value={String(editDraft.min_experience ?? "")}
                            onChange={(e) =>
                              setEditDraft((d) => ({
                                ...d,
                                min_experience: e.target.value.trim() === "" ? null : Number(e.target.value),
                              }))
                            }
                            placeholder="e.g. 2"
                          />
                        ) : (
                          job?.min_experience ?? "—"
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Salary Range</div>
                      <div>
                        {editMode ? (
                          <input
                            value={String((editDraft as any).salary_range ?? job?.salary_range ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, salary_range: e.target.value } as any))}
                            placeholder="50,000 – 70,000"
                          />
                        ) : (
                          (job?.salary_range || "—")
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Location</div>
                      <div>
                        {editMode ? (
                          <select
                            value={String((editDraft as any).work_location ?? (job as any)?.work_location ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, work_location: e.target.value } as any))}
                          >
                            <option value="">Select location</option>
                            <option value="on_site">On-site</option>
                            <option value="remote">Remote</option>
                          </select>
                        ) : (
                          ((job as any)?.work_location === "on_site"
                            ? "On-site"
                            : (job as any)?.work_location === "remote"
                              ? "Remote"
                              : "—")
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Job Type</div>
                      <div>
                        {editMode ? (
                          <select
                            value={String((editDraft as any).job_type ?? (job as any)?.job_type ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, job_type: e.target.value } as any))}
                          >
                            <option value="">Select job type</option>
                            <option value="full_time">Full-time</option>
                            <option value="part_time">Part-time</option>
                          </select>
                        ) : (
                          ((job as any)?.job_type === "full_time"
                            ? "Full-time"
                            : (job as any)?.job_type === "part_time"
                              ? "Part-time"
                              : "—")
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Recruitment Urgency</div>
                      <div>
                        {editMode ? (
                          <select
                            value={String((editDraft as any).recruitment_urgency ?? (job as any)?.recruitment_urgency ?? "")}
                            onChange={(e) => setEditDraft((d) => ({ ...d, recruitment_urgency: e.target.value } as any))}
                          >
                            <option value="">Select urgency</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                          </select>
                        ) : (
                          ((job as any)?.recruitment_urgency
                            ? String((job as any).recruitment_urgency)[0].toUpperCase() +
                              String((job as any).recruitment_urgency).slice(1)
                            : "—")
                        )}
                      </div>
                    </div>
                    <div className="job-kv-row">
                      <div className="muted">Preferred Onboarding Date</div>
                      <div>
                        {editMode ? (
                          <input
                            type="date"
                            value={dateInputValue((editDraft as any).preferred_onboarding_date ?? (job as any)?.preferred_onboarding_date)}
                            onChange={(e) =>
                              setEditDraft((d) => ({
                                ...d,
                                preferred_onboarding_date: e.target.value ? new Date(e.target.value).toISOString() : null,
                              }))
                            }
                          />
                        ) : (
                          fmtDate((job as any)?.preferred_onboarding_date)
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="job-card">
                  <div className="job-card-title">Applicants</div>
                  <div className="job-app-counts">
                    <div>Total Applicants: {applicantsCounts.total}</div>
                    <div>New: {applicantsCounts.new}</div>
                    <div>Screened: {applicantsCounts.screened}</div>
                    <div>Shortlisted: {applicantsCounts.shortlisted}</div>
                    <div>Interviewed: {applicantsCounts.interviewed}</div>
                    <div>Hired: {applicantsCounts.hired}</div>
                  </div>
                </div>
                <div className="job-card job-card-wide">
                  <div className="job-card-title">Job Description</div>
                  <div className="job-desc">
                    <div>
                      <strong>Required Skills:</strong>{" "}
                      {editMode ? (
                        <input
                          value={String(editDraft.skills ?? "")}
                          onChange={(e) => setEditDraft((d) => ({ ...d, skills: e.target.value }))}
                          placeholder="React, TypeScript, REST APIs…"
                        />
                      ) : (
                        job?.skills || "—"
                      )}
                    </div>
                    <div style={{ marginTop: "0.35rem" }}>
                      <strong>Description:</strong>{" "}
                      {editMode ? (
                        <textarea
                          value={String(editDraft.description ?? "")}
                          onChange={(e) => setEditDraft((d) => ({ ...d, description: e.target.value }))}
                          rows={6}
                        />
                      ) : (
                        job?.description || "—"
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {tab === "applicants" ? (
              <div className="job-tab-panel">
                {rankings && rankings.length > 0 ? (
                  <div className="job-table-wrap">
                    <table className="job-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Status</th>
                          <th>Score</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rankings.slice(0, 50).map((r) => (
                          <tr key={r.candidate_id}>
                            <td>{r.candidate_name || r.candidate_id}</td>
                            <td>
                              <select
                                value={appStatusByCandidate[r.candidate_id] || "new"}
                                onChange={async (e) => {
                                  const next = e.target.value;
                                  setAppStatusByCandidate((m) => ({ ...m, [r.candidate_id]: next }));
                                  try {
                                    await updateJobApplicantStatus(externalId, r.candidate_id, next);
                                    const s = await fetchJobApplicantStats(externalId);
                                    setAppStats({
                                      total: s.total,
                                      new: s.new,
                                      screened: s.screened,
                                      shortlisted: s.shortlisted,
                                      interviewed: s.interviewed,
                                      hired: s.hired,
                                    });
                                    toast.success("Applicant status updated.");
                                  } catch (err) {
                                    toast.error((err as Error).message || "Failed to update status");
                                  }
                                }}
                              >
                                <option value="new">New</option>
                                <option value="screened">Screened</option>
                                <option value="shortlisted">Shortlisted</option>
                                <option value="interviewed">Interviewed</option>
                                <option value="hired">Hired</option>
                              </select>
                            </td>
                            <td>{scorePct(r.cross_encoder_score)}</td>
                            <td>
                              <Link className="job-link-btn" to={`/candidates/lookup/${encodeURIComponent(r.candidate_id)}`}>
                                View Profile »
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="muted">No rankings saved for this job yet. Run “Save DB ranking” from the job page if needed.</div>
                )}
              </div>
            ) : null}

            {tab === "matching" ? (
              <div className="job-tab-panel">
                {rankings && rankings.length > 0 ? (
                  <div className="job-table-wrap">
                    <table className="job-table">
                      <thead>
                        <tr>
                          <th>Rank</th>
                          <th>Name</th>
                          <th>Score</th>
                          <th>Skills</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rankings.slice(0, 50).map((r, i) => (
                          <tr key={r.candidate_id}>
                            <td>{i + 1}</td>
                            <td>{r.candidate_name || r.candidate_id}</td>
                            <td className="job-score">{scorePct(r.cross_encoder_score)}</td>
                            <td className="muted" title={r.skills_summary || ""}>
                              {r.skills_summary ? `${r.skills_summary.slice(0, 48)}${r.skills_summary.length > 48 ? "…" : ""}` : "—"}
                            </td>
                            <td>
                              <Link className="job-link-btn" to={`/candidates/lookup/${encodeURIComponent(r.candidate_id)}`}>
                                View Profile »
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="muted">
                    No matching results saved yet for this job. (Next: we’ll add a “Run matching” button right here.)
                  </div>
                )}
              </div>
            ) : null}

            {tab === "notes" ? (
              <div className="job-tab-panel">
                <div className="job-notes-compose">
                  <textarea
                    value={noteDraft}
                    onChange={(e) => setNoteDraft(e.target.value)}
                    placeholder="Write a note…"
                    rows={3}
                  />
                  <div className="job-notes-actions">
                    <button
                      type="button"
                      className="small-btn"
                      onClick={() => {
                        const body = noteDraft.trim();
                        if (!body) return;
                        setNotes((prev) => [
                          { id: crypto.randomUUID(), body, created_at: new Date().toISOString() },
                          ...prev,
                        ]);
                        setNoteDraft("");
                      }}
                    >
                      Save
                    </button>
                    <div className="muted" style={{ fontSize: "0.8rem" }}>
                      Saved locally for now.
                    </div>
                  </div>
                </div>
                {notes.length === 0 ? (
                  <div className="muted">No notes yet.</div>
                ) : (
                  <div className="job-notes-list">
                    {notes.map((n) => (
                      <div key={n.id} className="job-note">
                        <div className="job-note-meta muted">{fmtDate(n.created_at)}</div>
                        <div className="job-note-body">{n.body}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : null}

            {tab === "attachments" ? (
              <div className="job-tab-panel">
                <div className="job-attachments-head">
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    Upload files (PDF, DOCX, images, TXT).
                  </div>
                  <label className="job-link-btn" style={{ cursor: attBusy ? "not-allowed" : "pointer" }}>
                    Upload file
                    <input
                      type="file"
                      style={{ display: "none" }}
                      disabled={attBusy}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (!f) return;
                        e.currentTarget.value = "";
                        (async () => {
                          setAttBusy(true);
                          try {
                            const created = await uploadJobAttachment(externalId, f);
                            setAttachments((prev) => [created, ...prev]);
                            toast.success("Attachment uploaded.");
                          } catch (err) {
                            toast.error((err as Error).message);
                          } finally {
                            setAttBusy(false);
                          }
                        })();
                      }}
                    />
                  </label>
                </div>

                {attLoading ? (
                  <div className="muted" style={{ marginTop: "0.75rem" }}>
                    Loading attachments…
                  </div>
                ) : attachments.length === 0 ? (
                  <div className="muted" style={{ marginTop: "0.75rem" }}>
                    No attachments yet.
                  </div>
                ) : (
                  <div className="job-table-wrap" style={{ marginTop: "0.75rem" }}>
                    <table className="job-table">
                      <thead>
                        <tr>
                          <th>File</th>
                          <th>Size</th>
                          <th>Uploaded</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {attachments.map((a) => (
                          <tr key={a.id}>
                            <td title={a.filename}>{a.filename}</td>
                            <td className="muted">
                              {a.size_bytes >= 1024 * 1024
                                ? `${(a.size_bytes / (1024 * 1024)).toFixed(1)} MB`
                                : `${Math.max(1, Math.round(a.size_bytes / 1024))} KB`}
                            </td>
                            <td className="muted">
                              {a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}
                            </td>
                            <td>
                              <button
                                type="button"
                                className="small-btn job-action-btn"
                                disabled={attBusy}
                                onClick={() => {
                                  (async () => {
                                    setAttBusy(true);
                                    try {
                                      const { blob } = await downloadJobAttachmentBlob(externalId, a.id);
                                      const url = URL.createObjectURL(blob);
                                      const link = document.createElement("a");
                                      link.href = url;
                                      link.download = a.filename || "attachment";
                                      link.rel = "noopener";
                                      document.body.appendChild(link);
                                      link.click();
                                      link.remove();
                                      URL.revokeObjectURL(url);
                                    } catch (err) {
                                      toast.error((err as Error).message);
                                    } finally {
                                      setAttBusy(false);
                                    }
                                  })();
                                }}
                              >
                                Download
                              </button>
                              <button
                                type="button"
                                className="small-btn job-action-btn job-action-btn--danger"
                                disabled={attBusy}
                                style={{ marginLeft: "0.4rem" }}
                                onClick={() => {
                                  setDeleteAtt(a);
                                }}
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={deleteJobOpen}
        title="Delete job"
        message="Delete this job? This will also remove saved rankings and attachments for this job."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        busy={savingJob}
        onClose={() => !savingJob && setDeleteJobOpen(false)}
        onConfirm={() => void doDeleteJob()}
      />

      <ConfirmDialog
        open={deleteAtt !== null}
        title="Delete attachment"
        message={deleteAtt ? `Delete ${deleteAtt.filename}?` : "Delete this attachment?"}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        danger
        busy={attBusy}
        onClose={() => !attBusy && setDeleteAtt(null)}
        onConfirm={() => {
          if (!deleteAtt) return;
          (async () => {
            setAttBusy(true);
            try {
              await deleteJobAttachment(externalId, deleteAtt.id);
              setAttachments((prev) => prev.filter((x) => x.id !== deleteAtt.id));
              toast.success("Attachment deleted.");
            } catch (err) {
              toast.error((err as Error).message);
            } finally {
              setAttBusy(false);
              setDeleteAtt(null);
            }
          })();
        }}
      />
    </div>
  );
}

