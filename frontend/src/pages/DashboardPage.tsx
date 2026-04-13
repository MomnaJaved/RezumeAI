import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard, type DashboardData } from "../api";
import ActivityNotificationList from "../components/ActivityNotificationList";
import DashFrame from "../DashFrame";
import { useActivityNotifications } from "../hooks/useActivityNotifications";

function fmt(n: number): string {
  return new Intl.NumberFormat().format(n);
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboard()
      .then(setData)
      .catch((e: Error) => setErr(e.message));
  }, []);

  const overview = data?.overview;
  const { items: notifications, pollErr: notificationsPollErr } = useActivityNotifications(data?.notifications);

  return (
    <DashFrame>
      <h1 className="dash-title">Build Your Talent Pipeline</h1>
      {err ? <p className="banner banner-error">{err}</p> : null}

      <section className="dash-cards">
        <div className="dash-tile">
            <div className="dash-tile-icon" aria-hidden="true">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
              <div className="dash-tile-body">
                <h3>Create a Candidate</h3>
                <p>Add a new candidate profile or upload a resume.</p>
                <Link to="/upload" className="dash-btn">
                  + Create Candidate
                </Link>
              </div>
        </div>
        <div className="dash-tile">
            <div className="dash-tile-icon" aria-hidden="true">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
                <path d="M3 7h18v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
                <path d="M3 12h18" />
              </svg>
            </div>
              <div className="dash-tile-body">
                <h3>Create a Job</h3>
                <p>Add job details and start screening instantly.</p>
                <Link to="/jobs" className="dash-btn">
                  + Create Job
                </Link>
              </div>
        </div>
        <div className="dash-tile">
            <div className="dash-tile-icon" aria-hidden="true">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 21V7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14" />
                <path d="M7 21v-4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v4" />
                <path d="M8 9h8" />
                <path d="M8 12h8" />
              </svg>
            </div>
              <div className="dash-tile-body">
                <h3>Create a Client</h3>
                <p>Add new client company information and requirements.</p>
                <Link to="/clients" className="dash-btn">
                  + Create Client
                </Link>
              </div>
        </div>
      </section>

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

        <div className="dash-panel">
          <h2>Notifications</h2>
          <p className="dash-live-hint muted">
            Live updates{notificationsPollErr ? ` (refresh error: ${notificationsPollErr})` : ""}.{" "}
            <Link to="/inbox">Open full inbox</Link>
          </p>
          <ActivityNotificationList items={notifications} />
        </div>
      </section>
    </DashFrame>
  );
}

