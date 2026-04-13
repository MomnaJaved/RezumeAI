import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchSavedRankings,
  fetchJobByExternalId,
  rankAndSave,
  rankFromDatabase,
  rankJobPreview,
  submitRankingFeedback,
  type Job,
  type RankedCandidate,
  type RankingFeedbackAction,
} from "../api";

function mapSavedRow(row: {
  candidate_external_id: string;
  cross_encoder_score: number;
  sbert_similarity: number;
  candidate_name: string;
  candidate_title: string;
  candidate_role: string;
  years_experience: number | null;
  highest_degree: string;
  skills_summary: string;
}): RankedCandidate {
  return {
    candidate_id: row.candidate_external_id,
    cross_encoder_score: row.cross_encoder_score,
    sbert_similarity: row.sbert_similarity,
    candidate_name: row.candidate_name,
    candidate_title: row.candidate_title,
    candidate_role: row.candidate_role,
    years_experience: row.years_experience,
    highest_degree: row.highest_degree,
    skills_summary: row.skills_summary,
  };
}

export default function JobDetailPage() {
  const { externalId = "" } = useParams<{ externalId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [preview, setPreview] = useState<RankedCandidate[]>([]);
  const [dbPreview, setDbPreview] = useState<RankedCandidate[]>([]);
  const [saved, setSaved] = useState<RankedCandidate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setJob(null);
    fetchJobByExternalId(externalId)
      .then(setJob)
      .catch(() => setJob(null));
    fetchSavedRankings(externalId)
      .then((r) => setSaved(r.rankings.map(mapSavedRow)))
      .catch(() => setSaved(null));
  }, [externalId]);

  async function runPreview() {
    setLoading(true);
    setError(null);
    try {
      const res = await rankJobPreview(externalId, 50);
      setPreview(res.candidates);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function runDbRank(persist: boolean) {
    setLoading(true);
    setError(null);
    try {
      const res = await rankFromDatabase(externalId, { limit: 400, topReturn: 40, persist });
      const mapped = res.rankings.map(mapSavedRow);
      setDbPreview(mapped);
      if (persist) setSaved(mapped);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function runSave() {
    setLoading(true);
    setError(null);
    try {
      const res = await rankAndSave(externalId, 50);
      setSaved(res.rankings.map(mapSavedRow));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <p>
        <Link to="/jobs">← Jobs</Link>
      </p>
      <h1>Job {externalId}</h1>
      {job ? (
        <section className="card" style={{ marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "baseline" }}>
            <div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                Title
              </div>
              <div style={{ fontWeight: 600 }}>{job.title || "—"}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                Department
              </div>
              <div style={{ fontWeight: 600 }}>{job.department || "—"}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                Min exp
              </div>
              <div style={{ fontWeight: 600 }}>{job.min_experience ?? "—"}</div>
            </div>
            <div>
              <div className="muted" style={{ fontSize: "0.85rem" }}>
                Education
              </div>
              <div style={{ fontWeight: 600 }}>{job.education_required || "—"}</div>
            </div>
          </div>
          <div style={{ marginTop: "0.75rem" }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Skills
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{job.skills || "—"}</div>
          </div>
          <div style={{ marginTop: "0.75rem" }}>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Description
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{job.description || "—"}</div>
          </div>
        </section>
      ) : (
        <p className="muted" style={{ marginBottom: "1.25rem" }}>
          Job details not found in DB (rank endpoints may still work via CSV).
        </p>
      )}
      <section style={{ marginBottom: "1.25rem" }}>
        <h2 className="h3like">Recommended for hiring-style screening</h2>
        <p className="muted">
          The <strong>cross-encoder</strong> reads the job and each resume together and is trained on your
          match pipeline (closer to “fit” than generic similarity).{" "}
          <strong>Database ranking</strong> scores up to 800 people in the database (synced CSV +{" "}
          <Link to="/upload">uploads</Link>), so strong candidates are not dropped just because SBERT retrieval
          ranked them low.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" className="primary" disabled={loading} onClick={() => void runDbRank(false)}>
            Preview DB rank (cross-encoder)
          </button>
          <button type="button" className="primary" disabled={loading} onClick={() => void runDbRank(true)}>
            Save DB ranking
          </button>
        </div>
      </section>
      <section style={{ marginBottom: "1rem" }}>
        <h2 className="h3like">Fast retrieval demo (SBERT shortlist)</h2>
        <p className="muted">
          Uses an offline MiniLM embedding shortlist, then reranks with the cross-encoder. Quick to run, but{" "}
          <strong>anyone not in the shortlist is never scored</strong> here—use DB ranking above for a fairer
          pool. SBERT cosine and cross-encoder scores measure different things; trust <strong>rank order</strong>{" "}
          from the cross-encoder for decisions, not the two numbers side by side.
        </p>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <button type="button" disabled={loading} onClick={() => void runPreview()}>
            Preview SBERT shortlist
          </button>
          <button type="button" disabled={loading} onClick={() => void runSave()}>
            Save SBERT shortlist ranking
          </button>
        </div>
      </section>
      {error ? <p className="error">{error}</p> : null}

      {saved && saved.length > 0 ? (
        <section>
          <h2>Saved rankings</h2>
          <p className="muted">Order reflects the last save (DB or shortlist). Prefer DB saves for hiring-style pools.</p>
          <RankTable rows={saved} jobExternalId={externalId} />
        </section>
      ) : (
        <p className="muted">No saved rankings yet (or job not in DB).</p>
      )}

      {preview.length > 0 ? (
        <section style={{ marginTop: "1.5rem" }}>
          <h2>Preview — SBERT shortlist (not saved)</h2>
          <RankTable rows={preview} jobExternalId={externalId} />
        </section>
      ) : null}

      {dbPreview.length > 0 ? (
        <section style={{ marginTop: "1.5rem" }}>
          <h2>Database rank preview (cross-encoder, full pool)</h2>
          <RankTable rows={dbPreview} jobExternalId={externalId} />
        </section>
      ) : null}
    </div>
  );
}

function fmtExp(y: number | null | undefined): string {
  if (y === null || y === undefined) return "—";
  return Number.isFinite(y) ? String(y) : "—";
}

function RankTable({ rows, jobExternalId }: { rows: RankedCandidate[]; jobExternalId: string }) {
  const showSbert = rows.some((r) => Math.abs(r.sbert_similarity) > 1e-8);
  const showFeedback = Boolean(jobExternalId.trim());
  const [fbBusy, setFbBusy] = useState<Record<string, boolean>>({});
  const [fbStatus, setFbStatus] = useState<Record<string, string>>({});

  const sendFeedback = useCallback(
    async (candidateId: string, rank1Based: number, score: number, action: RankingFeedbackAction) => {
      setFbBusy((b) => ({ ...b, [candidateId]: true }));
      setFbStatus((s) => {
        const next = { ...s };
        delete next[candidateId];
        return next;
      });
      try {
        await submitRankingFeedback({
          job_external_id: jobExternalId.trim(),
          candidate_external_id: candidateId,
          action,
          rank_position_shown: rank1Based,
          model_score_at_feedback: score,
        });
        setFbStatus((s) => ({ ...s, [candidateId]: "Recorded" }));
      } catch (e) {
        setFbStatus((s) => ({ ...s, [candidateId]: (e as Error).message || "Failed" }));
      } finally {
        setFbBusy((b) => ({ ...b, [candidateId]: false }));
      }
    },
    [jobExternalId],
  );

  return (
    <div className="card" style={{ padding: 0, overflow: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>ID</th>
            <th>Name</th>
            <th>Title</th>
            <th>Role</th>
            <th>Exp (yrs)</th>
            <th>Degree</th>
            <th>Skills</th>
            <th>Match (cross-encoder)</th>
            {showSbert ? <th>SBERT recall</th> : null}
            {showFeedback ? <th>Feedback</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.candidate_id}>
              <td>{i + 1}</td>
              <td className="muted" style={{ maxWidth: "7rem", wordBreak: "break-all" }}>
                {r.candidate_id}
              </td>
              <td>{r.candidate_name || "—"}</td>
              <td>{r.candidate_title || "—"}</td>
              <td>{r.candidate_role || "—"}</td>
              <td>{fmtExp(r.years_experience)}</td>
              <td>{r.highest_degree || "—"}</td>
              <td style={{ maxWidth: "14rem", fontSize: "0.8rem" }} title={r.skills_summary}>
                {r.skills_summary ? `${r.skills_summary.slice(0, 80)}${r.skills_summary.length > 80 ? "…" : ""}` : "—"}
              </td>
              <td>{r.cross_encoder_score.toFixed(4)}</td>
              {showSbert ? <td>{r.sbert_similarity.toFixed(4)}</td> : null}
              {showFeedback ? (
                <td style={{ minWidth: "11rem", verticalAlign: "top" }}>
                  <div className="rank-feedback-actions">
                    <button
                      type="button"
                      disabled={!!fbBusy[r.candidate_id]}
                      title="Strong positive — maps to training label 1.0"
                      onClick={() => void sendFeedback(r.candidate_id, i + 1, r.cross_encoder_score, "selected")}
                    >
                      Select
                    </button>
                    <button
                      type="button"
                      disabled={!!fbBusy[r.candidate_id]}
                      title="Positive — maps to training label 0.85"
                      onClick={() => void sendFeedback(r.candidate_id, i + 1, r.cross_encoder_score, "shortlisted")}
                    >
                      Shortlist
                    </button>
                    <button
                      type="button"
                      disabled={!!fbBusy[r.candidate_id]}
                      title="Negative — maps to training label 0.0"
                      onClick={() => void sendFeedback(r.candidate_id, i + 1, r.cross_encoder_score, "rejected")}
                    >
                      Reject
                    </button>
                  </div>
                  {fbStatus[r.candidate_id] ? (
                    <div
                      className={
                        fbStatus[r.candidate_id] === "Recorded" ? "muted rank-feedback-note" : "error rank-feedback-note"
                      }
                      style={{ marginTop: "0.35rem", fontSize: "0.75rem", wordBreak: "break-word" }}
                    >
                      {fbStatus[r.candidate_id]}
                    </div>
                  ) : null}
                </td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
