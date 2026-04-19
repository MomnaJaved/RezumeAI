import { useEffect, useState } from "react";
import { fetchCandidateApplications, type CandidateApplicationRow } from "../../api";

const LABELS: Record<string, string> = {
  new: "Applied",
  screened: "Screened",
  shortlisted: "Shortlisted",
  interviewed: "Interviewing",
  hired: "Hired",
  rejected: "Not selected",
  selected: "Selected",
};

export default function CandidateApplicationsPage() {
  const [items, setItems] = useState<CandidateApplicationRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetchCandidateApplications();
        if (!cancelled) setItems(r.items);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function label(st: string) {
    return LABELS[st.toLowerCase()] || st;
  }

  return (
    <div>
      <h1 className="dash-title">Your applications</h1>
      <p style={{ marginTop: "0.35rem", color: "rgba(255,255,255,0.65)" }}>Progress per job (shared with recruiters).</p>
      {loading ? <p style={{ marginTop: "1rem" }}>Loading…</p> : null}
      {!loading && items.length === 0 ? (
        <p style={{ marginTop: "1rem", color: "rgba(255,255,255,0.55)" }}>No applications yet. Browse jobs and apply.</p>
      ) : null}
      <ul style={{ listStyle: "none", padding: 0, marginTop: "1rem", display: "grid", gap: "0.65rem" }}>
        {items.map((row) => (
          <li
            key={`${row.job_external_id}-${row.updated_at}`}
            style={{
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 12,
              padding: "0.75rem 1rem",
              background: "rgba(2,6,23,0.35)",
            }}
          >
            <strong>{row.job_title}</strong>
            <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.55)", marginTop: "0.2rem" }}>
              {row.company ? `${row.company} · ` : ""}
              {row.job_external_id}
            </div>
            <div style={{ marginTop: "0.45rem", fontSize: "0.85rem" }}>
              Status: <strong>{label(row.status)}</strong>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
