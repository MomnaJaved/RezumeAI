import { useEffect } from "react";

export type ConfirmDialogProps = {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Destructive action (e.g. delete) — styles confirm as danger. */
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
};

/**
 * In-app confirmation (replaces window.confirm). Not a toast — confirmations need explicit choices.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="app-confirm-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="app-confirm-card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="app-confirm-title"
        aria-describedby="app-confirm-desc"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 id="app-confirm-title" className="app-confirm-title">
          {title}
        </h2>
        <p id="app-confirm-desc" className="app-confirm-message">
          {message}
        </p>
        <div className="app-confirm-actions">
          <button type="button" className="dash-btn app-confirm-cancel" disabled={busy} onClick={onClose}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "dash-btn app-confirm-danger" : "dash-btn"}
            disabled={busy}
            onClick={() => onConfirm()}
          >
            {busy ? "Please wait…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
