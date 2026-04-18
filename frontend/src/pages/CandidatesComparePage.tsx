import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import DashFrame from "../DashFrame";
import { candidateDisplayName } from "../candidateDisplayName";
import { compareCandidates, normalizedBestJobMatchPercent, type CandidateCompareSnapshot } from "../api";
import { useToast } from "../toast";

const ROWS: { key: keyof CandidateCompareSnapshot | "match_pct" | "client_line"; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "role_label", label: "Role" },
  { key: "years_experience", label: "Years experience" },
  { key: "highest_degree", label: "Degree" },
  { key: "match_pct", label: "Best match" },
  { key: "best_job_title", label: "Best job" },
  { key: "client_line", label: "Hiring / client" },
  { key: "status", label: "Status" },
  { key: "contact_email", label: "Email" },
  { key: "skills", label: "Skills (excerpt)" },
];

function clientLine(c: CandidateCompareSnapshot): string {
  const name = (c.best_job_client_name || "").trim();
  const co = (c.best_job_client_company || "").trim();
  const contact = (c.best_job_client_contact || "").trim();
  const email = (c.best_job_client_email || "").trim();
  const bits = [name && co ? `${name} (${co})` : name || co, contact, email].filter(Boolean);
  return bits.join(" · ");
}

function cellValue(c: CandidateCompareSnapshot, row: (typeof ROWS)[number]): string {
  if (row.key === "match_pct") {
    const p = normalizedBestJobMatchPercent(c.best_job_match_score);
    return p != null ? `${p}%` : "—";
  }
  if (row.key === "client_line") return clientLine(c) || "—";
  const v = c[row.key as keyof CandidateCompareSnapshot];
  if (v == null) return "—";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "—";
  const s = String(v).trim();
  if (row.key === "skills" && s.length > 220) return `${s.slice(0, 217)}…`;
  return s || "—";
}

export default function CandidatesComparePage() {
  const toast = useToast();
  const [sp] = useSearchParams();
  const ids = useMemo(
    () =>
      (sp.get("ids") || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    [sp],
  );
  const [loading, setLoading] = useState(true);
  const [cols, setCols] = useState<CandidateCompareSnapshot[]>([]);

  useEffect(() => {
    if (ids.length < 2 || ids.length > 6) {
      setCols([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await compareCandidates(ids);
        if (!cancelled) setCols(res.candidates || []);
      } catch (e) {
        if (!cancelled) {
          setCols([]);
          toast.error((e as Error).message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ids.join("|"), toast]);

  const invalid = ids.length > 0 && (ids.length < 2 || ids.length > 6);

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
      <div className="dash-panel cand-compare-wrap">
        <h1 className="dash-title" style={{ marginTop: 0 }}>
          Compare candidates
        </h1>
        {invalid ? (
          <p className="muted" style={{ margin: 0 }}>
            Select between 2 and 6 candidates from the list (use checkboxes), then open Compare again.
          </p>
        ) : loading ? (
          <p className="muted" style={{ margin: 0 }}>
            Loading…
          </p>
        ) : cols.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No data returned. The selected IDs may be invalid or no longer exist.
          </p>
        ) : (
          <div className="cand-compare-scroll">
            <table className="cand-compare-table">
              <thead>
                <tr>
                  <th className="cand-compare-sticky-col" />
                  {cols.map((c) => (
                    <th key={c.id}>
                      <Link to={`/candidates/${c.id}`} className="cand-compare-name-link">
                        {candidateDisplayName(c)}
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((row) => (
                  <tr key={row.label}>
                    <th className="cand-compare-sticky-col muted">{row.label}</th>
                    {cols.map((c) => (
                      <td key={`${c.id}-${row.label}`}>{cellValue(c, row)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashFrame>
  );
}
