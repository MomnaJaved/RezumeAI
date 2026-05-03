import { useCallback, useEffect, useRef, useState } from "react";
import { Plus, X, FileUp } from "lucide-react";
import { uploadResume } from "../api";
import { useToast } from "../toast";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Called after a successful parse so parent can refetch profile data */
  onUploaded?: () => void;
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function CandidateResumeUploadModal({ open, onClose, onUploaded }: Props) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (!open) {
      setFile(null);
      setDragOver(false);
    }
  }, [open]);

  const runUpload = useCallback(
    async (f: File) => {
      setBusy(true);
      try {
        await uploadResume(f);
        toast.success("Your profile was updated from your resume.");
        onUploaded?.();
        onClose();
      } catch (e) {
        toast.error((e as Error).message || "Upload failed.");
      } finally {
        setBusy(false);
      }
    },
    [toast, onUploaded, onClose],
  );

  const onPick = useCallback(
    (list: FileList | null) => {
      const f = list?.[0];
      if (!f) return;
      setFile(f);
    },
    [],
  );

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cand-resume-upload-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 6000,
        background: "rgba(0,0,0,0.72)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(440px, 100%)",
          borderRadius: 18,
          border: "1px solid rgba(255,255,255,0.12)",
          background: "rgba(15,23,42,0.98)",
          boxShadow: "0 24px 80px rgba(0,0,0,0.55)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.75rem",
            padding: "0.85rem 1.1rem",
            borderBottom: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          <div id="cand-resume-upload-title" style={{ fontWeight: 700, fontSize: "1rem", color: "#fff" }}>
            Upload resume
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            aria-label="Close"
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.12)",
              background: "rgba(255,255,255,0.06)",
              color: "#fff",
              cursor: busy ? "wait" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: "1rem 1.15rem 1.15rem" }}>
          <p style={{ margin: "0 0 1rem", fontSize: "0.86rem", color: "rgba(255,255,255,0.55)", lineHeight: 1.5 }}>
            PDF, DOCX, TXT, or a clear image. Text is stored safely; skills and role are inferred automatically. You can
            replace your resume anytime.
          </p>

          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp,.bmp,application/pdf"
            style={{ display: "none" }}
            onChange={(e) => {
              onPick(e.target.files);
              e.target.value = "";
            }}
          />

          <div
            onDragEnter={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              onPick(e.dataTransfer.files);
            }}
            onClick={() => !busy && inputRef.current?.click()}
            style={{
              borderRadius: 14,
              border: dragOver ? "2px dashed rgba(56,189,248,0.55)" : "2px dashed rgba(255,255,255,0.18)",
              background: dragOver ? "rgba(56,189,248,0.08)" : "rgba(255,255,255,0.04)",
              padding: "1.35rem 1rem",
              textAlign: "center",
              cursor: busy ? "wait" : "pointer",
              transition: "border-color 0.15s, background 0.15s",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                margin: "0 auto 0.65rem",
                borderRadius: 14,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(56,189,248,0.15)",
                border: "1px solid rgba(56,189,248,0.35)",
                color: "#38bdf8",
              }}
            >
              <Plus size={26} strokeWidth={2.25} />
            </div>
            <div style={{ fontWeight: 650, fontSize: "0.9rem", color: "rgba(255,255,255,0.9)" }}>
              {busy ? "Uploading…" : "Drop your file here or click to browse"}
            </div>
            <div style={{ fontSize: "0.78rem", color: "rgba(255,255,255,0.4)", marginTop: "0.35rem" }}>
              One file · max 12 MB
            </div>
          </div>

          {file ? (
            <div
              style={{
                marginTop: "0.85rem",
                display: "flex",
                alignItems: "center",
                gap: "0.65rem",
                padding: "0.55rem 0.75rem",
                borderRadius: 12,
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <FileUp size={16} color="rgba(167,139,250,0.95)" style={{ flexShrink: 0 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "#fff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {file.name}
                </div>
                <div style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.45)" }}>{formatBytes(file.size)}</div>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                }}
                style={{
                  fontSize: "0.75rem",
                  color: "#fca5a5",
                  background: "none",
                  border: "none",
                  cursor: busy ? "not-allowed" : "pointer",
                  flexShrink: 0,
                }}
              >
                Clear
              </button>
            </div>
          ) : null}

          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
            <button
              type="button"
              disabled={busy}
              onClick={onClose}
              style={{
                padding: "0.5rem 0.9rem",
                borderRadius: 10,
                border: "1px solid rgba(255,255,255,0.14)",
                background: "rgba(255,255,255,0.06)",
                color: "rgba(255,255,255,0.85)",
                fontWeight: 600,
                fontSize: "0.84rem",
                cursor: busy ? "wait" : "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !file}
              onClick={() => file && void runUpload(file)}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: 10,
                border: "1px solid rgba(56,189,248,0.45)",
                background: file && !busy ? "rgba(56,189,248,0.22)" : "rgba(255,255,255,0.06)",
                color: file && !busy ? "#e0f2fe" : "rgba(255,255,255,0.35)",
                fontWeight: 650,
                fontSize: "0.84rem",
                cursor: busy || !file ? "not-allowed" : "pointer",
              }}
            >
              {busy ? "Saving…" : "Save to profile"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Compact circular + control for headers (opens upload modal via onClick). */
export function CandidateResumeUploadTrigger({
  onClick,
  disabled,
  title = "Upload or replace resume",
}: {
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        width: 42,
        height: 42,
        flexShrink: 0,
        borderRadius: 12,
        border: "1px solid rgba(56,189,248,0.4)",
        background: "rgba(56,189,248,0.12)",
        color: "#7dd3fc",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        cursor: disabled ? "wait" : "pointer",
        transition: "background 0.15s, border-color 0.15s",
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.background = "rgba(56,189,248,0.22)";
          (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(56,189,248,0.55)";
        }
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = "rgba(56,189,248,0.12)";
        (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(56,189,248,0.4)";
      }}
    >
      <Plus size={22} strokeWidth={2.25} />
    </button>
  );
}
