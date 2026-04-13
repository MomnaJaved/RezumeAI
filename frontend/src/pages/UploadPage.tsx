import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchJobs,
  rankFromDatabase,
  uploadResume,
  type CandidateDto,
  type Job,
} from "../api";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<CandidateDto | null>(null);
  const [uploadMeta, setUploadMeta] = useState<{ status: string; textLen: number } | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [rankLoading, setRankLoading] = useState(false);
  const [rankErr, setRankErr] = useState<string | null>(null);
  const [rankPreview, setRankPreview] = useState<
    Array<{
      rank_position: number;
      candidate_external_id: string;
      candidate_name: string;
      cross_encoder_score: number;
    }>
  >([]);

  useEffect(() => {
    fetchJobs()
      .then((list) => {
        setJobs(list);
        setJobId((prev) => (prev || (list[0]?.external_id ?? "")));
      })
      .catch(() => setJobs([]));
  }, []);

  const onFile = useCallback((f: File | null) => {
    setFile(f);
    setErr(null);
    setMsg(null);
    setCandidate(null);
    setUploadMeta(null);
    setRankPreview([]);
    setRankErr(null);
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      const f = e.dataTransfer.files?.[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  async function submitUpload() {
    if (!file) return;
    setLoading(true);
    setErr(null);
    setMsg(null);
    setCandidate(null);
    setUploadMeta(null);
    setRankPreview([]);
    try {
      const r = await uploadResume(file);
      setCandidate(r.candidate);
      setUploadMeta({ status: r.status, textLen: r.text_len });
      setMsg(r.status === "created" ? "Candidate created in the database." : "Existing candidate updated.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function runRank(persist: boolean) {
    if (!jobId.trim()) {
      setRankErr("Pick a job.");
      return;
    }
    setRankLoading(true);
    setRankErr(null);
    setRankPreview([]);
    try {
      const res = await rankFromDatabase(jobId.trim(), {
        limit: 800,
        topReturn: 50,
        persist,
      });
      setRankPreview(
        res.rankings.map((row) => ({
          rank_position: row.rank_position,
          candidate_external_id: row.candidate_external_id,
          candidate_name: row.candidate_name,
          cross_encoder_score: row.cross_encoder_score,
        })),
      );
      setMsg(
        persist
          ? `Saved database ranking for ${res.job_external_id} (${res.rankings.length} rows).`
          : `Preview: top ${res.rankings.length} candidates for ${res.job_external_id} (not saved).`,
      );
    } catch (e) {
      setRankErr((e as Error).message);
    } finally {
      setRankLoading(false);
    }
  }

  return (
    <div>
      <h1>Upload resume</h1>
      <p className="muted">
        Supported: <strong>PDF</strong>, <strong>DOCX</strong>, <strong>TXT</strong>, and common{" "}
        <strong>images</strong> (PNG, JPEG, WebP, …). Scanned pages need{" "}
        <a href="https://github.com/tesseract-ocr/tesseract">Tesseract</a> and{" "}
        <code>pytesseract</code> on the server. Text is stored with PII placeholders; skills and role are
        inferred automatically.
      </p>

      <div
        className={`upload-zone ${dragActive ? "upload-zone-active" : ""}`}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
      >
        <p>
          <strong>Drop a file here</strong> or choose below.
        </p>
        <input
          type="file"
          className="upload-input"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,application/pdf"
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file ? (
        <div className="card file-pill">
          <div>
            <strong>{file.name}</strong>
            <span className="muted"> · {formatBytes(file.size)} · {file.type || "unknown type"}</span>
          </div>
          <button type="button" className="linkish" onClick={() => onFile(null)}>
            Clear
          </button>
        </div>
      ) : null}

      <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="primary" disabled={loading || !file} onClick={() => void submitUpload()}>
          {loading ? "Parsing…" : "Parse & save to database"}
        </button>
        <Link to="/jobs">View jobs</Link>
      </div>

      {err ? (
        <div className="banner banner-error" role="alert">
          {err}
        </div>
      ) : null}
      {msg && !err ? (
        <div className="banner banner-info" role="status">
          {msg}
        </div>
      ) : null}

      {candidate && uploadMeta ? (
        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h2 style={{ marginTop: 0 }}>Parsed candidate</h2>
          <dl className="field-grid">
            <dt>External ID</dt>
            <dd className="mono-row">
              <code>{candidate.external_id}</code>
              <button type="button" className="small-btn" onClick={() => void copyToClipboard(candidate.external_id)}>
                Copy
              </button>
            </dd>
            <dt>Status</dt>
            <dd>{uploadMeta.status}</dd>
            <dt>Chars stored</dt>
            <dd>{uploadMeta.textLen}</dd>
            <dt>Display name</dt>
            <dd>{candidate.full_name || "—"}</dd>
            <dt>Headline / title</dt>
            <dd>{candidate.title || "—"}</dd>
            <dt>Role (model)</dt>
            <dd>{candidate.role_label || "—"}</dd>
            <dt>Filename</dt>
            <dd>{candidate.filename}</dd>
            <dt>Skills (summary)</dt>
            <dd className="skills-dd">{candidate.skills || "—"}</dd>
            <dt>Years experience</dt>
            <dd>{candidate.years_experience ?? "—"}</dd>
            <dt>Highest degree</dt>
            <dd>{candidate.highest_degree || "—"}</dd>
            <dt>Created</dt>
            <dd>{new Date(candidate.created_at).toLocaleString()}</dd>
          </dl>
        </section>
      ) : null}

      <section className="card" style={{ marginTop: "1.5rem" }}>
        <h2 style={{ marginTop: 0 }}>Rank against a job (database mode)</h2>
        <p className="muted">
          Best automated prior for fit: cross-encoder on the <strong>full database pool</strong> (includes this
          upload). No SBERT shortlist, so nobody is dropped before scoring. Open a job for more actions:{" "}
          {jobId ? <Link to={`/jobs/${encodeURIComponent(jobId)}`}>job {jobId}</Link> : <Link to="/jobs">jobs</Link>}.
        </p>
        <label htmlFor="job-select">Job</label>
        <select
          id="job-select"
          value={jobId}
          onChange={(e) => setJobId(e.target.value)}
          disabled={!jobs.length}
        >
          {jobs.length === 0 ? (
            <option value="">No jobs in DB — sync CSV or create via API</option>
          ) : (
            jobs.map((j) => (
              <option key={j.id} value={j.external_id}>
                {j.external_id} — {j.title || "untitled"}
              </option>
            ))
          )}
        </select>
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button
            type="button"
            disabled={rankLoading || !jobId || !jobs.length}
            onClick={() => void runRank(false)}
          >
            {rankLoading ? "Ranking…" : "Preview top 50"}
          </button>
          <button
            type="button"
            className="primary"
            disabled={rankLoading || !jobId || !jobs.length}
            onClick={() => void runRank(true)}
          >
            Save ranking to DB
          </button>
        </div>
        {rankErr ? <p className="error">{rankErr}</p> : null}
        {rankPreview.length > 0 ? (
          <div style={{ marginTop: "1rem", overflow: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Candidate</th>
                  <th>Name</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {rankPreview.map((row) => (
                  <tr
                    key={row.candidate_external_id}
                    style={
                      candidate && row.candidate_external_id === candidate.external_id
                        ? { background: "#eff6ff" }
                        : undefined
                    }
                  >
                    <td>{row.rank_position}</td>
                    <td className="muted mono-tiny">{row.candidate_external_id}</td>
                    <td>{row.candidate_name || "—"}</td>
                    <td>{row.cross_encoder_score.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {candidate ? (
              <p className="muted" style={{ marginTop: "0.5rem" }}>
                Highlighted row = the candidate you just uploaded (if they appear in the top 50).
              </p>
            ) : null}
          </div>
        ) : null}
      </section>
    </div>
  );
}
