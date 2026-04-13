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
  title: string;
  department: string;
  description: string;
  skills: string;
  min_experience: number | null;
  education_required: string;
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
  created_at: string;
  /** Cohort-relative profile blend (0–100). */
  profile_percentile_score?: number | null;
  /** Mean cross-encoder match vs all jobs (0–100); 0 if no jobs or skipped. */
  avg_job_match_score?: number | null;
  /** Combined competition score (0–100). */
  competition_score?: number | null;
};

export async function fetchCandidates(limit = 100): Promise<CandidateDto[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/candidates?${q}`);
  return parseJson<CandidateDto[]>(res);
}

/** Candidates page only: cohort competition scores (expensive). */
export async function fetchCandidatesScoreboard(limit = 500): Promise<CandidateDto[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/candidates/scoreboard?${q}`);
  return parseJson<CandidateDto[]>(res);
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

export async function fetchJobByExternalId(externalId: string): Promise<Job> {
  const res = await authedFetch(`${base}/api/v1/jobs/by-external/${encodeURIComponent(externalId)}`);
  return parseJson<Job>(res);
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
