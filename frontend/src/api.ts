import { getStoredToken } from "./auth";

const base = import.meta.env.VITE_API_BASE ?? "";

async function authedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const token = getStoredToken();
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(input, { ...init, headers });
  if (res.status === 401 && token) {
    // Token expired or invalidated — signal the auth layer to clear the session.
    window.dispatchEvent(new CustomEvent("auth:expired"));
  }
  return res;
}

function formatFastApiDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item && typeof (item as { msg: unknown }).msg === "string") {
          return (item as { msg: string }).msg;
        }
        return null;
      })
      .filter(Boolean) as string[];
    if (msgs.length) return msgs.join(" ");
    try {
      return JSON.stringify(detail);
    } catch {
      return "Request failed";
    }
  }
  if (detail && typeof detail === "object" && "message" in detail && typeof (detail as { message: unknown }).message === "string") {
    return (detail as { message: string }).message;
  }
  try {
    return typeof detail === "undefined" ? "" : JSON.stringify(detail);
  } catch {
    return "Request failed";
  }
}

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const j = JSON.parse(text) as { detail?: unknown; error?: string };
      if (j.detail !== undefined && j.detail !== null) detail = formatFastApiDetail(j.detail);
      else if (typeof j.error === "string" && j.error.trim()) detail = j.error.trim();
    } catch {
      /* plain text */
    }
    throw new Error((detail || "").trim() || res.statusText);
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
  /** Query-time status (e.g. `new` ages to screened after 7 days). */
  status_effective?: string;
  /** When title is Fresher, optional skills-aligned role hint from the backend. */
  skills_role_hint?: string | null;
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
  best_job_title?: string | null;
  best_job_department?: string | null;
  best_job_client_name?: string | null;
  best_job_client_company?: string | null;
  best_job_client_contact?: string | null;
  best_job_client_email?: string | null;
  /** Pool type: true = public (portal applicant), false = private (recruiter upload). */
  is_public?: boolean;
};

/** Best stored cross-encoder match as 0–100 (handles legacy 0–1 scale in older rows). */
export function normalizedBestJobMatchPercent(raw: number | null | undefined): number | null {
  if (raw == null || Number.isNaN(Number(raw))) return null;
  let n = Number(raw);
  if (n > 0 && n <= 1) n *= 100;
  return Math.max(0, Math.min(100, Math.round(n)));
}

export type RankingExplanationDto = {
  skills_match_ratio: number;
  experience_match: number;
  education_match: number;
  heuristic_weak_score: number;
  missing_skills: string[];
  cross_encoder_score: number;
};

export type JobSavedRankingRow = {
  rank_position: number;
  cross_encoder_score: number;
  sbert_similarity?: number;
  candidate_external_id: string;
  candidate_name: string;
  candidate_title: string;
  candidate_role?: string;
  years_experience: number | null;
  highest_degree: string;
  skills_summary: string;
  explanation?: RankingExplanationDto | null;
};

/** Saved rankings API payload (GET /rankings, POST rank-and-save, rank-shortlist, etc.). */
export type JobRankingsApiResponse = {
  job_external_id: string;
  rankings: JobSavedRankingRow[];
  run_at: string | null;
  top_candidate_insight?: string | null;
};

export type CandidateCompareSnapshot = {
  id: string;
  external_id: string;
  full_name: string;
  title: string;
  role_label: string;
  role_fine?: string | null;
  skills: string;
  years_experience: number | null;
  highest_degree: string;
  certifications?: string | null;
  status?: string | null;
  contact_email?: string | null;
  best_job_match_score?: number | null;
  best_job_external_id?: string | null;
  best_job_title?: string | null;
  best_job_department?: string | null;
  best_job_client_name?: string | null;
  best_job_client_company?: string | null;
  best_job_client_contact?: string | null;
  best_job_client_email?: string | null;
};

export async function compareCandidates(candidateIds: string[]): Promise<{ candidates: CandidateCompareSnapshot[] }> {
  const res = await authedFetch(`${base}/api/v1/candidates/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: candidateIds }),
  });
  return parseJson(res);
}

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

export async function rankAndSave(jobId: string, topK = 30): Promise<JobRankingsApiResponse> {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobId)}/rank-and-save?top_k=${topK}`,
    { method: "POST" },
  );
  return parseJson<JobRankingsApiResponse>(res);
}

/**
 * Canonical match trigger: computes SBERT + cross-encoder, persists results, and
 * refreshes best_job_match_score for all affected candidates.
 * Use this instead of match-batch whenever scores must be stored and visible across views.
 */
export async function triggerMatchCandidates(jobId: string, topK = 50): Promise<JobRankingsApiResponse> {
  const res = await authedFetch(
    `${base}/api/v1/jobs/${encodeURIComponent(jobId)}/match-candidates?top_k=${topK}`,
    { method: "POST" },
  );
  return parseJson<JobRankingsApiResponse>(res);
}

/** Fetch latest persisted match scores for a job (single source of truth). */
export async function fetchJobMatches(jobId: string): Promise<JobRankingsApiResponse> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobId)}/matches`);
  return parseJson<JobRankingsApiResponse>(res);
}

export type CandidateMatchItem = {
  job_external_id: string;
  job_title: string;
  job_status: string;
  match_score: number;
  sbert_similarity: number;
  rank_position: number;
  run_at: string | null;
  explanation?: RankingExplanationDto | null;
};

export type CandidateMatchesResponse = {
  candidate_id: string;
  candidate_external_id: string;
  best_match_score: number | null;
  items: CandidateMatchItem[];
};

/** Fetch latest persisted job match scores for a candidate (single source of truth). */
export async function fetchCandidateMatches(candidateUuid: string, limit = 20): Promise<CandidateMatchesResponse> {
  const sp = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/candidates/${encodeURIComponent(candidateUuid)}/matches?${sp}`);
  return parseJson<CandidateMatchesResponse>(res);
}

export async function fetchSavedRankings(jobId: string): Promise<JobRankingsApiResponse> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobId)}/rankings`);
  return parseJson<JobRankingsApiResponse>(res);
}

export type Stage1PoolRow = {
  candidate_id: string; // external id
  candidate_uuid: string;
  candidate_name: string;
  candidate_title: string;
  candidate_role: string;
  years_experience: number | null;
  highest_degree: string;
  certifications?: string;
  skills_summary: string;
  sbert_score: number;
  is_shortlisted: boolean;
  candidate_status?: string;
  /** Pool type: true = public (portal applicant), false = private (recruiter upload). */
  is_public?: boolean;
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

export async function rankShortlist(jobExternalId: string): Promise<JobRankingsApiResponse> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/rank-shortlist`, { method: "POST" });
  return parseJson<JobRankingsApiResponse>(res);
}

export async function matchOneCandidate(jobExternalId: string, candidateExternalId: string): Promise<{
  job_external_id: string;
  candidate_id: string;
  rank_position: number;
  cross_encoder_score: number;
}> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/match-one`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_id: candidateExternalId }),
  });
  return parseJson(res);
}

export async function matchCandidatesBatch(jobExternalId: string, candidateExternalIds: string[]): Promise<{
  job_external_id: string;
  items: Array<{ candidate_id: string; rank_position: number; cross_encoder_score: number }>;
  top_candidate_insight?: string;
}> {
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/match-batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ candidate_ids: candidateExternalIds }),
  });
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
    interviewing: number;
    /** @deprecated same as interviewing */
    interviewed?: number;
    hired: number;
    rejected: number;
  }>(res);
}

export type JobApplicantRow = {
  candidate_external_id: string;
  candidate_name: string;
  candidate_title: string;
  applicant_status: string;
  applicant_status_effective: string;
  cross_encoder_score: number | null;
  retrieval_similarity: number | null;
  rank_position: number | null;
  in_saved_ranking: boolean;
};

export async function fetchJobApplicants(jobExternalId: string, limit = 500) {
  const sp = new URLSearchParams({ limit: String(limit) });
  const res = await authedFetch(`${base}/api/v1/jobs/${encodeURIComponent(jobExternalId)}/applicants?${sp.toString()}`);
  return parseJson<{ job_external_id: string; items: JobApplicantRow[] }>(res);
}

export type CandidateJobEvaluationRow = {
  job_external_id: string;
  job_title: string;
  applicant_status: string | null;
  applicant_status_effective: string | null;
  retrieval_similarity: number | null;
  cross_encoder_score: number | null;
  rank_position: number | null;
  in_saved_ranking: boolean;
  brief_reason: string | null;
};

export async function fetchCandidateJobEvaluations(candidateUuid: string) {
  const res = await authedFetch(`${base}/api/v1/candidates/${encodeURIComponent(candidateUuid)}/job-evaluations`);
  return parseJson<{ candidate_id: string; candidate_external_id: string; items: CandidateJobEvaluationRow[] }>(res);
}

// Canonical 7 pipeline status values — mirrors STORAGE_APPLICANT_STATUSES on the backend.
export const CANDIDATE_STATUSES = [
  "new",
  "screened",
  "shortlisted",
  "interviewing",
  "selected",
  "hired",
  "rejected",
] as const;

export type CandidateStatus = (typeof CANDIDATE_STATUSES)[number];

/**
 * Dedicated status-update endpoint. This is the ONLY function that should be called
 * when changing a candidate's pipeline status from any UI view.
 * AI/ranking logic must never call this.
 */
export async function updateCandidateStatus(
  externalId: string,
  status: CandidateStatus | string,
): Promise<{ external_id: string; status: string }> {
  const res = await authedFetch(
    `${base}/api/v1/candidates/${encodeURIComponent(externalId)}/status`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  return parseJson<{ external_id: string; status: string }>(res);
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

export type InboxTab = "all" | "alerts" | "candidates";

export type InboxItem = {
  id: string;
  kind: string;
  message: string;
  at: string;
  href?: string | null;
  read: boolean;
  tabs: string[];
  direct: boolean;
  sender_email?: string | null;
  direction?: string | null;
  peer_email?: string | null;
  chat_scope?: string | null;
  peer_display_name?: string | null;
  peer_profile_path?: string | null;
};

export async function fetchInbox(): Promise<InboxItem[]> {
  const res = await authedFetch(`${base}/api/v1/inbox`);
  return parseJson<InboxItem[]>(res);
}

export async function inboxMarkRead(ids: string[]): Promise<{ updated: number }> {
  const res = await authedFetch(`${base}/api/v1/inbox/mark-read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  return parseJson(res);
}

export async function inboxMarkUnread(ids: string[]): Promise<{ updated: number }> {
  const res = await authedFetch(`${base}/api/v1/inbox/mark-unread`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  return parseJson(res);
}

export async function inboxMarkAllRead(tab: InboxTab): Promise<{ updated: number }> {
  const res = await authedFetch(`${base}/api/v1/inbox/mark-all-read`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tab }),
  });
  return parseJson(res);
}

export async function inboxMarkAllUnread(tab: InboxTab): Promise<{ updated: number }> {
  const res = await authedFetch(`${base}/api/v1/inbox/mark-all-unread`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tab }),
  });
  return parseJson(res);
}

export async function inboxSendMessage(body: {
  to_email: string;
  body: string;
  subject?: string;
  chat_scope?: "general" | "candidates" | "clients";
}): Promise<InboxItem> {
  const res = await authedFetch(`${base}/api/v1/inbox/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

export async function inboxDeleteMessage(messageId: string, mode: "everyone" | "me"): Promise<void> {
  const id = messageId.startsWith("msg-") ? messageId.slice(4) : messageId;
  const res = await authedFetch(`${base}/api/v1/inbox/messages/${encodeURIComponent(id)}/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
  if (!res.ok) await parseJson(res);
}

export async function inboxDeleteThread(body: {
  peer_email: string;
  chat_scope: "general" | "candidates" | "clients";
}): Promise<{ deleted: number }> {
  const res = await authedFetch(`${base}/api/v1/inbox/thread/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return parseJson(res);
}

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

// ── Settings / Profile ───────────────────────────────────────────────────────

export type UserProfile = {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  address: string;
  company: string;
  available_hours: string;
  role_label: string;
  avatar_data: string | null;
  two_factor_enabled?: boolean;
  account_role?: string;
};

export async function fetchMyProfile(): Promise<UserProfile> {
  const res = await authedFetch(`${base}/api/v1/auth/me`);
  return parseJson<UserProfile>(res);
}

export async function updateMyProfile(data: Partial<Omit<UserProfile, "id" | "email">> & { two_factor_enabled?: boolean }): Promise<UserProfile> {
  const res = await authedFetch(`${base}/api/v1/auth/me`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return parseJson<UserProfile>(res);
}

export async function changePassword(current_password: string, new_password: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/auth/change-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current_password, new_password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Password change failed" }));
    throw new Error(err.detail || "Password change failed");
  }
}

/** Permanently delete the signed-in account (requires correct password). */
export async function deleteAccount(password: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/auth/delete-account`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    let detail = "Account deletion failed";
    try {
      const err = await res.json();
      detail = formatFastApiDetail(err.detail) || detail;
    } catch {
      /* plain */
    }
    throw new Error(detail);
  }
}

export type ReportsKpi = {
  total_jobs: number;
  total_candidates: number;
  hires: number;
  avg_hire_time_days: number;
};

export type ReportsPipeline = {
  new: number;
  screened: number;
  shortlisted: number;
  interviewing: number;
  /** Legacy; always 0 — selected is folded into shortlisted (same as dashboard). */
  selected?: number;
  hired: number;
  rejected: number;
  total: number;
};

export type ReportsJobPerf = {
  job_external_id: string;
  job_title: string;
  avg_match_score: number;
  hires: number;
};

export type ReportsData = {
  kpi: ReportsKpi;
  pipeline: ReportsPipeline;
  job_performance: ReportsJobPerf[];
  time_saved_pct: number;
  shortlist_accuracy_pct: number;
  ai_screening_pct: number;
  manual_screening_pct: number;
  clients: { id: string; name: string }[];
  jobs_list: { external_id: string; title: string }[];
};

export async function fetchReportsData(params: {
  client_id?: string;
  date_from?: string;
  job_external_id?: string;
}): Promise<ReportsData> {
  const sp = new URLSearchParams();
  if (params.client_id) sp.set("client_id", params.client_id);
  if (params.date_from) sp.set("date_from", params.date_from);
  if (params.job_external_id) sp.set("job_external_id", params.job_external_id);
  const res = await authedFetch(`${base}/api/v1/analytics/reports?${sp.toString()}`);
  return parseJson<ReportsData>(res);
}

/** Poll for live activity (ingestions, new candidates, rankings, shortlist actions). */
export async function fetchActivityNotifications(): Promise<ActivityNotification[]> {
  const res = await authedFetch(`${base}/api/v1/meta/activity`);
  const j = await parseJson<{ notifications: ActivityNotification[] }>(res);
  return j.notifications;
}

/** Clear all activity notifications for the current recruiter's workspace. */
export async function clearActivityNotifications(): Promise<void> {
  await authedFetch(`${base}/api/v1/meta/activity`, { method: "DELETE" });
}

/** Log a custom activity event visible in the inbox and notification feed. */
export async function logActivity(kind: string, message: string, href?: string): Promise<void> {
  await authedFetch(`${base}/api/v1/meta/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, message, href: href ?? "" }),
  });
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

export async function registerUser(
  email: string,
  password: string,
  account_role: "recruiter" | "candidate" = "recruiter",
): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/register-start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, account_role }),
  });
  return parseJson(res);
}

export type LoginResult =
  | { access_token: string; requires_otp?: false; otp_challenge_id?: null; account_role?: string | null }
  | { requires_otp: true; otp_challenge_id: string; access_token?: null };

export async function loginUser(email: string, password: string): Promise<LoginResult> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return parseJson(res);
}

export async function requestForgotPassword(email: string): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return parseJson(res);
}

export async function resetPasswordWithCode(email: string, code: string, new_password: string): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code, new_password }),
  });
  return parseJson(res);
}

export async function completeLoginOtp(challengeId: string, code: string): Promise<{ access_token: string; account_role?: string | null }> {
  const res = await fetch(`${base}/api/v1/auth/login-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge_id: challengeId, code }),
  });
  return parseJson(res);
}

export type CandidateMe = {
  linked: boolean;
  candidate_id: string | null;
  external_id: string | null;
  full_name: string;
  title?: string;
  status?: string;
  best_job_match_score?: number | null;
  best_job_external_id?: string;
  email: string;
};

export async function fetchCandidateMe(): Promise<CandidateMe> {
  const res = await authedFetch(`${base}/api/v1/candidate/me`);
  return parseJson(res);
}

export type CandidateJobListItem = {
  id: string;
  external_id: string;
  title: string;
  department: string;
  work_location: string;
  job_type: string;
  salary_range: string;
  client_display: string;
  created_at: string;
  applied?: boolean;
};

export async function fetchCandidateJobs(params: {
  role_q?: string;
  work_location?: string;
  country?: string;
  city?: string;
  skip?: number;
  limit?: number;
}): Promise<{ total: number; items: CandidateJobListItem[] }> {
  const sp = new URLSearchParams();
  if (params.role_q) sp.set("role_q", params.role_q);
  if (params.work_location) sp.set("work_location", params.work_location);
  if (params.country) sp.set("country", params.country);
  if (params.city) sp.set("city", params.city);
  if (params.skip != null) sp.set("skip", String(params.skip));
  if (params.limit != null) sp.set("limit", String(params.limit));
  const res = await authedFetch(`${base}/api/v1/candidate/jobs?${sp.toString()}`);
  return parseJson(res);
}

export async function candidateApplyToJob(externalId: string): Promise<{ status: string; applicant_status?: string }> {
  const res = await authedFetch(`${base}/api/v1/candidate/jobs/${encodeURIComponent(externalId)}/apply`, {
    method: "POST",
  });
  return parseJson(res);
}

export type CandidateApplicationRow = {
  job_external_id: string;
  job_title: string;
  company: string;
  status: string;
  updated_at: string;
  rank_position: number | null;
  match_score: number | null;
};

export async function fetchCandidateApplications(): Promise<{ items: CandidateApplicationRow[] }> {
  const res = await authedFetch(`${base}/api/v1/candidate/applications`);
  return parseJson(res);
}

export type CandidateProfilePatch = {
  full_name?: string;
  title?: string;
  skills?: string;
  years_experience?: number | null;
};

export async function updateCandidateProfile(patch: CandidateProfilePatch): Promise<{ status: string }> {
  const res = await authedFetch(`${base}/api/v1/candidate/profile`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return parseJson(res);
}

export type AuthSessionRow = {
  id: string;
  device_label: string;
  location_label: string;
  ip_address: string;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
};

export async function fetchAuthSessions(): Promise<AuthSessionRow[]> {
  const res = await authedFetch(`${base}/api/v1/auth/sessions`);
  return parseJson(res);
}

export async function deleteAuthSession(sessionId: string): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || "Failed to revoke session");
  }
}

export async function deleteAllAuthSessions(): Promise<void> {
  const res = await authedFetch(`${base}/api/v1/auth/sessions`, { method: "DELETE" });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || "Failed to sign out all devices");
  }
}

export async function verifyEmailCode(email: string, code: string): Promise<{ status: string }> {
  const res = await fetch(`${base}/api/v1/auth/verify-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code }),
  });
  return parseJson(res);
}
