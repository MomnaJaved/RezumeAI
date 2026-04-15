import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { fetchClients, fetchJobsPage, type ClientDto, type Job } from "../api";
import DashFrame from "../DashFrame";
import JobModal from "../components/JobModal";
import { useToast } from "../toast";

export default function JobsPage() {
  const toast = useToast();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [searchParams, setSearchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [clients, setClients] = useState<ClientDto[]>([]);
  const [clientId, setClientId] = useState("all");
  const [status, setStatus] = useState("all");
  const [sortBy, setSortBy] = useState("created_desc");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchClients({ status: "active" })
      .then(setClients)
      .catch(() => setClients([]));
  }, []);

  const selectedJobExternalId = (searchParams.get("job") || "").trim();
  useEffect(() => {
    const st = (searchParams.get("status") || "").trim();
    if (st) setStatus(st);
  }, [searchParams]);
  const openJob = (externalId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("job", externalId);
    setSearchParams(next, { replace: true });
  };
  const closeJob = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("job");
    setSearchParams(next, { replace: true });
  };

  useEffect(() => setPage(1), [q, clientId, status, sortBy]);

  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await fetchJobsPage({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          q: q.trim() || undefined,
          client_id: clientId !== "all" ? clientId : undefined,
          status: status !== "all" ? status : undefined,
          sort: sortBy,
        });
        if (cancelled) return;
        setJobs(res.items);
        setTotal(res.total);
      } catch (e) {
        if (cancelled) return;
        setJobs([]);
        setTotal(0);
        toast.error((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [toast, page, q, clientId, status, sortBy]);

  const pageRows = useMemo(() => jobs, [jobs]);

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Jobs: {total}</div>
            <div className="cand-search">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search jobs by name, client name…"
              />
            </div>
            <Link to="/jobs/add" className="cand-add-btn" title="Add job" aria-label="Add job">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
            </Link>
          </div>
          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">Filter By</span>
            <select value={clientId} onChange={(e) => setClientId(e.target.value)} aria-label="Clients filter">
              <option value="all">Clients</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
              <option value="all">Status</option>
              <option value="active">Active</option>
              <option value="on_hold">On hold</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)} aria-label="Sort order">
              <option value="created_desc">Newest</option>
              <option value="created_asc">Oldest</option>
              <option value="title_asc">A–Z</option>
              <option value="title_desc">Z–A</option>
            </select>
          </div>
        </div>
      }
    >
      {loading ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            Loading jobs…
          </p>
        </div>
      ) : total === 0 ? (
        <div className="dash-panel">
          <p className="muted" style={{ margin: 0 }}>
            No jobs match your filters.
          </p>
        </div>
      ) : (
        <>
          <div className="jobs-table-wrap">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th style={{ width: "36%" }}>Job Title</th>
                  <th style={{ width: "20%" }}>Client Name</th>
                  <th style={{ width: "12%" }}>Applicants</th>
                  <th style={{ width: "14%" }}>Created On</th>
                  <th style={{ width: "10%" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.map((j) => (
                  <tr key={j.id} className="jobs-row" onClick={() => openJob(j.external_id)} role="button" tabIndex={0}>
                    <td>
                      <span className="muted" style={{ marginRight: "0.45rem", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }}>
                        {j.external_id}
                      </span>
                      {j.title || "—"}
                    </td>
                    <td className="muted">{j.client_name || "—"}</td>
                    <td className="muted">—</td>
                    <td>{j.created_at ? new Date(j.created_at).toLocaleDateString() : "—"}</td>
                    <td>
                      <span className={`job-status ${(j.status || "active").toLowerCase()}`}>
                        {(j.status || "active").toLowerCase() === "on_hold"
                          ? "On hold"
                          : (j.status || "active")[0].toUpperCase() + (j.status || "active").slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="jobs-pager">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              « Previous
            </button>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Page {page} of {totalPages}
            </div>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next »
            </button>
          </div>
        </>
      )}

      <JobModal
        open={Boolean(selectedJobExternalId)}
        externalId={selectedJobExternalId}
        onClose={closeJob}
        onJobUpdated={(updated) => {
          setJobs((prev) => prev.map((j) => (j.external_id === updated.external_id ? updated : j)));
        }}
        onJobDeleted={(deletedExternalId) => {
          setJobs((prev) => prev.filter((j) => j.external_id !== deletedExternalId));
        }}
      />
    </DashFrame>
  );
}
