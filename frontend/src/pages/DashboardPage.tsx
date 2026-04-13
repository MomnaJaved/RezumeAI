import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard, fetchDashboardWidgets, type DashboardData, type DashboardWidgets } from "../api";
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

export default function DashboardPage() {
  const toast = useToast();
  const lastPollErr = useRef<string | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [widgets, setWidgets] = useState<DashboardWidgets | null>(null);
  const [widgetsErr, setWidgetsErr] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: Error) => toast.error(e.message));
  }, [toast]);

  useEffect(() => {
    let cancelled = false;
    fetchDashboardWidgets()
      .then((w) => {
        if (cancelled) return;
        setWidgets(w);
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
  }, []);

  const overview = data?.overview;
  const { items: notifications, pollErr: notificationsPollErr } = useActivityNotifications(data?.notifications);

  useEffect(() => {
    if (notificationsPollErr && notificationsPollErr !== lastPollErr.current) {
      lastPollErr.current = notificationsPollErr;
      toast.error(notificationsPollErr);
    }
    if (!notificationsPollErr) lastPollErr.current = null;
  }, [notificationsPollErr, toast]);

  return (
    <DashFrame>
      <h1 className="dash-title">Build Your Talent pipeline</h1>

      <section className="dash-lower">
        <div className="dash-panel">
          <h2>Overview</h2>
          <div className="dash-kv">
            <div className="row">
              <span>Total Candidate</span>
              <strong>{overview ? fmt(overview.candidates_total) : "—"}</strong>
            </div>
            <div className="row">
              <span>Active Jobs</span>
              <strong>{overview ? fmt(overview.jobs_total) : "—"}</strong>
            </div>
            <div className="row">
              <span>Queued</span>
              <strong>{overview ? fmt(overview.ingestions_queued) : "—"}</strong>
            </div>
            <div className="row">
              <span>Processing</span>
              <strong>{overview ? fmt(overview.ingestions_processing) : "—"}</strong>
            </div>
            <div className="row">
              <span>New Candidates Today</span>
              <strong>{overview ? fmt(overview.new_candidates_24h) : "—"}</strong>
            </div>
            <div className="row">
              <span>Done (24h)</span>
              <strong>{overview ? fmt(overview.ingestions_done_24h) : "—"}</strong>
            </div>
          </div>
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
        !widgetsErr && (
          <p className="muted dash-widgets-loading">Loading dashboard widgets…</p>
        )
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
