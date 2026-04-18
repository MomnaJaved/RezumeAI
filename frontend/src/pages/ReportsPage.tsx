import { useEffect, useState } from "react";
import DashFrame from "../DashFrame";
import { fetchReportsData, type ReportsData } from "../api";
import { useToast } from "../toast";

const DATE_PRESETS: { label: string; value: string; days?: number }[] = [
  { label: "All time", value: "all" },
  { label: "Last 7 days", value: "7d", days: 7 },
  { label: "Last 30 days", value: "30d", days: 30 },
  { label: "Last 90 days", value: "90d", days: 90 },
  { label: "Last 6 months", value: "6m", days: 180 },
  { label: "Last year", value: "1y", days: 365 },
];

const PIPELINE_STAGES = [
  { key: "new",          label: "New",          color: "rgba(56,189,248,0.85)"  },
  { key: "screened",     label: "Screened",     color: "rgba(56,189,248,0.68)"  },
  { key: "shortlisted",  label: "Shortlisted",  color: "rgba(99,102,241,0.85)"  },
  { key: "interviewing", label: "Interviewing", color: "rgba(168,85,247,0.8)"   },
  { key: "selected",     label: "Selected",     color: "rgba(251,191,36,0.85)"  },
  { key: "hired",        label: "Hired",        color: "rgba(134,239,172,0.85)" },
  { key: "rejected",     label: "Rejected",     color: "rgba(248,113,113,0.75)" },
] as const;

function dateFrom(preset: string): string | undefined {
  const found = DATE_PRESETS.find((p) => p.value === preset);
  if (!found?.days) return undefined;
  const d = new Date(Date.now() - found.days * 86_400_000);
  return d.toISOString().split("T")[0];
}

export default function ReportsPage() {
  const toast = useToast();
  const [data, setData] = useState<ReportsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [clientFilter, setClientFilter] = useState("");
  const [dateRange, setDateRange] = useState("all");
  const [jobFilter, setJobFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchReportsData({
      client_id: clientFilter || undefined,
      date_from: dateFrom(dateRange),
      job_external_id: jobFilter || undefined,
    })
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) toast.error((e as Error).message || "Failed to load report"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [clientFilter, dateRange, jobFilter, toast]);

  const pipeline = data?.pipeline;
  const kpi = data?.kpi;
  const pipelineMax = pipeline
    ? Math.max(1, ...PIPELINE_STAGES.map((s) => pipeline[s.key] ?? 0))
    : 1;

  const downloadPdf = () => {
    if (!data || !kpi) return;
    const pipelineRows = PIPELINE_STAGES.map((s) =>
      `<tr><td>${s.label}</td><td style="font-weight:700">${pipeline?.[s.key] ?? 0}</td></tr>`
    ).join("");
    const jobRows = (data.job_performance || []).map((j) =>
      `<tr><td>${j.job_title}</td><td>${j.avg_match_score}%</td><td>${j.hires}</td></tr>`
    ).join("");
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
      <title>Hiring Performance Report</title>
      <style>
        * { box-sizing:border-box; margin:0; padding:0; }
        body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; font-size:12px; color:#0f172a; padding:32px 36px; }
        h1 { font-size:20px; font-weight:800; margin-bottom:4px; text-transform:uppercase; letter-spacing:.06em; }
        h2 { font-size:13px; font-weight:700; margin:20px 0 8px; text-transform:uppercase; letter-spacing:.05em; color:#334155; }
        .meta { font-size:11px; color:#64748b; margin-bottom:24px; }
        .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }
        .kpi-card { background:#f1f5f9; border-radius:8px; padding:12px 16px; }
        .kpi-label { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color:#64748b; }
        .kpi-value { font-size:24px; font-weight:800; color:#0f172a; }
        .two-col { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:24px; }
        table { width:100%; border-collapse:collapse; }
        thead tr { background:#0f172a; color:#fff; }
        thead th { padding:7px 10px; text-align:left; font-size:10px; text-transform:uppercase; }
        tbody td { padding:6px 10px; border-bottom:1px solid #e2e8f0; }
        tbody tr:nth-child(even) { background:#f8fafc; }
        .metrics-row { display:flex; gap:12px; margin-top:12px; }
        .metric-box { flex:1; background:#f1f5f9; border-radius:8px; padding:12px; text-align:center; }
        .metric-big { font-size:28px; font-weight:800; }
        .metric-sub { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:.05em; }
        .screen-row { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
        .screen-label { width:130px; font-size:12px; }
        .screen-bar-bg { flex:1; height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden; }
        .screen-bar-fill { height:100%; background:#0369a1; border-radius:4px; }
        .screen-pct { width:40px; text-align:right; font-weight:700; font-size:13px; }
      </style>
    </head><body>
      <h1>Insights into Hiring Performance</h1>
      <div class="meta">Generated on ${new Date().toLocaleDateString(undefined, { year:"numeric", month:"long", day:"numeric" })}</div>
      <div class="kpi-grid">
        <div class="kpi-card"><div class="kpi-label">Total Jobs</div><div class="kpi-value">${kpi.total_jobs}</div></div>
        <div class="kpi-card"><div class="kpi-label">Candidates</div><div class="kpi-value">${kpi.total_candidates}</div></div>
        <div class="kpi-card"><div class="kpi-label">Hires</div><div class="kpi-value">${kpi.hires}</div></div>
        <div class="kpi-card"><div class="kpi-label">Avg Hire Time</div><div class="kpi-value">${kpi.avg_hire_time_days}<span style="font-size:14px"> days</span></div></div>
      </div>
      <div class="two-col">
        <div>
          <h2>Pipeline</h2>
          <table><tbody>${pipelineRows}</tbody></table>
        </div>
        <div>
          <h2>Job Performance</h2>
          <table>
            <thead><tr><th>Job Title</th><th>Avg Match</th><th>Hires</th></tr></thead>
            <tbody>${jobRows}</tbody>
          </table>
          <div class="metrics-row">
            <div class="metric-box"><div class="metric-big">${data.time_saved_pct}%</div><div class="metric-sub">Time Saved</div></div>
            <div class="metric-box"><div class="metric-big">${data.shortlist_accuracy_pct}%</div><div class="metric-sub">Shortlist Accuracy</div></div>
          </div>
        </div>
      </div>
      <h2>AI vs Manual Screening</h2>
      <div class="screen-row">
        <div class="screen-label">AI Screening</div>
        <div class="screen-bar-bg"><div class="screen-bar-fill" style="width:${data.ai_screening_pct}%"></div></div>
        <div class="screen-pct">${data.ai_screening_pct}%</div>
      </div>
      <div class="screen-row">
        <div class="screen-label">Manual Screening</div>
        <div class="screen-bar-bg"><div class="screen-bar-fill" style="width:${data.manual_screening_pct}%"></div></div>
        <div class="screen-pct">${data.manual_screening_pct}%</div>
      </div>
    </body></html>`;
    const win = window.open("", "_blank", "width=960,height=720");
    if (!win) return;
    win.document.write(html);
    win.document.close();
    win.focus();
    setTimeout(() => win.print(), 400);
  };

  const selectStyle: React.CSSProperties = {
    background: "rgba(2,6,23,0.4)",
    color: "rgba(226,232,240,0.9)",
    border: "1px solid rgba(255,255,255,0.14)",
    borderRadius: "10px",
    padding: "0.3rem 0.6rem",
    fontSize: "0.82rem",
    cursor: "pointer",
    fontFamily: "inherit",
  };

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">Filter By</span>
            <select
              value={clientFilter}
              onChange={(e) => setClientFilter(e.target.value)}
              style={selectStyle}
              aria-label="Client filter"
            >
              <option value="">All Clients</option>
              {(data?.clients || []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              style={selectStyle}
              aria-label="Date range"
            >
              {DATE_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            <select
              value={jobFilter}
              onChange={(e) => setJobFilter(e.target.value)}
              style={selectStyle}
              aria-label="Job filter"
            >
              <option value="">All Jobs</option>
              {(data?.jobs_list || []).map((j) => (
                <option key={j.external_id} value={j.external_id}>{j.title}</option>
              ))}
            </select>
            <span style={{ marginLeft: "auto" }} />
            <button
              type="button"
              className="match-compare-btn"
              onClick={downloadPdf}
              disabled={!data || loading}
            >
              Download Report as PDF
            </button>
          </div>
        </div>
      }
    >
      <div className="reports-page">
        <h1 className="reports-title">Insights into Hiring Performance</h1>

        {loading && !data ? (
          <p className="muted" style={{ marginTop: 24 }}>Loading report…</p>
        ) : (
          <>
            {/* KPI Cards */}
            <div className="reports-kpi-grid">
              <div className="reports-kpi-card">
                <div className="reports-kpi-label">Total Jobs</div>
                <div className="reports-kpi-value">{kpi?.total_jobs ?? 0}</div>
              </div>
              <div className="reports-kpi-card">
                <div className="reports-kpi-label">Candidates</div>
                <div className="reports-kpi-value">{kpi?.total_candidates ?? 0}</div>
              </div>
              <div className="reports-kpi-card">
                <div className="reports-kpi-label">Hires</div>
                <div className="reports-kpi-value">{kpi?.hires ?? 0}</div>
              </div>
              <div className="reports-kpi-card">
                <div className="reports-kpi-label">Average Hire Time</div>
                <div className="reports-kpi-value">
                  {kpi?.avg_hire_time_days ?? 0}
                  <span className="reports-kpi-unit">days</span>
                </div>
              </div>
            </div>

            {/* Middle: pipeline + job table */}
            <div className="reports-mid-grid">
              {/* Pipeline funnel */}
              <div className="reports-panel">
                <div className="reports-panel-title">Hiring Pipeline</div>
                <div className="reports-pipeline">
                  {PIPELINE_STAGES.map((s) => {
                    const count = pipeline?.[s.key] ?? 0;
                    const width = Math.round((count / pipelineMax) * 100);
                    return (
                      <div key={s.key} className="reports-pipe-row">
                        <span className="reports-pipe-count">{count}</span>
                        <span className="reports-pipe-label">{s.label}</span>
                        <div className="reports-pipe-bar-track">
                          <div
                            className="reports-pipe-bar"
                            style={{ width: `${width}%`, background: s.color }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Right: job table + metric tiles */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                <div className="reports-panel reports-panel--flex">
                  <div className="reports-panel-title">Job Performance</div>
                  {(data?.job_performance || []).length === 0 ? (
                    <p className="muted" style={{ fontSize: "0.85rem" }}>No ranked jobs yet.</p>
                  ) : (
                    <div className="reports-job-table-wrap">
                      <table className="reports-job-table">
                        <thead>
                          <tr>
                            <th>Job Title</th>
                            <th>Avg Match</th>
                            <th>Hires</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data?.job_performance || []).map((j) => (
                            <tr key={j.job_external_id}>
                              <td>{j.job_title}</td>
                              <td className="reports-job-match">{j.avg_match_score}%</td>
                              <td className="reports-job-hires">{j.hires}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                {/* Metric tiles */}
                <div className="reports-metric-tiles">
                  <div className="reports-metric-tile">
                    <div className="reports-metric-label">Time Saved</div>
                    <div className="reports-metric-value">{data?.time_saved_pct ?? 0}<span className="reports-metric-unit">%</span></div>
                  </div>
                  <div className="reports-metric-tile">
                    <div className="reports-metric-label">Shortlist Accuracy</div>
                    <div className="reports-metric-value">{data?.shortlist_accuracy_pct ?? 0}<span className="reports-metric-unit">%</span></div>
                  </div>
                </div>
              </div>
            </div>

            {/* AI vs Manual Screening comparison */}
            <div className="reports-panel reports-screening">
              <div className="reports-panel-title">Screening Contribution — AI vs Manual</div>
              <div className="reports-screen-subtitle">
                Of all candidates who reached shortlist or beyond, what share were surfaced by AI vs picked manually?
              </div>
              <div className="reports-screen-compare">
                {(() => {
                  const ai = data?.ai_screening_pct ?? 0;
                  const manual = data?.manual_screening_pct ?? 0;
                  return (
                    <>
                      {[
                        { label: "AI Screening", pct: ai, color: "rgba(56,189,248,0.9)", pill: "AI-ranked" },
                        { label: "Manual Screening", pct: manual, color: "rgba(168,85,247,0.8)", pill: "Unranked" },
                      ].map((row) => (
                        <div key={row.label} className="reports-screen-row">
                          <div className="reports-screen-label">
                            {row.label}
                            <span className="reports-screen-pill">{row.pill}</span>
                          </div>
                          <div className="reports-screen-track">
                            <div
                              className="reports-screen-fill"
                              style={{
                                width: `${row.pct}%`,
                                background: row.color,
                              }}
                            />
                          </div>
                          <div className="reports-screen-pct">
                            {row.pct}%
                            {ai > 0 && manual > 0 && row.label === "AI Screening" && ai > manual && (
                              <span className="reports-screen-badge reports-screen-badge--up">
                                +{ai - manual}pp
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                      {(ai > 0 || manual > 0) && (
                        <p className="reports-screen-insight">
                          {ai > manual
                            ? `AI is driving the majority — ${ai}% of shortlisted candidates were AI-ranked.`
                            : manual > ai
                            ? `Manual picks are leading at ${manual}% vs AI's ${ai}%. Consider running more matches to let AI contribute.`
                            : `AI and manual picks are contributing equally at ${ai}% each.`}
                        </p>
                      )}
                      {ai === 0 && manual === 0 && (
                        <p className="reports-screen-insight muted">
                          No progression data yet. Move candidates to shortlist or beyond to see the comparison.
                        </p>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
          </>
        )}
      </div>
    </DashFrame>
  );
}
