import { useEffect, useState } from "react";
import { fetchCandidateApplications, type CandidateApplicationRow } from "../../api";
import { useToast } from "../../toast";

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
  const toast = useToast();
  const [items, setItems] = useState<CandidateApplicationRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetchCandidateApplications();
        if (!cancelled) setItems(r.items);
      } catch (e) {
        if (!cancelled) {
          setItems([]);
          toast.error(e instanceof Error ? e.message : "Could not load applications");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast]);

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
            {/* Job title + meta */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong style={{ flex: 1 }}>{row.job_title}</strong>
              {/* Match score badge */}
              {row.match_score !== null ? (
                <span
                  style={{
                    flexShrink: 0,
                    background: "rgba(99,102,241,0.18)",
                    border: "1px solid rgba(99,102,241,0.35)",
                    borderRadius: 8,
                    padding: "0.15rem 0.55rem",
                    fontSize: "0.78rem",
                    fontWeight: 600,
                    color: "#a5b4fc",
                    whiteSpace: "nowrap",
                  }}
                >
                  {row.match_score.toFixed(1)}%
                </span>
              ) : (
                <span
                  style={{
                    flexShrink: 0,
                    background: "rgba(255,255,255,0.06)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 8,
                    padding: "0.15rem 0.55rem",
                    fontSize: "0.78rem",
                    color: "rgba(255,255,255,0.35)",
                    whiteSpace: "nowrap",
                  }}
                >
                  Processing…
                </span>
              )}
            </div>

            {/* Company + job ID */}
            <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.55)", marginTop: "0.2rem" }}>
              {row.company ? `${row.company} · ` : ""}
              {row.job_external_id}
            </div>

            {/* Status + rank row */}
            <div style={{ marginTop: "0.5rem", display: "flex", gap: "1.2rem", fontSize: "0.85rem", flexWrap: "wrap" }}>
              <span>
                Status: <strong>{label(row.status)}</strong>
              </span>
              {row.rank_position !== null ? (
                <span style={{ color: "rgba(255,255,255,0.7)" }}>
                  Rank:{" "}
                  <strong style={{ color: "#f0abfc" }}>
                    #{row.rank_position}
                  </strong>
                  {row.match_score !== null && (
                    <span style={{ color: "rgba(255,255,255,0.45)", fontSize: "0.8rem", marginLeft: "0.3rem" }}>
                      ({row.match_score.toFixed(1)}% match)
                    </span>
                  )}
                </span>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
