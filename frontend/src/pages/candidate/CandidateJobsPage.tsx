import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { candidateApplyToJob, fetchCandidateJobs, fetchCandidateMe, type CandidateJobListItem, type CandidateMe } from "../../api";
import { useToast } from "../../toast";

export default function CandidateJobsPage() {
  const toast = useToast();
  const [me, setMe] = useState<CandidateMe | null>(null);
  const [meLoading, setMeLoading] = useState(true);
  const [roleQ, setRoleQ] = useState("");
  const [workLoc, setWorkLoc] = useState("");
  const [country, setCountry] = useState("");
  const [city, setCity] = useState("");
  const [items, setItems] = useState<CandidateJobListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [applyHint, setApplyHint] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchCandidateMe();
        if (!cancelled) setMe(m);
      } catch {
        if (!cancelled) setMe(null);
      } finally {
        if (!cancelled) setMeLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(
    async (opts?: { soft?: boolean }) => {
      if (!opts?.soft) setLoading(true);
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
        if (!opts?.soft) setLoading(false);
      }
    },
    [roleQ, workLoc, country, city, toast],
  );

  useEffect(() => {
    const t = window.setTimeout(() => void load(), 300);
    return () => window.clearTimeout(t);
  }, [load]);

  async function apply(ext: string) {
    const id = ext.trim();
    setApplyHint(null);
    if (me && !me.linked) {
      setApplyHint("Upload your resume on Profile first — that creates your candidate profile for recruiters.");
      toast.info("Add your resume on Profile before you can apply.");
      return;
    }
    setBusyId(id);
    try {
      const r = await candidateApplyToJob(id);
      if (r.status === "already_applied") toast.info("You already applied to this job.");
      else if (r.status === "applied") toast.success("Application sent.");
      if (r.status === "applied" || r.status === "already_applied") {
        await load({ soft: true });
        setItems((prev) => prev.map((item) => (item.external_id.trim() === id ? { ...item, applied: true } : item)));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Apply failed";
      setApplyHint(msg);
      toast.error(msg);
    } finally {
      setBusyId(null);
    }
  }

  /** After /candidate/me loads: require linked pool row (resume) before Apply. If me failed to load, allow click and let the API respond. */
  const canApply = !meLoading && (me == null || me.linked);

  return (
    <div>
      <h1 className="dash-title">Open jobs</h1>
      <p style={{ marginTop: "0.35rem", color: "rgba(255,255,255,0.65)" }}>{total} active role{total === 1 ? "" : "s"}</p>
      {!meLoading && me && !me.linked ? (
        <div
          role="status"
          style={{
            marginTop: "1rem",
            padding: "0.85rem 1rem",
            borderRadius: 12,
            border: "1px solid rgba(251,191,36,0.45)",
            background: "rgba(251,191,36,0.1)",
            color: "#fde68a",
            maxWidth: "48rem",
            lineHeight: 1.45,
          }}
        >
          <strong>Resume required to apply.</strong> Upload a resume on{" "}
          <Link to="/candidate/profile" style={{ color: "#fef3c7", textDecoration: "underline" }}>
            Profile
          </Link>{" "}
          so we can create your candidate record. After that, Apply works and recruiters can see you for this job.
        </div>
      ) : null}
      {applyHint ? (
        <p role="alert" style={{ marginTop: "0.75rem", color: "#fca5a5", maxWidth: "48rem" }}>
          {applyHint}
        </p>
      ) : null}
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
              {j.applied ? (
                <button type="button" className="dash-btn dash-btn-xs" disabled>
                  Applied
                </button>
              ) : (
                <button
                  type="button"
                  className="dash-btn dash-btn-xs"
                  disabled={!canApply || busyId === j.external_id.trim()}
                  title={!canApply ? "Upload your resume on Profile to enable Apply" : undefined}
                  onClick={() => void apply(j.external_id)}
                >
                  {busyId === j.external_id.trim()
                    ? "…"
                    : me && !me.linked && !meLoading
                      ? "Apply (needs resume)"
                      : "Apply"}
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
