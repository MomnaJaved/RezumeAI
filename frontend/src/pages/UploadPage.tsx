import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchJobs,
  rankFromDatabase,
  uploadResume,
  type CandidateDto,
  type Job,
} from "../api";
import { useToast } from "../toast";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function copyToClipboard(text: string): Promise<void> {
  await navigator.clipboard.writeText(text);
}

export default function UploadPage() {
  const toast = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [candidate, setCandidate] = useState<CandidateDto | null>(null);
  const [uploadMeta, setUploadMeta] = useState<{ status: string; textLen: number } | null>(null);

  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [rankLoading, setRankLoading] = useState(false);
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

  const resetOutcome = useCallback(() => {
    setCandidate(null);
    setUploadMeta(null);
    setRankPreview([]);
  }, []);

  const addFiles = useCallback(
    (incoming: FileList | null) => {
      if (!incoming?.length) return;
      const next = Array.from(incoming);
      setFiles((prev) => {
        const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
        const merged = [...prev];
        for (const f of next) {
          const k = `${f.name}:${f.size}`;
          if (!seen.has(k)) {
            seen.add(k);
            merged.push(f);
          }
        }
        return merged;
      });
      resetOutcome();
    },
    [resetOutcome],
  );

  const clearAll = useCallback(() => {
    setFiles([]);
    resetOutcome();
  }, [resetOutcome]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      addFiles(e.dataTransfer.files);
    },
    [addFiles],
  );

  async function submitUpload() {
    if (!files.length) return;
    setLoading(true);
    resetOutcome();
    const ok: Array<{ candidate: CandidateDto; status: string; textLen: number }> = [];
    const failLines: string[] = [];
    try {
      for (const file of files) {
        try {
          const r = await uploadResume(file);
          ok.push({ candidate: r.candidate, status: r.status, textLen: r.text_len });
        } catch (e) {
          failLines.push(`${file.name}: ${(e as Error).message}`);
        }
      }
      if (ok.length) {
        const last = ok[ok.length - 1];
        setCandidate(last.candidate);
        setUploadMeta({ status: last.status, textLen: last.textLen });
      }
      if (failLines.length === 0) {
        if (files.length === 1 && ok[0]) {
          toast.success(
            ok[0].status === "created" ? "Candidate created in the database." : "Existing candidate updated.",
          );
        } else {
          toast.success(`${ok.length} résumé(s) parsed and saved.`);
        }
      } else if (ok.length === 0) {
        toast.error(failLines.join("\n"));
      } else {
        toast.success(`${ok.length} of ${files.length} saved. Last success shown below.`);
        toast.error(failLines.join("\n"));
      }
    } finally {
      setLoading(false);
    }
  }

  async function runRank(persist: boolean) {
    if (!jobId.trim()) {
      toast.error("Pick a job.");
      return;
    }
    setRankLoading(true);
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
      toast.success(
        persist
          ? `Saved database ranking for ${res.job_external_id} (${res.rankings.length} rows).`
          : `Preview: top ${res.rankings.length} candidates for ${res.job_external_id} (not saved).`,
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setRankLoading(false);
    }
  }

  return (
    <div>
      <h1>Add candidates</h1>
      <p className="muted">
        Upload <strong>one or many</strong> resumes in a single batch. Supported: <strong>PDF</strong>,{" "}
        <strong>DOCX</strong>, <strong>TXT</strong>, and common <strong>images</strong> (PNG, JPEG, WebP, …).
        Scanned pages need{" "}
        <a href="https://github.com/tesseract-ocr/tesseract">Tesseract</a> and <code>pytesseract</code> on the
        server. Text is stored with PII placeholders; skills and role are inferred automatically.
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
          <strong>Drop resume files here</strong> or choose below (multiple files allowed).
        </p>
        <input
          type="file"
          multiple
          className="upload-input"
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,application/pdf"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length ? (
        <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {files.map((f, i) => (
            <div key={`${f.name}-${f.size}-${i}`} className="card file-pill">
              <div>
                <strong>{f.name}</strong>
                <span className="muted"> · {formatBytes(f.size)} · {f.type || "unknown type"}</span>
              </div>
              <button
                type="button"
                className="linkish"
                onClick={() => {
                  setFiles((prev) => prev.filter((_, j) => j !== i));
                  resetOutcome();
                }}
              >
                Remove
              </button>
            </div>
          ))}
          <button type="button" className="linkish" style={{ alignSelf: "flex-start" }} onClick={clearAll}>
            Clear all
          </button>
        </div>
      ) : null}

      <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        <button type="button" className="primary" disabled={loading || !files.length} onClick={() => void submitUpload()}>
          {loading ? "Parsing…" : "Parse & save to database"}
        </button>
        <Link to="/jobs">View jobs</Link>
      </div>

      {candidate && uploadMeta ? (
        <section className="card" style={{ marginTop: "1.25rem" }}>
          <h2 style={{ marginTop: 0 }}>Last parsed candidate</h2>
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
