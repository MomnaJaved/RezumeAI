import { Link, useNavigate } from "react-router-dom";
import type { DashboardCandidatePreview, DashboardJobChart, DashboardPipelineStage } from "../api";

function pieSlicePath(cx: number, cy: number, r: number, start: number, end: number): string {
  const sweep = end - start;
  if (sweep <= 0.001) return "";
  if (sweep >= 2 * Math.PI - 0.001) return "";
  const x0 = cx + r * Math.cos(start);
  const y0 = cy + r * Math.sin(start);
  const x1 = cx + r * Math.cos(end);
  const y1 = cy + r * Math.sin(end);
  const large = sweep > Math.PI ? 1 : 0;
  return `M ${cx} ${cy} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} Z`;
}

export function DashboardApplicantTracker({ pipeline }: { pipeline: DashboardPipelineStage[] }) {
  return (
    <section className="dash-widget dash-widget-tracker">
      <header className="dash-widget-head">
        <h2>Applicant Tracker</h2>
        <Link to="/candidates" className="dash-widget-link">
          See complete board →
        </Link>
      </header>
      <div className="dash-tracker-rows">
        {pipeline.map((row) => (
          <div key={row.key} className="dash-tracker-row">
            <div className="dash-tracker-meta">
              <span className="dash-tracker-label">{row.label}</span>
              <span className="dash-tracker-count">{row.count}</span>
            </div>
            <div className="dash-tracker-avatars" aria-label={`${row.count} in ${row.label}`}>
              {row.people.map((p) => (
                <span key={p.external_id} className="dash-avatar" title={p.name}>
                  {p.initials}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function DashboardJobsPie({ chart }: { chart: DashboardJobChart }) {
  const cx = 90;
  const cy = 90;
  const r = 68;
  const segs = chart.segments;
  let a = -Math.PI / 2;
  const paths: { d: string; fill: string; key: string }[] = [];

  const fullDisc = segs.length === 1 && segs[0].pct >= 99.5;

  if (!fullDisc) {
    for (const s of segs) {
      const sweep = (s.pct / 100) * 2 * Math.PI;
      const d = pieSlicePath(cx, cy, r, a, a + sweep);
      if (d) paths.push({ d, fill: s.color, key: s.key });
      a += sweep;
    }
  }

  return (
    <section className="dash-widget dash-widget-jobs">
      <header className="dash-widget-head">
        <h2>Jobs</h2>
        <span className="dash-widget-sub">{chart.total} in database</span>
      </header>
      <div className="dash-pie-wrap">
        <svg className="dash-pie-svg" viewBox="0 0 180 180" aria-hidden>
          {fullDisc ? (
            <circle cx={cx} cy={cy} r={r} fill={segs[0].color} />
          ) : (
            paths.map((p) => (
              <path
                key={p.key}
                d={p.d}
                fill={p.fill}
                stroke="rgba(15, 23, 42, 0.45)"
                strokeWidth="1.2"
              />
            ))
          )}
        </svg>
        <ul className="dash-pie-legend">
          {segs.map((s) => (
            <li key={s.key}>
              <span className="dash-pie-dot" style={{ background: s.color }} />
              <span className="dash-pie-legend-label">{s.label}</span>
              <span className="dash-pie-legend-pct">{s.pct}%</span>
              <span className="dash-pie-legend-n">({s.count})</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function scoreClass(score: number): string {
  if (score >= 70) return "dash-score-good";
  if (score >= 45) return "dash-score-mid";
  return "dash-score-low";
}

function statusClass(raw: string): string {
  const s = raw.toLowerCase();
  if (s.includes("shortlist") || s === "selected") return "dash-status-hot";
  if (s.includes("interview")) return "dash-status-warm";
  if (s.includes("hire")) return "dash-status-hired";
  if (s === "new") return "dash-status-new";
  return "dash-status-default";
}

/** Same mapping as CandidatesPage `displayRoleFine`. */
function displayRoleFine(v: string | undefined): string {
  const x = (v || "").trim().toLowerCase();
  if (x === "intern" || x === "mobile") return "software";
  return (v || "").trim();
}

export function DashboardCandidateSummary({ rows }: { rows: DashboardCandidatePreview[] }) {
  const navigate = useNavigate();

  function goRow(id: string) {
    navigate(`/candidates/${id}`);
  }

  return (
    <section className="dash-widget dash-widget-table">
      <header className="dash-widget-head">
        <div>
          <h2>Candidate Summary</h2>
        </div>
        <Link to="/candidates" className="dash-widget-btn">
          See all candidates →
        </Link>
      </header>
      <div className="dash-table-wrap">
        <table className="dash-summary-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th title="Profile strength vs your candidate pool (same as the candidates list). Job-specific match % appears when ranking against a job.">
                Score
              </th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.external_id}
                className="dash-summary-row-click"
                tabIndex={0}
                role="link"
                title="Open candidate profile"
                onClick={() => goRow(r.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    goRow(r.id);
                  }
                }}
              >
                <td className="dash-td-name">{r.full_name}</td>
                <td>
                  <div style={{ fontWeight: 700, color: "rgba(255,255,255,0.92)" }}>{r.title || "—"}</div>
                  {(r.role_fine || "").trim() && (r.role_fine || "").trim().toLowerCase() !== "unknown" ? (
                    <div className="muted" style={{ fontSize: "0.85rem", marginTop: "0.15rem" }}>
                      {displayRoleFine(r.role_fine)}
                    </div>
                  ) : null}
                </td>
                <td>
                  <span className={`dash-score ${scoreClass(r.score)}`}>{r.score}%</span>
                </td>
                <td>
                  <span className={`dash-status-pill ${statusClass(r.status_raw)}`}>{r.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
