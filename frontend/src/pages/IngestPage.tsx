import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import DashFrame from "../DashFrame";
import {
  fetchIngestionBatchStatus,
  ingestBulkResumes,
  ingestResumeText,
  deleteCandidateByExternalId,
  type IngestionBatchStatus,
} from "../api";
import { useToast } from "../toast";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function rowStatusClass(s: string): string {
  if (s === "done") return "add-cand-row-status add-cand-row-status--done";
  if (s === "failed") return "add-cand-row-status add-cand-row-status--failed";
  if (s === "processing") return "add-cand-row-status add-cand-row-status--processing";
  return "add-cand-row-status add-cand-row-status--muted";
}

const MIN_PASTE_CHARS = 80;

export default function IngestPage() {
  const toast = useToast();
  const [files, setFiles] = useState<File[]>([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [batchId, setBatchId] = useState<string>("");
  const [status, setStatus] = useState<IngestionBatchStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState<Record<string, boolean>>({});
  const [deleteNote, setDeleteNote] = useState<Record<string, string>>({});
  const [pasteText, setPasteText] = useState("");
  const [pasteFilename, setPasteFilename] = useState("linkedin-profile.txt");
  const [pasteBusy, setPasteBusy] = useState(false);

  const totalBytes = useMemo(() => files.reduce((a, f) => a + f.size, 0), [files]);

  const onFiles = useCallback((incoming: FileList | null) => {
    if (!incoming) return;
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
  }, []);

  async function startBulk() {
    if (!files.length) return;
    setBulkBusy(true);
    setStatus(null);
    try {
      const res = await ingestBulkResumes(files);
      setBatchId(res.batch_id);
      const st = await fetchIngestionBatchStatus(res.batch_id);
      setStatus(st);
      setPolling(true);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  }

  async function startPasteIngest() {
    const text = pasteText.trim();
    if (text.length < MIN_PASTE_CHARS) {
      toast.error(`Paste at least ${MIN_PASTE_CHARS} characters (API needs enough text to parse skills and experience).`);
      return;
    }
    setPasteBusy(true);
    try {
      const item = await ingestResumeText({
        text,
        source: "web_ui",
        filename: (pasteFilename || "profile.txt").trim() || "profile.txt",
      });
      setBatchId(item.batch_id);
      const st = await fetchIngestionBatchStatus(item.batch_id);
      setStatus(st);
      setPolling(true);
      setPasteText("");
      toast.success("Text ingestion queued — status updates below.");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setPasteBusy(false);
    }
  }

  async function pollOnce(id: string) {
    const prev = status;
    const st = await fetchIngestionBatchStatus(id);
    setStatus(st);
    if (prev) {
      const newlyDone = Math.max(0, st.done - prev.done);
      if (newlyDone === 1) toast.success("Candidate added to the pool successfully");
      if (newlyDone > 1) toast.success(`${newlyDone} candidates added to the pool successfully`);
    }
    if (st.failed + st.done >= st.total) setPolling(false);
  }

  async function deleteCandidate(externalId: string) {
    if (!externalId.trim()) return;
    setDeleteBusy((b) => ({ ...b, [externalId]: true }));
    setDeleteNote((n) => ({ ...n, [externalId]: "" }));
    try {
      await deleteCandidateByExternalId(externalId);
      setDeleteNote((n) => ({ ...n, [externalId]: "Removed" }));
      toast.success("Candidate has been deleted");
    } catch (e) {
      const m = (e as Error).message || "Remove failed";
      setDeleteNote((n) => ({ ...n, [externalId]: m }));
      toast.error(m);
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
      <div className="add-candidate-pro">
        <header className="add-candidate-pro-head">
          <h1 className="add-candidate-pro-title">Add candidates</h1>
          <p className="add-candidate-pro-sub">
            Upload résumés (PDF, Word, images) or paste LinkedIn / profile text — both use the same RezumeAI parser,
            embeddings, and jobs pipeline. The Chrome extension is optional.
          </p>
        </header>

        <section className="add-candidate-pro-card">
          <h2 className="add-candidate-pro-field-label" style={{ marginBottom: "0.35rem" }}>
            Paste profile or résumé text
          </h2>
          <p className="muted" style={{ margin: "0 0 0.65rem", fontSize: "0.88rem", lineHeight: 1.5 }}>
            From LinkedIn: open the profile, select from <strong>Name</strong> through <strong>Skills</strong> (and
            Experience if you can), copy, and paste here. Include every skill line after &quot;Show all&quot; if you
            need the full list. Minimum <strong>{MIN_PASTE_CHARS} characters</strong> so parsing succeeds.
          </p>
          <textarea
            className="add-candidate-textarea"
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={`Example lines the parser likes:\nName: …\nCurrent Title: …\nSkills: Python, SQL, …\nWORK EXPERIENCE\n  …`}
            rows={10}
            disabled={pasteBusy}
            spellCheck={false}
          />
          <div className="add-candidate-pro-row" style={{ marginTop: "0.75rem" }}>
            <label htmlFor="paste-filename" className="add-candidate-pro-field-label">
              Label (saved as filename)
            </label>
            <input
              id="paste-filename"
              className="add-candidate-pro-input"
              value={pasteFilename}
              onChange={(e) => setPasteFilename(e.target.value)}
              disabled={pasteBusy}
            />
          </div>
          <div className="add-candidate-pro-actions">
            <button type="button" className="dash-btn" disabled={pasteBusy} onClick={() => void startPasteIngest()}>
              {pasteBusy ? "Sending…" : "Ingest pasted text"}
            </button>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {pasteText.trim().length.toLocaleString()} / {MIN_PASTE_CHARS}+ chars
            </span>
          </div>
        </section>

        <section className="add-candidate-pro-card">
          <div className="add-candidate-pro-drop">
            <input
              type="file"
              className="add-candidate-pro-file"
              multiple
              accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,application/pdf,image/*"
              onClick={(e) => {
                (e.currentTarget as HTMLInputElement).value = "";
              }}
              onChange={(e) => onFiles(e.target.files)}
              disabled={bulkBusy}
              id="add-cand-files"
            />
            <label htmlFor="add-cand-files" className="add-candidate-pro-label">
              <span className="add-candidate-pro-label-title">Choose files</span>
              <span className="add-candidate-pro-label-hint">or drag into the list after selecting from the file picker</span>
            </label>
          </div>

          {files.length > 0 ? (
            <div className="add-candidate-pro-list">
              <div className="add-candidate-pro-meta">
                <span>{files.length} file(s)</span>
                <span className="muted">{formatBytes(totalBytes)}</span>
              </div>
              <ul>
                {files.slice(0, 20).map((f) => (
                  <li key={`${f.name}-${f.size}`}>{f.name}</li>
                ))}
              </ul>
              {files.length > 20 ? <p className="muted add-candidate-pro-more">+{files.length - 20} more</p> : null}
            </div>
          ) : null}

          <div className="add-candidate-pro-actions">
            <button type="button" className="dash-btn" disabled={bulkBusy || files.length === 0} onClick={() => void startBulk()}>
              {bulkBusy ? "Uploading…" : "Upload"}
            </button>
          </div>
        </section>

        <section className="add-candidate-pro-card add-candidate-pro-card--tight">
          <div className="add-candidate-pro-row">
            <label htmlFor="batch-id" className="add-candidate-pro-field-label">
              Batch ID
            </label>
            <input
              id="batch-id"
              className="add-candidate-pro-input"
              value={batchId}
              placeholder="Optional"
              onChange={(e) => setBatchId(e.target.value)}
            />
          </div>

          {status ? (
            <>
              <div className="add-candidate-pro-stats muted">
                <span>{status.total} total</span>
                <span>{status.queued} queued</span>
                <span>{status.processing} active</span>
                <span>{status.done} done</span>
                <span>{status.failed} failed</span>
              </div>
              <div className="dash-table-wrap">
                <table className="dash-summary-table add-candidate-table">
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Status</th>
                      <th>ID</th>
                      <th />
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.items.map((it) => (
                      <tr key={it.id}>
                        <td className="add-candidate-cell-file">{it.filename || "—"}</td>
                        <td>
                          <span className={rowStatusClass(it.status)}>{it.status}</span>
                        </td>
                        <td className="muted add-candidate-cell-id">{it.candidate_external_id || "—"}</td>
                        <td className="add-candidate-cell-actions">
                          {it.candidate_external_id && it.status === "done" ? (
                            <>
                              <button
                                type="button"
                                className="small-btn"
                                disabled={!!deleteBusy[it.candidate_external_id]}
                                onClick={() => void deleteCandidate(it.candidate_external_id)}
                              >
                                Remove
                              </button>
                              {deleteNote[it.candidate_external_id] ? (
                                <div
                                  className={
                                    deleteNote[it.candidate_external_id] === "Removed"
                                      ? "muted add-cand-note"
                                      : "add-cand-note add-cand-note--err"
                                  }
                                >
                                  {deleteNote[it.candidate_external_id]}
                                </div>
                              ) : null}
                            </>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="add-candidate-cell-err">{it.error || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="muted add-candidate-pro-empty">Status appears after you upload.</p>
          )}
        </section>
      </div>
    </DashFrame>
  );
}
