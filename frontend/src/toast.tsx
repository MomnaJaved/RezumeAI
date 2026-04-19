import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type ToastVariant = "success" | "error" | "info";

export type ToastOptions = {
  /** Small label above the message (Slack-style workspace header). */
  title?: string;
};

type ToastItem = {
  id: number;
  message: string;
  variant: ToastVariant;
  title?: string;
};

type ToastApi = {
  show: (message: string, variant?: ToastVariant, options?: ToastOptions) => void;
  success: (message: string, options?: ToastOptions) => void;
  error: (message: string, options?: ToastOptions) => void;
  info: (message: string, options?: ToastOptions) => void;
};

const ToastContext = createContext<ToastApi | null>(null);

const DEFAULT_MS = 5200;

function ToastBellIcon() {
  return (
    <span className="toast-icon" aria-hidden>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    </span>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, number>>(new Map());

  const remove = useCallback((id: number) => {
    const t = timers.current.get(id);
    if (t) window.clearTimeout(t);
    timers.current.delete(id);
    setItems((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const show = useCallback(
    (message: string, variant: ToastVariant = "info", options?: ToastOptions) => {
      const id = Date.now() + Math.floor(Math.random() * 1000);
      const title = options?.title?.trim();
      setItems((prev) => {
        const next: ToastItem = { id, message, variant, title: title || undefined };
        // Newest at top (Slack-style stack in top-right)
        return [next, ...prev].slice(0, 5);
      });
      const tid = window.setTimeout(() => remove(id), DEFAULT_MS);
      timers.current.set(id, tid);
    },
    [remove],
  );

  const api = useMemo<ToastApi>(
    () => ({
      show: (m, v = "info", o) => show(m, v, o),
      success: (m, o) => show(m, "success", o),
      error: (m, o) => show(m, "error", o),
      info: (m, o) => show(m, "info", o),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {items.map((t) => (
          <div key={t.id} className={`toast toast--${t.variant}`} role="status">
            <ToastBellIcon />
            <div className="toast-body">
              {t.title ? <div className="toast-title">{t.title}</div> : null}
              <span className="toast-msg">{t.message}</span>
            </div>
            <button type="button" className="toast-dismiss" aria-label="Dismiss" onClick={() => remove(t.id)}>
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      show: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
    };
  }
  return ctx;
}
