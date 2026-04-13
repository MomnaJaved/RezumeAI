import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchIngestionBatchStatus,
  ingestBulkResumes,
  ingestResumeText,
  deleteCandidateByExternalId,
  type IngestionBatchStatus,
  type IngestionItem,
} from "../api";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function statusColor(s: string): string {
  if (s === "done") return "#166534";
  if (s === "failed") return "#991b1b";
  if (s === "processing") return "#1d4ed8";
  return "#475569";
}

export default function IngestPage() {
  // Bulk
  const [files, setFiles] = useState<File[]>([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkErr, setBulkErr] = useState<string | null>(null);
  const [batchId, setBatchId] = useState<string>("");
  const [status, setStatus] = useState<IngestionBatchStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState<Record<string, boolean>>({});
  const [deleteNote, setDeleteNote] = useState<Record<string, string>>({});

  // Text ingest
  const [text, setText] = useState("");
  const [textBusy, setTextBusy] = useState(false);
  const [textErr, setTextErr] = useState<string | null>(null);
  const [textOk, setTextOk] = useState<string | null>(null);

  const totalBytes = useMemo(() => files.reduce((a, f) => a + f.size, 0), [files]);

  const onFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
    // Append (don’t replace) so users can pick in multiple rounds.
    const picked = Array.from(incoming);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}::${f.size}::${f.lastModified}`));
      const merged = [...prev];
      for (const f of picked) {
        const k = `${f.name}::${f.size}::${f.lastModified}`;
        if (!seen.has(k)) merged.push(f);
      }
      return merged;
    });
    setBulkErr(null);
  }, []);

  async function startBulk() {
    if (!files.length) return;
    setBulkBusy(true);
    setBulkErr(null);
    setStatus(null);
    try {
      const res = await ingestBulkResumes(files);
      setBatchId(res.batch_id);
      // Load status once immediately.
      const st = await fetchIngestionBatchStatus(res.batch_id);
      setStatus(st);
      setPolling(true);
    } catch (e) {
      setBulkErr((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  }

  async function uploadSample() {
    setBulkBusy(true);
    setBulkErr(null);
    setStatus(null);
    try {
      const sample = new File(
        [
          "John Doe\nBackend Engineer\nSkills: node.js, postgres, fastapi\nExperience: 2020-2024\nEducation: BS Computer Science\n",
        ],
        "sample_resume.txt",
        { type: "text/plain" },
      );
      const res = await ingestBulkResumes([sample]);
      setBatchId(res.batch_id);
      const st = await fetchIngestionBatchStatus(res.batch_id);
      setStatus(st);
      setPolling(true);
    } catch (e) {
      setBulkErr((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  }

  async function pollOnce(id: string) {
    const st = await fetchIngestionBatchStatus(id);
    setStatus(st);
    if (st.failed + st.done >= st.total) setPolling(false);
  }

  async function deleteCandidate(externalId: string) {
    if (!externalId.trim()) return;
    setDeleteBusy((b) => ({ ...b, [externalId]: true }));
    setDeleteNote((n) => ({ ...n, [externalId]: "" }));
    try {
      await deleteCandidateByExternalId(externalId);
      setDeleteNote((n) => ({ ...n, [externalId]: "Deleted" }));
    } catch (e) {
      setDeleteNote((n) => ({ ...n, [externalId]: (e as Error).message || "Delete failed" }));
    } finally {
      setDeleteBusy((b) => ({ ...b, [externalId]: false }));
    }
  }

  useEffect(() => {
    if (!polling || !batchId) return;
    const t = window.setInterval(() => {
      void pollOnce(batchId);
    }, 1500);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [polling, batchId]);

  async function submitText() {
    if (text.trim().length < 20) {
      setTextErr("Paste at least ~20 characters.");
      return;
    }
    setTextBusy(true);
    setTextErr(null);
    setTextOk(null);
    try {
      const ing: IngestionItem = await ingestResumeText({
        text: text.trim(),
        source: "extension",
        filename: "pasted.txt",
        batch_id: batchId || undefined,
      });
      setTextOk(`Queued: ${ing.id} (batch ${ing.batch_id})`);
      setBatchId(ing.batch_id);
      setPolling(true);
      void pollOnce(ing.batch_id);
      setText("");
    } catch (e) {
      setTextErr((e as Error).message);
    } finally {
      setTextBusy(false);
    }
  }

  return (
    <div>
      <h1>Resume ingestion (bulk / phone OCR / extension)</h1>
      <p className="muted">
        This page calls the async ingestion APIs: bulk upload uses <code>/api/v1/ingestions/bulk</code> and paste-text
        uses <code>/api/v1/ingestions/text</code>. Polling shows processing progress.
      </p>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Bulk upload</h2>
        <p className="muted">
          Upload multiple PDFs/DOCX/TXT or images. For phone scanning, you can choose images from camera/gallery.
        </p>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,application/pdf,image/*"
          onClick={(e) => {
            // Allow selecting the same file again in the picker.
            (e.currentTarget as HTMLInputElement).value = "";
          }}
          onChange={(e) => onFiles(e.target.files)}
          disabled={bulkBusy}
        />
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" className="primary" disabled={bulkBusy || files.length === 0} onClick={() => void startBulk()}>
            {bulkBusy ? "Uploading…" : `Upload ${files.length || ""} file(s)`}
          </button>
          <button type="button" disabled={bulkBusy} onClick={() => void uploadSample()}>
            Upload sample (debug)
          </button>
          <button type="button" disabled={bulkBusy || files.length === 0} onClick={() => setFiles([])}>
            Clear
          </button>
          <Link to="/upload">Single upload (legacy)</Link>
        </div>

        {files.length ? (
          <div className="card" style={{ marginTop: "0.75rem" }}>
            <div className="muted">
              Total: <strong>{files.length}</strong> files · <strong>{formatBytes(totalBytes)}</strong>
            </div>
            <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.2rem" }}>
              {files.slice(0, 12).map((f) => (
                <li key={`${f.name}-${f.size}`}>{f.name}</li>
              ))}
              {files.length > 12 ? <li className="muted">…and {files.length - 12} more</li> : null}
            </ul>
          </div>
        ) : null}

        {bulkErr ? (
          <div className="banner banner-error" role="alert" style={{ marginTop: "0.75rem" }}>
            {bulkErr}
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Paste text (Chrome extension / LinkedIn / OCR text)</h2>
        <textarea
          rows={8}
          placeholder="Paste resume text or a copied LinkedIn profile here…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={textBusy}
        />
        <div style={{ marginTop: "0.75rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" className="primary" disabled={textBusy || text.trim().length < 20} onClick={() => void submitText()}>
            {textBusy ? "Submitting…" : "Queue ingest"}
          </button>
          <button type="button" disabled={textBusy || !text} onClick={() => setText("")}>
            Clear
          </button>
        </div>
        {textErr ? (
          <div className="banner banner-error" role="alert" style={{ marginTop: "0.75rem" }}>
            {textErr}
          </div>
        ) : null}
        {textOk ? (
          <div className="banner banner-info" role="status" style={{ marginTop: "0.75rem" }}>
            {textOk}
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Batch status</h2>
        <div className="mono-row" style={{ marginBottom: "0.5rem" }}>
          <label htmlFor="batch-id" style={{ marginBottom: 0 }}>
            Batch ID
          </label>
          <input
            id="batch-id"
            value={batchId}
            placeholder="paste batch_id here…"
            onChange={(e) => setBatchId(e.target.value)}
          />
          <button type="button" disabled={!batchId.trim()} onClick={() => void pollOnce(batchId.trim())}>
            Refresh
          </button>
          <button type="button" disabled={!batchId.trim()} onClick={() => setPolling((p) => !p)}>
            {polling ? "Stop polling" : "Start polling"}
          </button>
        </div>

        {status ? (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Total: <strong>{status.total}</strong> · queued {status.queued} · processing {status.processing} · done{" "}
              {status.done} · failed {status.failed}
            </p>
            <div style={{ overflow: "auto" }}>
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Status</th>
                    <th>Candidate ID</th>
                    <th>Actions</th>
                    <th>Error</th>
                  </tr>
                </thead>
                <tbody>
                  {status.items.map((it) => (
                    <tr key={it.id}>
                      <td style={{ maxWidth: "18rem", wordBreak: "break-word" }}>{it.filename || "—"}</td>
                      <td style={{ color: statusColor(it.status), fontWeight: 600 }}>{it.status}</td>
                      <td className="muted" style={{ maxWidth: "10rem", wordBreak: "break-all" }}>
                        {it.candidate_external_id || "—"}
                      </td>
                      <td style={{ minWidth: "10rem" }}>
                        {it.candidate_external_id && it.status === "done" ? (
                          <>
                            <button
                              type="button"
                              disabled={!!deleteBusy[it.candidate_external_id]}
                              onClick={() => void deleteCandidate(it.candidate_external_id)}
                            >
                              Delete candidate
                            </button>
                            {deleteNote[it.candidate_external_id] ? (
                              <div
                                className={deleteNote[it.candidate_external_id] === "Deleted" ? "muted" : "error"}
                                style={{ fontSize: "0.75rem", marginTop: "0.25rem", wordBreak: "break-word" }}
                              >
                                {deleteNote[it.candidate_external_id]}
                              </div>
                            ) : null}
                          </>
                        ) : (
                          <span className="muted">—</span>
                        )}
                      </td>
                      <td className="error" style={{ maxWidth: "18rem", wordBreak: "break-word" }}>
                        {it.error || ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="muted">Upload a batch (or paste a batch id) to see status here.</p>
        )}
      </section>
    </div>
  );
}

