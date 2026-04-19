import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

type SearchItem = {
  id: string;
  label: string;
  path: string;
  /** Extra phrases to match (lowercased). */
  match: string;
};

const ITEMS: SearchItem[] = [
  { id: "dashboard", label: "Dashboard", path: "/dashboard", match: "dashboard home overview pipeline" },
  { id: "candidates", label: "Candidates", path: "/candidates", match: "candidates people talent cv resume profiles applicants" },
  { id: "jobs", label: "Jobs", path: "/jobs", match: "jobs postings roles requisitions openings" },
  { id: "clients", label: "Clients", path: "/clients", match: "clients companies accounts customers" },
  { id: "reports", label: "Reports", path: "/reports", match: "reports analytics exports metrics" },
  { id: "settings", label: "Settings", path: "/settings", match: "settings preferences account profile configuration" },
  { id: "inbox", label: "Inbox", path: "/inbox", match: "inbox notifications messages activity" },
  { id: "matching", label: "Matching", path: "/matching", match: "matching rank screening shortlist job match" },
  { id: "upload", label: "Upload resume", path: "/upload", match: "upload resume cv document candidate file" },
  { id: "add-candidate", label: "Add candidate", path: "/candidates/add", match: "add candidate new resume upload bulk import paste cv" },
  { id: "playground", label: "Playground", path: "/playground", match: "playground ml api try experiment" },
];

function norm(s: string): string {
  return s.trim().toLowerCase();
}

export default function DashGlobalSearch() {
  const nav = useNavigate();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [highlight, setHighlight] = useState(0);

  const filtered = useMemo(() => {
    const needle = norm(q);
    if (!needle) return ITEMS.slice(0, 8);
    return ITEMS.filter((it) => {
      const blob = `${it.label} ${it.path} ${it.match}`;
      return blob.includes(needle);
    }).slice(0, 12);
  }, [q]);

  const go = useCallback(
    (path: string) => {
      setOpen(false);
      setQ("");
      nav(path);
    },
    [nav]
  );

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  useEffect(() => {
    setHighlight(0);
  }, [q, open]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open && (e.key === "ArrowDown" || e.key === "Enter") && q.trim()) {
      setOpen(true);
      return;
    }
    if (!open) return;
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((i) => Math.min(i + 1, Math.max(0, filtered.length - 1)));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((i) => Math.max(i - 1, 0));
    }
    if (e.key === "Enter" && filtered.length > 0) {
      e.preventDefault();
      go(filtered[highlight]?.path ?? filtered[0].path);
    }
  }

  return (
    <div className="dash-global-search" ref={rootRef}>
      <input
        type="search"
        className="dash-global-search-input"
        name="rezume_dash_search"
        placeholder="Search pages, CVs, jobs, settings…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls="dash-global-search-list"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
        data-lpignore="true"
        data-1p-ignore="true"
        data-form-type="other"
      />
      {open ? (
        filtered.length > 0 ? (
          <ul id="dash-global-search-list" className="dash-global-search-list" role="listbox">
            {filtered.map((it, idx) => (
              <li key={it.id} role="option" aria-selected={idx === highlight}>
                <button
                  type="button"
                  className={idx === highlight ? "dash-global-search-item is-active" : "dash-global-search-item"}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => go(it.path)}
                >
                  <span className="dash-global-search-item-label">{it.label}</span>
                  <span className="dash-global-search-item-path">{it.path}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : q.trim() ? (
          <div className="dash-global-search-empty" id="dash-global-search-list" role="status">
            No pages match “{q.trim()}”. Try “candidates”, “jobs”, or “upload”.
          </div>
        ) : null
      ) : null}
    </div>
  );
}
