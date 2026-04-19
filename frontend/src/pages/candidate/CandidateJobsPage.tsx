import { useCallback, useEffect, useState } from "react";
import { candidateApplyToJob, fetchCandidateJobs, type CandidateJobListItem } from "../../api";
import { useToast } from "../../toast";

export default function CandidateJobsPage() {
  const toast = useToast();
  const [roleQ, setRoleQ] = useState("");
  const [workLoc, setWorkLoc] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [items, setItems] = useState<CandidateJobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetchCandidateJobs({
        role_q: roleQ.trim(),
        work_location: workLoc.trim(),
        country: country.trim(),
        city: city.trim(),
        skip: 0,
        limit: 80,
      });
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load jobs");
    } finally {
      setLoading(false);
    }
  }, [roleQ, workLoc, country, city, toast]);

  useEffect(() => {
    const t = window.setTimeout(() => void load(), 300);
    return () => window.clearTimeout(t);
  }, [load]);

  async function apply(ext: string) {
    setBusyId(ext);
    try {
      const r = await candidateApplyToJob(ext);
      if (r.status === "already_applied") toast.info("You already applied to this job.");
      else toast.success("Application sent.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Apply failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <h1 className="dash-title">Open jobs</h1>
      <p style={{ marginTop: "0.35rem", color: "rgba(255,255,255,0.65)" }}>{total} active role{total === 1 ? "" : "s"}</p>
      <div style={{ display: "grid", gap: "0.5rem", marginTop: "1rem", maxWidth: "48rem" }}>
        <input className="dash-inbox-dir-input" placeholder="Role / skills / title search…" value={roleQ} onChange={(e) => setRoleQ(e.target.value)} />
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <input className="dash-inbox-dir-input" style={{ flex: "1 1 140px" }} placeholder="Work location (e.g. remote)" value={workLoc} onChange={(e) => setWorkLoc(e.target.value)} />
          <input className="dash-inbox-dir-input" style={{ flex: "1 1 140px" }} placeholder="Country (description search)" value={country} onChange={(e) => setCountry(e.target.value)} />
          <input className="dash-inbox-dir-input" style={{ flex: "1 1 140px" }} placeholder="City (description search)" value={city} onChange={(e) => setCity(e.target.value)} />
        </div>
      </div>
      {loading ? <p style={{ marginTop: "1rem", color: "rgba(255,255,255,0.55)" }}>Loading…</p> : null}
      <ul style={{ listStyle: "none", padding: 0, marginTop: "1rem", display: "grid", gap: "0.65rem" }}>
        {items.map((j) => (
          <li
            key={j.id}
            style={{
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 12,
              padding: "0.75rem 1rem",
              background: "rgba(2,6,23,0.35)",
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "0.5rem", alignItems: "flex-start" }}>
              <div>
                <strong>{j.title || j.external_id}</strong>
                <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.55)", marginTop: "0.2rem" }}>
                  {j.external_id}
                  {j.client_display ? ` · ${j.client_display}` : ""}
                  {j.work_location ? ` · ${j.work_location}` : ""}
                </div>
              </div>
              <button
                type="button"
                className="dash-btn dash-btn-xs"
                disabled={busyId === j.external_id}
                onClick={() => void apply(j.external_id)}
              >
                {busyId === j.external_id ? "…" : "Apply"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
