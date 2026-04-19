import { useEffect, useState } from "react";
import { fetchCandidate, fetchCandidateMe, fetchCandidateMatches, type CandidateMe } from "../../api";

export default function CandidateProfilePage() {
  const [me, setMe] = useState<CandidateMe | null>(null);
  const [matches, setMatches] = useState<{ job_external_id: string; job_title: string; match_score: number }[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchCandidateMe();
        if (cancelled) return;
        setMe(m);
        if (!m.linked || !m.candidate_id) {
          setMatches([]);
          return;
        }
        await fetchCandidate(m.candidate_id);
        const mm = await fetchCandidateMatches(m.candidate_id!, 25);
        if (!cancelled) setMatches(mm.items ?? []);
      } catch (e) {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Could not load profile");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (err) {
    return (
      <div>
        <h1 className="dash-title">Profile</h1>
        <p className="dash-inbox-banner dash-inbox-banner-error">{err}</p>
      </div>
    );
  }

  if (me && !me.linked) {
    return (
      <div>
        <h1 className="dash-title">Profile</h1>
        <p style={{ marginTop: "0.75rem", color: "rgba(255,255,255,0.7)", maxWidth: "36rem" }}>
          Upload a resume from the <strong>Resume</strong> tab to create your pool profile. Recruiters use the same record you see here.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="dash-title">Your profile</h1>
      <p style={{ marginTop: "0.35rem", color: "rgba(255,255,255,0.65)" }}>Same candidate record recruiters rank against jobs.</p>
      {me?.linked ? (
        <div style={{ marginTop: "1rem", fontSize: "0.92rem" }}>
          <p>
            <strong>{me.full_name}</strong> {me.title ? `— ${me.title}` : ""}
          </p>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            Pool status: <strong>{me.status || "—"}</strong>
          </p>
          <p>
            Best job match score:{" "}
            <strong>{me.best_job_match_score != null ? Math.round(me.best_job_match_score) : "—"}</strong>
            {me.best_job_external_id ? ` (${me.best_job_external_id})` : ""}
          </p>
        </div>
      ) : null}
      <h2 style={{ marginTop: "1.5rem", fontSize: "1rem" }}>Match scores (ranked jobs)</h2>
      {matches.length === 0 ? (
        <p style={{ marginTop: "0.5rem", color: "rgba(255,255,255,0.55)" }}>No saved rankings yet — apply to jobs so recruiters can shortlist and rank you.</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, marginTop: "0.65rem", display: "grid", gap: "0.4rem", maxWidth: "40rem" }}>
          {matches.map((m) => (
            <li key={m.job_external_id} style={{ fontSize: "0.88rem", display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <span>
                {m.job_title} <span style={{ color: "rgba(255,255,255,0.45)" }}>({m.job_external_id})</span>
              </span>
              <strong>{Math.round(m.match_score)}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
