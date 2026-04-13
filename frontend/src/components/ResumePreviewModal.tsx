import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { fetchCandidateFileBlob } from "../api";
import { useToast } from "../toast";

const ResumePdfJsView = lazy(() => import("./ResumePdfJsView"));

type PreviewMode = "pdf" | "image" | "text" | "none";

function safeDownloadName(filename: string | undefined, externalId: string): string {
  const base = (filename || `${externalId}.bin`).trim() || "resume";
  return base.replace(/[/\\?%*:|"<>]/g, "_");
}

function detectPreviewMode(blob: Blob, contentType: string, filename?: string): PreviewMode {
  const c = (contentType || blob.type || "").toLowerCase();
  const fn = (filename || "").toLowerCase();
  const looksPdf = c.includes("pdf") || fn.endsWith(".pdf");
  if (looksPdf || (c.includes("octet-stream") && fn.endsWith(".pdf"))) return "pdf";
  if (c.startsWith("image/") || /\.(png|jpe?g|gif|webp|bmp)$/i.test(fn)) return "image";
  if (c.startsWith("text/") || fn.endsWith(".txt") || fn.endsWith(".md")) return "text";
  return "none";
}

async function blobForPreview(blob: Blob, mode: PreviewMode): Promise<Blob> {
  if (mode !== "pdf") return blob;
  const t = (blob.type || "").toLowerCase();
  if (t.includes("pdf")) return blob;
  const ab = await blob.arrayBuffer();
  return new Blob([ab], { type: "application/pdf" });
}

export type ResumePreviewModalProps = {
  open: boolean;
  externalId: string;
  filename?: string;
  onClose: () => void;
};

/**
 * Full-screen resume preview (PDF / image / text). Fetches file when opened.
 */
export default function ResumePreviewModal({ open, externalId, filename, onClose }: ResumePreviewModalProps) {
  const toast = useToast();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<PreviewMode>("none");
  const [loading, setLoading] = useState(false);
  const [downloadReady, setDownloadReady] = useState(false);
  const [textPreview, setTextPreview] = useState("");
  const [pdfBuffer, setPdfBuffer] = useState<ArrayBuffer | null>(null);
  const blobRef = useRef<Blob | null>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      blobRef.current = null;
      setPreviewUrl(null);
      setPreviewMode("none");
      setTextPreview("");
      setPdfBuffer(null);
      setLoading(false);
      setDownloadReady(false);
      return;
    }

    if (!externalId) return;

    let cancelled = false;
    setLoading(true);
    setDownloadReady(false);
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    blobRef.current = null;
    setPreviewUrl(null);
    setPreviewMode("none");
    setTextPreview("");
    setPdfBuffer(null);

    (async () => {
      try {
        const { blob, contentType } = await fetchCandidateFileBlob(externalId);
        if (cancelled) return;
        const mode = detectPreviewMode(blob, contentType, filename);
        const displayBlob = await blobForPreview(blob, mode);
        blobRef.current = displayBlob;
        const url = URL.createObjectURL(displayBlob);
        objectUrlRef.current = url;
        setPreviewUrl(url);
        setPreviewMode(mode);
        if (mode === "pdf") {
          const ab = await displayBlob.arrayBuffer();
          if (cancelled) return;
          // Own copy for React state + pdf.js worker (avoid detached SharedArrayBuffer / postMessage errors).
          setPdfBuffer(ab.slice(0));
        }
        if (mode === "text") {
          const slice = displayBlob.size > 400_000 ? displayBlob.slice(0, 400_000) : displayBlob;
          setTextPreview(await slice.text());
        }
        setDownloadReady(true);
      } catch (e) {
        if (!cancelled) {
          toast.error((e as Error).message || "Could not load resume (file may be missing).");
          onClose();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, externalId, filename]);

  useEffect(
    () => () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  function onDownload() {
    const blob = blobRef.current;
    if (!blob || !externalId) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = safeDownloadName(filename, externalId);
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
  }

  if (!open) return null;

  return (
    <div
      className="cand-preview-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="cand-preview-dialog" role="dialog" aria-modal="true" aria-label="Resume preview">
        <header className="cand-preview-head">
          <span className="cand-preview-title">{filename?.trim() || "Resume"}</span>
          <div className="cand-preview-head-actions">
            {previewUrl && previewMode === "pdf" ? (
              <button
                type="button"
                className="dash-btn"
                disabled={!downloadReady}
                onClick={() => window.open(previewUrl, "_blank", "noopener,noreferrer")}
              >
                Open in new tab
              </button>
            ) : null}
            <button type="button" className="dash-btn" disabled={!downloadReady} onClick={onDownload}>
              Download
            </button>
            <button type="button" className="small-btn" onClick={onClose}>
              Close
            </button>
          </div>
        </header>
        <div className="cand-preview-body">
          {loading ? (
            <p className="muted cand-preview-fallback" style={{ margin: "2rem auto" }}>
              Loading preview…
            </p>
          ) : null}
          {!loading && previewMode === "pdf" && pdfBuffer ? (
            <Suspense
              fallback={
                <p className="muted cand-preview-fallback" style={{ margin: "2rem auto" }}>
                  Loading PDF viewer…
                </p>
              }
            >
              <ResumePdfJsView data={pdfBuffer} />
            </Suspense>
          ) : null}
          {!loading && previewUrl && previewMode === "image" ? (
            <img className="cand-preview-img" src={previewUrl} alt="Resume" />
          ) : null}
          {!loading && previewMode === "text" ? (
            <pre className="cand-preview-text">{textPreview}</pre>
          ) : null}
          {!loading && previewUrl && previewMode === "none" ? (
            <p className="muted cand-preview-fallback">
              Inline preview is not available for this file type. Use Download to open it on your device.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
