import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchJobs, type Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchJobs()
      .then(setJobs)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div>
        <h1>Jobs</h1>
        <p className="error">{error}</p>
        <p className="muted">
          Start Postgres (<code>docker compose up -d postgres</code>), set <code>DATABASE_URL</code>, run{" "}
          <code>python training/scripts/sync_enriched_to_postgres.py</code>, then reload.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1>Jobs</h1>
      {jobs.length === 0 ? (
        <p className="muted">No rows in PostgreSQL yet. Sync CSV with scripts/sync_enriched_to_postgres.py.</p>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Department</th>
                <th>Skills</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link to={`/jobs/${encodeURIComponent(j.external_id)}`}>{j.external_id}</Link>
                  </td>
                  <td>{j.title}</td>
                  <td>{j.department}</td>
                  <td style={{ maxWidth: "18rem", fontSize: "0.85rem" }} title={j.skills || ""}>
                    {j.skills ? `${j.skills.slice(0, 120)}${j.skills.length > 120 ? "…" : ""}` : "—"}
                  </td>
                  <td style={{ maxWidth: "26rem", fontSize: "0.85rem" }} title={j.description || ""}>
                    {j.description ? `${j.description.slice(0, 180)}${j.description.length > 180 ? "…" : ""}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
