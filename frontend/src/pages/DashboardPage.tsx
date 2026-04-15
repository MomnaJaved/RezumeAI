import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchDashboard,
  fetchDashboardWidgets,
  fetchRecentIngestions,
  type DashboardData,
  type DashboardWidgets,
  type IngestionItem,
} from "../api";
import ActivityNotificationList from "../components/ActivityNotificationList";
import {
  DashboardApplicantTracker,
  DashboardCandidateSummary,
  DashboardJobsPie,
} from "../components/DashboardWidgets";
import DashFrame from "../DashFrame";
import { useActivityNotifications } from "../hooks/useActivityNotifications";
import { useToast } from "../toast";

function fmt(n: number): string {
  return new Intl.NumberFormat().format(n);
}

type IngestOverviewKind = "queued" | "processing" | "done";

const INGEST_LABELS: Record<IngestOverviewKind, string> = {
  queued: "Queued uploads",
  processing: "Processing",
  done: "Completed (last 24h)",
};

export default function DashboardPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const lastPollErr = useRef<string | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [widgets, setWidgets] = useState<DashboardWidgets | null>(null);
  const [widgetsErr, setWidgetsErr] = useState<string | null>(null);

  const [ingestOpen, setIngestOpen] = useState<IngestOverviewKind | null>(null);
  const [ingestRows, setIngestRows] = useState<IngestionItem[]>([]);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestErr, setIngestErr] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: Error) => toast.error(e.message));
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    fetchDashboardWidgets()
      .then((w) => {
        if (!cancelled) setWidgets(w);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setWidgetsErr(e.message);
          toast.error(e.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [toast]);

  useEffect(() => {
    if (!ingestOpen) {
      setIngestRows([]);
      setIngestErr(null);
      setIngestLoading(false);
      return;
    }
    let cancelled = false;
    setIngestLoading(true);
    setIngestErr(null);
    fetchRecentIngestions(ingestOpen, {
      sinceHours: ingestOpen === "done" ? 24 : undefined,
      limit: 30,
    })
      .then((rows) => {
        if (!cancelled) setIngestRows(rows);
      })
      .catch((e: Error) => {
        if (!cancelled) setIngestErr(e.message);
      })
      .finally(() => {
        if (!cancelled) setIngestLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ingestOpen]);

  const toggleIngest = useCallback((kind: IngestOverviewKind) => {
    setIngestOpen((prev) => (prev === kind ? null : kind));
  }, []);

  const overview = data?.overview;
  const { items: notifications, pollErr: notificationsPollErr } = useActivityNotifications(data?.notifications, {
    toastOnNew: true,
  });

  useEffect(() => {
    if (notificationsPollErr && notificationsPollErr !== lastPollErr.current) {
      lastPollErr.current = notificationsPollErr;
      toast.error("Something went wrong. Please try again.");
    }
    if (!notificationsPollErr) lastPollErr.current = null;
  }, [notificationsPollErr, toast]);

  return (
    <DashFrame>
      <h1 className="dash-title">Build Your Talent pipeline</h1>

      <section className="dash-lower">
        <div className="dash-panel">
          <h2>Overview</h2>
          <p className="dash-overview-hint muted">Click a row for quick navigation or to expand upload details.</p>
          <div className="dash-kv">
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => navigate("/candidates")}
              title="Open candidates list"
            >
              <span>Total Candidate</span>
              <strong>{overview ? fmt(overview.candidates_total) : "—"}</strong>
            </button>
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => navigate("/jobs")}
              title="Open jobs list"
            >
              <span>Active Jobs</span>
              <strong>{overview ? fmt(overview.jobs_total) : "—"}</strong>
            </button>
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => toggleIngest("queued")}
              title="Show recent queued uploads"
              aria-expanded={ingestOpen === "queued"}
            >
              <span>Queued</span>
              <strong>{overview ? fmt(overview.ingestions_queued) : "—"}</strong>
            </button>
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => toggleIngest("processing")}
              title="Show items currently processing"
              aria-expanded={ingestOpen === "processing"}
            >
              <span>Processing</span>
              <strong>{overview ? fmt(overview.ingestions_processing) : "—"}</strong>
            </button>
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => navigate("/candidates?sort=created_desc")}
              title="Candidates sorted by newest first"
            >
              <span>New Candidates Today</span>
              <strong>{overview ? fmt(overview.new_candidates_24h) : "—"}</strong>
            </button>
            <button
              type="button"
              className="dash-kv-row dash-kv-row--click"
              onClick={() => toggleIngest("done")}
              title="Show uploads finished in the last 24 hours"
              aria-expanded={ingestOpen === "done"}
            >
              <span>Done (24h)</span>
              <strong>{overview ? fmt(overview.ingestions_done_24h) : "—"}</strong>
            </button>
          </div>

          {ingestOpen ? (
            <div className="dash-overview-detail">
              <div className="dash-overview-detail-head">
                <h3 className="dash-overview-detail-title">{INGEST_LABELS[ingestOpen]}</h3>
                <div className="dash-overview-detail-actions">
                  <Link to="/candidates/add" className="dash-widget-link">
                    Upload &amp; track →
                  </Link>
                  <button type="button" className="small-btn" onClick={() => setIngestOpen(null)}>
                    Close
                  </button>
                </div>
              </div>
              {ingestLoading ? (
                <p className="muted dash-overview-detail-body">Loading…</p>
              ) : ingestErr ? (
                <p className="dash-overview-detail-body" style={{ color: "#fca5a5" }}>
                  {ingestErr}
                </p>
              ) : ingestRows.length === 0 ? (
                <p className="muted dash-overview-detail-body">No rows in this state right now.</p>
              ) : (
                <ul className="dash-overview-ingest-list">
                  {ingestRows.map((r) => (
                    <li key={r.id} className="dash-overview-ingest-item">
                      <span className="dash-overview-ingest-file">{r.filename || "—"}</span>
                      <span className={`dash-overview-ingest-status dash-overview-ingest-status--${r.status}`}>
                        {r.status}
                      </span>
                      {r.candidate_external_id && r.status === "done" ? (
                        <Link
                          className="dash-widget-link"
                          to={`/candidates/lookup/${encodeURIComponent(r.candidate_external_id)}`}
                        >
                          Open candidate
                        </Link>
                      ) : (
                        <span className="muted">{r.candidate_external_id || "—"}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </div>

        <div className="dash-panel dash-panel-notifications">
          <h2>Notifications</h2>
          <p className="dash-live-hint muted">
            Live updates. <Link to="/inbox">Open full inbox</Link>
          </p>
          <div className="dash-notifications-scroll">
            <ActivityNotificationList items={notifications} />
          </div>
        </div>
      </section>

      {widgets ? (
        <section className="dash-widgets">
          <div className="dash-widgets-top">
            <DashboardApplicantTracker pipeline={widgets.pipeline} />
            <DashboardJobsPie chart={widgets.jobs_chart} />
          </div>
          <DashboardCandidateSummary rows={widgets.candidate_preview} />
        </section>
      ) : (
        !widgetsErr && <p className="muted dash-widgets-loading">Loading dashboard widgets…</p>
      )}

      <footer className="dash-site-footer">
        <span>© {new Date().getFullYear()} Rezume AI</span>
        <span className="dash-footer-sep">·</span>
        <a href="#">Privacy Policy</a>
        <span className="dash-footer-sep">·</span>
        <a href="#">Terms</a>
        <span className="dash-footer-sep">·</span>
        <a href="#">Contact</a>
      </footer>
    </DashFrame>
  );
}
