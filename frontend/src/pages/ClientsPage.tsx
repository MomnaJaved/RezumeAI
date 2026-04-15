import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import DashFrame from "../DashFrame";
import { ClientDto, fetchClients } from "../api";
import { useToast } from "../toast";

function norm(s: string) {
  return (s || "").trim().toLowerCase();
}

export default function ClientsPage() {
  const toast = useToast();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ClientDto[]>([]);

  const q = sp.get("q") ?? "";
  const status = sp.get("status") ?? "";
  const sortBy = sp.get("sort") ?? "created_desc";

  useEffect(() => {
    let mounted = true;
    async function run() {
      setLoading(true);
      try {
        const res = await fetchClients(status ? { status: status as "active" | "inactive" } : undefined);
        if (!mounted) return;
        setItems(res || []);
      } catch (e) {
        toast.error((e as Error).message || "Failed to load clients");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void run();
    return () => {
      mounted = false;
    };
  }, [status, toast]);

  const filtered = useMemo(() => {
    const needle = norm(q);
    const base = !needle
      ? items
      : items.filter((c) => {
          const hay = `${c.name || ""} ${c.company_name || ""} ${c.contact_person || ""} ${c.email || ""}`.toLowerCase();
          return hay.includes(needle);
        });

    const rows = [...base];
    if (sortBy === "created_asc") {
      rows.sort((a, b) => (a.created_at || "").localeCompare(b.created_at || ""));
    } else if (sortBy === "name_asc") {
      rows.sort((a, b) => (a.name || "").localeCompare(b.name || "", undefined, { sensitivity: "base" }));
    } else if (sortBy === "name_desc") {
      rows.sort((a, b) => (b.name || "").localeCompare(a.name || "", undefined, { sensitivity: "base" }));
    } else {
      // created_desc (default)
      rows.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    }
    return rows;
  }, [items, q, sortBy]);

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Clients: {filtered.length}</div>
            <div className="cand-search">
              <input
                value={q}
                placeholder="Search clients by name, company, email…"
                onChange={(e) => {
                  const v = e.target.value;
                  setSp((prev) => {
                    const next = new URLSearchParams(prev);
                    if (v) next.set("q", v);
                    else next.delete("q");
                    return next;
                  });
                }}
              />
            </div>
            <Link to="/clients/add" className="cand-add-btn" title="Add client" aria-label="Add client">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
            </Link>
          </div>
          <div className="cand-toolbar-row">
            <span className="cand-toolbar-label muted">Filter By</span>
            <select
              value={status || "all"}
              onChange={(e) => {
                const v = e.target.value;
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  if (v && v !== "all") next.set("status", v);
                  else next.delete("status");
                  return next;
                });
              }}
              aria-label="Status filter"
            >
              <option value="all">Active/Inactive</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <select
              value={sortBy}
              onChange={(e) => {
                const v = e.target.value || "created_desc";
                setSp((prev) => {
                  const next = new URLSearchParams(prev);
                  if (v && v !== "created_desc") next.set("sort", v);
                  else next.delete("sort");
                  return next;
                });
              }}
              aria-label="Sort order"
            >
              <option value="created_desc">Newest</option>
              <option value="created_asc">Oldest</option>
              <option value="name_asc">A–Z</option>
              <option value="name_desc">Z–A</option>
            </select>
          </div>
        </div>
      }
    >
      <div className="jobs-table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Client Name</th>
              <th>Contact Person</th>
              <th>Email</th>
              <th>Active jobs</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="muted">
                  Loading…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No clients found.
                </td>
              </tr>
            ) : (
              filtered.map((c) => (
                <tr
                  key={c.id}
                  className="jobs-row"
                  onClick={() => nav(`/clients/${encodeURIComponent(c.id)}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") nav(`/clients/${encodeURIComponent(c.id)}`);
                  }}
                >
                  <td>{c.name}</td>
                  <td>{c.contact_person || <span className="muted">—</span>}</td>
                  <td>{c.email || <span className="muted">—</span>}</td>
                  <td>{typeof c.active_jobs === "number" ? c.active_jobs : 0}</td>
                  <td>
                    <span className={`job-pill job-status ${(c.status || "active").toLowerCase()}`}>
                      {(c.status || "active").toLowerCase() === "inactive" ? "Inactive" : "Active"}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </DashFrame>
  );
}

