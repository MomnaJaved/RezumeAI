import { getStoredToken } from "./auth";

const base = import.meta.env.VITE_API_BASE ?? "";

async function authedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const token = getStoredToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const j = JSON.parse(text) as { detail?: string };
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* plain text */
    }
    throw new Error(detail || res.statusText);
  }
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export type Job = {
  id: string;
  external_id: string;
  client_id?: string | null;
  client_name?: string;
  title: string;
  department: string;
  description: string;
  skills: string;
  salary_range?: string;
  work_location?: string;
  job_type?: string;
  recruitment_urgency?: string;
  preferred_onboarding_date?: string | null;
  min_experience: number | null;
  education_required: string;
  status: string;
  created_at: string;
};

export type ClientDto = {
  id: string;
  name: string;
  contact_person?: string;
  email?: string;
  company_name?: string;
  active_jobs?: number;
  status: string;
  created_at: string;
};

export type JobAttachmentDto = {
  id: string;
  job_external_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type CandidateDto = {
  id: string;
  external_id: string;
  full_name: string;
  title: string;
  role_label: string;
  role_fine?: string;
  skills: string;
  filename: string;
  years_experience: number | null;
  highest_degree: string;
  certifications?: string;
  education_lines?: string;
  status?: string;
  contact_email?: string;
  created_at: string;
  /** Cohort-relative profile blend (0–100). */
  profile_percentile_score?: number | null;
  /** Mean cross-encoder match vs all jobs (0–100); 0 if no jobs or skipped. */
  avg_job_match_score?: number | null;
  /** Combined competition score (0–100). */
  competition_score?: number | null;
  /** Best cross-encoder match vs active jobs (0–100). */
  best_job_match_score?: number | null;
  best_job_external_id?: string | null;
};

export async function fetchCandidates(limit = 100): Promise<CandidateDto[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/candidates?${q}`);
  return parseJson<CandidateDto[]>(res);
}

export async function fetchCandidatesPage(params: {
  skip: number;
  limit: number;
  q?: string;
  status?: string;
  role?: string;
  sort?: string;
}): Promise<{ total: number; items: CandidateDto[] }> {
  const sp = new URLSearchParams({
    skip: String(params.skip ?? 0),
    limit: String(params.limit ?? 50),
  });
  if (params.q) sp.set("q", params.q);
  if (params.status) sp.set("status", params.status);
  if (params.role) sp.set("role", params.role);
  if (params.sort) sp.set("sort", params.sort);
  const res = await authedFetch(`${base}/api/v1/candidates/page?${sp.toString()}`);
  return parseJson(res);
}

/** Candidates page only: cohort competition scores (expensive). */
export async function fetchCandidatesScoreboard(limit = 500): Promise<CandidateDto[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/candidates/scoreboard?${q}`);
  return parseJson<CandidateDto[]>(res);
}

/** Single candidate profile (fast; no competition scoring). */
export async function fetchCandidate(candidateId: string): Promise<CandidateDto> {
  const res = await authedFetch(`${base}/api/v1/candidates/${encodeURIComponent(candidateId)}`);
  return parseJson<CandidateDto>(res);
}

export async function fetchCandidateByExternalId(externalId: string): Promise<CandidateDto> {
  const res = await authedFetch(`${base}/api/v1/candidates/by-external/${encodeURIComponent(externalId)}`);
  return parseJson<CandidateDto>(res);
}

/** Candidate profile + competition scores (expensive; same math as scoreboard). */
export async function fetchCandidateWithScores(candidateId: string): Promise<CandidateDto> {
  const res = await authedFetch(
    `${base}/api/v1/candidates/${encodeURIComponent(candidateId)}/with-scores`,
  );
  return parseJson<CandidateDto>(res);
}

export type CandidateUpdatePayload = {
  full_name?: string;
  title?: string;
  role_label?: string;
  role_fine?: string;
  skills?: string;
  years_experience?: number | null;
  highest_degree?: string;
  certifications?: string;
  education_lines?: string;
  status?: string;
  contact_email?: string;
};

export async function updateCandidate(
  candidateId: string,
  payload: CandidateUpdatePayload,
): Promise<CandidateDto> {
  const res = await authedFetch(`${base}/api/v1/candidates/${encodeURIComponent(candidateId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<CandidateDto>(res);
}

export type RankedCandidate = {
  candidate_id: string;
  cross_encoder_score: number;
  sbert_similarity: number;
  candidate_name?: string;
  candidate_title?: string;
  candidate_role?: string;
  years_experience?: number | null;
  highest_degree?: string;
  skills_summary?: string;
};

export type RankResponse = {
  job_id: string;
  candidates: RankedCandidate[];
};

export type ClassifyResponse = { label: string; probs: Record<string, number> };

export async function fetchJobs(): Promise<Job[]> {
  const res = await authedFetch(`${base}/api/v1/jobs`);
  return parseJson<Job[]>(res);
}

export async function fetchJobsPage(params: {
  skip: number;
  limit: number;
  q?: string;
  status?: string;
  client_id?: string;
  sort?: string;
}): Promise<{ total: number; items: Job[] }> {
  const sp = new URLSearchParams({
    skip: String(params.skip ?? 0),
    limit: String(params.limit ?? 50),
  });
  if (params.q) sp.set("q", params.q);
  if (params.status) sp.set("status", params.status);
  if (params.client_id) sp.set("client_id", params.client_id);
  if (params.sort) sp.set("sort", params.sort);
  const res = await authedFetch(`${base}/api/v1/jobs/page?${sp.toString()}`);
  return parseJson(res);
}

export async function fetchClients(params?: { status?: "active" | "inactive" }): Promise<ClientDto[]> {
  const sp = new URLSearchParams();
  if (params?.status) sp.set("status", params.status);
  const suffix = sp.toString() ? `?${sp.toString()}` : "";
  const res = await authedFetch(`${base}/api/v1/clients${suffix}`);
  return parseJson<ClientDto[]>(res);
}

export async function createClient(payload: {
  name: string;
  contact_person?: string;
  email?: string;
  company_name?: string;
  status?: "active" | "inactive";
}): Promise<ClientDto> {
  const res = await authedFetch(`${base}/api/v1/clients`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ClientDto>(res);
}

export async function fetchClientJobs(clientId: string): Promise<{ client: ClientDto; jobs: Job[] }> {
  const res = await authedFetch(`${base}/api/v1/clients/${encodeURIComponent(clientId)}/jobs`);
  return parseJson(res);
}

export async function updateClient(
  clientId: string,
  payload: Partial<Pick<ClientDto, "name" | "contact_person" | "email" | "company_name" | "status">>,
): Promise<ClientDto> {
  const res = await authedFetch(`${base}/api/v1/clients/${encodeURIComponent(clientId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<ClientDto>(res);
}

export async function deleteClient(clientId: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/clients/${encodeURIComponent(clientId)}`, { method: "DELETE" });
  if (!res.ok) {
    await parseJson(res);
  }
}

export async function createJob(payload: {
  external_id?: string;
  client_id?: string | null;
  title?: string;
  department?: string;
  description?: string;
  skills?: string;
  salary_range?: string;
  work_location?: string;
  job_type?: string;
  recruitment_urgency?: string;
  preferred_onboarding_date?: string | null;
  min_experience?: number | null;
  education_required?: string;
  status?: string;
}): Promise<Job> {
  const res = await authedFetch(`${base}/api/v1/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<Job>(res);
}

export async function fetchJobByExternalId(externalId: string): Promise<Job> {
  const res = await authedFetch(`${base}/api/v1/jobs/by-external/${encodeURIComponent(externalId)}`);
  return parseJson<Job>(res);
}

export async function fetchJobAttachments(jobExternalId: string): Promise<JobAttachmentDto[]> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/attachments`);
  return parseJson<JobAttachmentDto[]>(res);
}

export async function uploadJobAttachment(jobExternalId: string, file: File): Promise<JobAttachmentDto> {
  const fd = new FormData();
  fd.append("file", file, file.name);
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/attachments`, {
    method: "POST",
    body: fd,
  });
  return parseJson<JobAttachmentDto>(res);
}

export async function downloadJobAttachmentBlob(
  jobExternalId: string,
  attachmentId: string,
): Promise<{ blob: Blob; contentType: string }> {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/attachments/${encodeURIComponent(attachmentId)}`,
  );
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  const blob = await res.blob();
  const contentType = res.headers.get("Content-Type") || blob.type || "application/octet-stream";
  return { blob, contentType };
}

export async function deleteJobAttachment(jobExternalId: string, attachmentId: string): Promise<void> {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/attachments/${encodeURIComponent(attachmentId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    await parseJson(res);
  }
}

export async function updateJobByExternalId(
  externalId: string,
  payload: Partial<
    Pick<
      Job,
      | "title"
      | "client_id"
      | "department"
      | "description"
      | "skills"
      | "salary_range"
      | "work_location"
      | "job_type"
      | "recruitment_urgency"
      | "preferred_onboarding_date"
      | "min_experience"
      | "education_required"
      | "status"
    >
  >,
): Promise<Job> {
  const res = await authedFetch(`${base}/api/v1/jobs/by-external/${encodeURIComponent(externalId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson<Job>(res);
}

export async function deleteJobByExternalId(externalId: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/jobs/by-external/${encodeURIComponent(externalId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    await parseJson(res);
  }
}

export async function rankJobPreview(jobId: string, topK = 30): Promise<RankResponse> {
  const res = await authedFetch(`${base}/rank_candidates_for_job`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, top_k: topK }),
  });
  return parseJson<RankResponse>(res);
}

export async function rankAndSave(jobId: string, topK = 30) {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobId)}/rank-and-save?top_k=${topK}`,
    { method: "POST" },
  );
  return parseJson<{
    job_external_id: string;
    rankings: Array<{
      rank_position: number;
      cross_encoder_score: number;
      sbert_similarity: number;
      candidate_external_id: string;
      candidate_name: string;
      candidate_title: string;
      candidate_role: string;
      years_experience: number | null;
      highest_degree: string;
      skills_summary: string;
    }>;
    run_at: string | null;
  }>(res);
}

export async function fetchSavedRankings(jobId: string) {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobId)}/rankings`);
  return parseJson<{
    job_external_id: string;
    rankings: Array<{
      rank_position: number;
      cross_encoder_score: number;
      sbert_similarity: number;
      candidate_external_id: string;
      candidate_name: string;
      candidate_title: string;
      candidate_role: string;
      years_experience: number | null;
      highest_degree: string;
      skills_summary: string;
    }>;
    run_at: string | null;
  }>(res);
}

export type Stage1PoolRow = {
  candidate_id: string; // external id
  candidate_uuid: string;
  candidate_name: string;
  candidate_title: string;
  candidate_role: string;
  years_experience: number | null;
  highest_degree: string;
  skills_summary: string;
  sbert_score: number;
  is_shortlisted: boolean;
};

export async function fetchStage1Pool(jobExternalId: string, limit = 50) {
  const sp = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/stage1-pool?${sp.toString()}`);
  return parseJson<{ job_external_id: string; items: Stage1PoolRow[] }>(res);
}

export type ShortlistRow = Omit<Stage1PoolRow, "is_shortlisted">;

export async function fetchJobShortlist(jobExternalId: string) {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/shortlist`);
  return parseJson<{ job_external_id: string; items: ShortlistRow[] }>(res);
}

export async function updateJobShortlist(jobExternalId: string, body: { add?: string[]; remove?: string[] }) {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/shortlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJson<{ job_external_id: string; items: ShortlistRow[] }>(res);
}

export async function rankShortlist(jobExternalId: string) {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/rank-shortlist`, { method: "POST" });
  return parseJson(res);
}

export async function fetchJobApplicantStats(jobExternalId: string) {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/stats`);
  return parseJson<{
    job_external_id: string;
    total: number;
    new: number;
    screened: number;
    shortlisted: number;
    interviewed: number;
    hired: number;
  }>(res);
}

export async function updateJobApplicantStatus(jobExternalId: string, candidateExternalId: string, status: string) {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/applicants/${encodeURIComponent(candidateExternalId)}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  return parseJson<{ job_external_id: string; candidate_external_id: string; status: string }>(res);
}

export async function classifyRole(text: string): Promise<ClassifyResponse> {
  const res = await authedFetch(`${base}/classify_role`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_text: text }),
  });
  return parseJson<ClassifyResponse>(res);
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await authedFetch(`${base}/health`);
  return parseJson(res);
}

export type ActivityNotification = {
  id: string;
  kind: string;
  message: string;
  at: string;
  href?: string;
};

export type DashboardData = {
  overview: {
    candidates_total: number;
    jobs_total: number;
    new_candidates_24h: number;
    ingestions_queued: number;
    ingestions_processing: number;
    ingestions_done_24h: number;
  };
  notifications: ActivityNotification[];
};

export async function fetchDashboard(): Promise<DashboardData> {
  const res = await authedFetch(`${base}/api/v1/meta/dashboard`);
  return parseJson(res);
}

/** Poll for live activity (ingestions, new candidates, rankings, shortlist actions). */
export async function fetchActivityNotifications(): Promise<ActivityNotification[]> {
  const res = await authedFetch(`${base}/api/v1/meta/activity`);
  const j = await parseJson<{ notifications: ActivityNotification[] }>(res);
  return j.notifications;
}

export type DashboardPipelineStage = {
  key: string;
  label: string;
  count: number;
  people: Array<{ id: string; initials: string; external_id: string; name: string }>;
};

export type DashboardPieSegment = {
  key: string;
  label: string;
  count: number;
  pct: number;
  color: string;
};

export type DashboardJobChart = {
  segments: DashboardPieSegment[];
  total: number;
};

export type DashboardCandidatePreview = {
  id: string;
  external_id: string;
  full_name: string;
  /** Professional headline (matches Candidates table primary role line). */
  title: string;
  /** Fine role bucket; shown under title when set (same as Candidates page). */
  role_fine: string;
  /** Cohort-relative profile strength (0–100). */
  profile_strength: number;
  /** Best model-based match vs jobs (0–100). */
  best_job_match: number;
  status: string;
  status_raw: string;
  email: string;
};

export type DashboardWidgets = {
  pipeline: DashboardPipelineStage[];
  jobs_chart: DashboardJobChart;
  candidate_preview: DashboardCandidatePreview[];
  generated_at: string;
  /** Reserved; always false — dashboard preview uses profile cohort scores only. */
  needs_job_breadth_scores_refresh?: boolean;
};

export async function fetchDashboardWidgets(): Promise<DashboardWidgets> {
  const res = await authedFetch(`${base}/api/v1/meta/dashboard/widgets`);
  return parseJson(res);
}

/** Same candidate preview scores as fetchDashboardWidgets() (legacy; optional tooling). */
export async function fetchDashboardWidgetPreviewScores(): Promise<{
  candidate_preview: DashboardCandidatePreview[];
  generated_at: string;
}> {
  const res = await authedFetch(`${base}/api/v1/meta/dashboard/widgets/preview-scores`);
  return parseJson(res);
}

/** Fetch stored resume bytes for in-app preview or download (uses auth header). */
export async function fetchCandidateFileBlob(externalId: string): Promise<{ blob: Blob; contentType: string }> {
  const res = await authedFetch(
    `${base}/api/v1/candidates/by-external/${encodeURIComponent(externalId)}/file`,
  );
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  const blob = await res.blob();
  const contentType = res.headers.get("Content-Type") || blob.type || "application/octet-stream";
  return { blob, contentType };
}

export async function uploadResume(file: File): Promise<{
  status: string;
  text_len: number;
  candidate: CandidateDto;
}> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await authedFetch(`${base}/api/v1/uploads/resume`, {
    method: "POST",
    body: fd,
  });
  return parseJson(res);
}

// --- Async resume ingestion (bulk / extension / phone OCR) ---
export type IngestionItem = {
  id: string;
  batch_id: string;
  source: string;
  status: "queued" | "processing" | "done" | "failed" | string;
  filename: string;
  content_type: string;
  storage_path: string;
  candidate_external_id: string;
  error: string;
  created_at: string;
  updated_at: string;
};

export type IngestionBatchResponse = {
  batch_id: string;
  accepted: IngestionItem[];
  failed: IngestionItem[];
};

export type IngestionBatchStatus = {
  batch_id: string;
  total: number;
  queued: number;
  processing: number;
  done: number;
  failed: number;
  items: IngestionItem[];
};

export async function ingestBulkResumes(files: File[]): Promise<IngestionBatchResponse> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f, f.name);
  const res = await authedFetch(`${base}/api/v1/ingestions/bulk`, { method: "POST", body: fd });
  return parseJson(res);
}

export async function ingestResumeText(payload: {
  text: string;
  source?: string;
  filename?: string;
  batch_id?: string;
}): Promise<IngestionItem> {
  const res = await authedFetch(`${base}/api/v1/ingestions/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson(res);
}

export async function fetchIngestionBatchStatus(batchId: string): Promise<IngestionBatchStatus> {
  const res = await authedFetch(`${base}/api/v1/ingestions/batch/${encodeURIComponent(batchId)}`);
  return parseJson(res);
}

/** Global ingestion queue (any batch), for dashboard drill-down. */
export async function fetchRecentIngestions(
  status: "queued" | "processing" | "done",
  opts?: { sinceHours?: number; limit?: number },
): Promise<IngestionItem[]> {
  const sp = new URLSearchParams({ status });
  if (opts?.sinceHours != null) sp.set("since_hours", String(opts.sinceHours));
  if (opts?.limit != null) sp.set("limit", String(opts.limit));
  const res = await authedFetch(`${base}/api/v1/ingestions/recent?${sp.toString()}`);
  return parseJson(res);
}

export async function deleteCandidateByExternalId(externalId: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/candidates/by-external/${encodeURIComponent(externalId)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const text = await res.text();
    let detail = text || res.statusText;
    try {
      const j = JSON.parse(text) as { detail?: string };
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* plain text */
    }
    throw new Error(detail);
  }
}

/** Cross-encoder rank against all DB candidates (for uploads not in SBERT CSV). */
export async function rankFromDatabase(
  jobId: string,
  opts?: { limit?: number; topReturn?: number; persist?: boolean },
) {
  const limit = opts?.limit ?? 500;
  const topReturn = opts?.topReturn ?? 50;
  const persist = opts?.persist ?? false;
  const q = new URLSearchParams({
    limit: String(limit),
    top_return: String(topReturn),
    persist: String(persist),
  });
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobId)}/rank-database-candidates?${q}`,
    { method: "POST" },
  );
  return parseJson<{
    job_external_id: string;
    rankings: Array<{
      rank_position: number;
      cross_encoder_score: number;
      sbert_similarity: number;
      candidate_external_id: string;
      candidate_name: string;
      candidate_title: string;
      candidate_role: string;
      years_experience: number | null;
      highest_degree: string;
      skills_summary: string;
    }>;
    run_at: string | null;
  }>(res);
}

export type RankingFeedbackAction = "selected" | "shortlisted" | "rejected";

/** Log recruiter action on a ranked row (offline retraining / evaluation; not live model updates). */
export async function submitRankingFeedback(payload: {
  job_external_id: string;
  candidate_external_id: string;
  action: RankingFeedbackAction;
  rank_position_shown: number;
  model_score_at_feedback: number;
  notes?: string;
}): Promise<{
  id: string;
  job_external_id: string;
  candidate_external_id: string;
  action: string;
  rank_position_shown: number | null;
  model_score_at_feedback: number | null;
  created_at: string;
}> {
  const res = await authedFetch(`${base}/api/v1/feedback/ranking-selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      job_external_id: payload.job_external_id,
      candidate_external_id: payload.candidate_external_id,
      action: payload.action,
      rank_position_shown: payload.rank_position_shown,
      model_score_at_feedback: payload.model_score_at_feedback,
      notes: payload.notes ?? "",
    }),
  });
  return parseJson(res);
}

export async function registerUser(email: string, password: string): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/register-start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJson(res);
}

export async function loginUser(email: string, password: string): Promise<{ access_token: string }> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJson(res);
}

export async function verifyEmailCode(email: string, code: string): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  return parseJson(res);
}
