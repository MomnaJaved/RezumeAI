import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { fetchCandidateMe, type CandidateMe } from "../../api";

export default function CandidateDashboardPage() {
  const [me, setMe] = useState<CandidateMe | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchCandidateMe();
        if (!cancelled) setMe(m);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Could not load profile");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <h1 className="dash-title">Candidate home</h1>
      <p className="dash-subtitle" style={{ marginTop: "0.35rem", color: "rgba(255,255,255,0.65)", maxWidth: "40rem" }}>
        Discover open roles, track your applications, and keep one resume profile in sync with what recruiters see.
      </p>
      {err ? (
        <p className="dash-inbox-banner dash-inbox-banner-error" role="alert">
          {err}
        </p>
      ) : null}
      <div className="dash-cards" style={{ marginTop: "1.25rem", display: "grid", gap: "0.75rem", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
        <Link to="/candidate/jobs" className="dash-link" style={{ padding: "1rem 1rem", borderRadius: 12 }}>
          <strong>Browse jobs</strong>
          <div style={{ fontSize: "0.8rem", marginTop: "0.35rem", color: "rgba(255,255,255,0.6)" }}>Active listings & filters</div>
        </Link>
        <Link to="/candidate/applications" className="dash-link" style={{ padding: "1rem 1rem", borderRadius: 12 }}>
          <strong>Applications</strong>
          <div style={{ fontSize: "0.8rem", marginTop: "0.35rem", color: "rgba(255,255,255,0.6)" }}>Status per job</div>
        </Link>
        <Link to="/candidate/resume" className="dash-link" style={{ padding: "1rem 1rem", borderRadius: 12 }}>
          <strong>Resume</strong>
          <div style={{ fontSize: "0.8rem", marginTop: "0.35rem", color: "rgba(255,255,255,0.6)" }}>Upload or replace CV</div>
        </Link>
        <Link to="/candidate/profile" className="dash-link" style={{ padding: "1rem 1rem", borderRadius: 12 }}>
          <strong>Profile &amp; scores</strong>
          <div style={{ fontSize: "0.8rem", marginTop: "0.35rem", color: "rgba(255,255,255,0.6)" }}>Match insights</div>
        </Link>
      </div>
      {me ? (
        <div style={{ marginTop: "1.5rem", fontSize: "0.88rem", color: "rgba(255,255,255,0.75)" }}>
          {me.linked ? (
            <p>
              Pool profile <strong>{me.full_name || me.external_id || "linked"}</strong> — best match score:{" "}
              <strong>{me.best_job_match_score != null ? Math.round(me.best_job_match_score) : "—"}</strong>
              {me.best_job_external_id ? ` (${me.best_job_external_id})` : ""}
            </p>
          ) : (
            <p>
              <strong>Next step:</strong> upload a resume on the Resume tab so you appear in the recruiter pool and can apply to jobs.
            </p>
          )}
        </div>
      ) : null}
    </div>
  );
}
