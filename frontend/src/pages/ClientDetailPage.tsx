import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import DashFrame from "../DashFrame";
import { ClientDto, Job, deleteClient, fetchClientJobs, updateClient } from "../api";
import { useToast } from "../toast";
import JobModal from "../components/JobModal";
import ConfirmDialog from "../components/ConfirmDialog";

export default function ClientDetailPage() {
  const toast = useToast();
  const nav = useNavigate();
  const { clientId } = useParams();
  const [sp, setSp] = useSearchParams();

  const [loading, setLoading] = useState(false);
  const [client, setClient] = useState<ClientDto | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [editMode, setEditMode] = useState(false);
  const [editDraft, setEditDraft] = useState<Partial<ClientDto>>({});
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const q = sp.get("q") ?? "";

  const reload = async () => {
    if (!clientId) return;
    const res = await fetchClientJobs(clientId);
    setClient(res.client);
    setJobs(res.jobs || []);
  };

  useEffect(() => {
    if (!clientId) return;
    let mounted = true;
    async function run() {
      setLoading(true);
      try {
        const res = await fetchClientJobs(clientId);
        if (!mounted) return;
        setClient(res.client);
        setJobs(res.jobs || []);
      } catch (e) {
        toast.error((e as Error).message || "Failed to load client");
      } finally {
        if (mounted) setLoading(false);
      }
    }
    void run();
    return () => {
      mounted = false;
    };
  }, [clientId, toast]);

  useEffect(() => {
    if (!editMode) return;
    setEditDraft({
      name: client?.name || "",
      company_name: client?.company_name || "",
      contact_person: client?.contact_person || "",
      email: client?.email || "",
      status: (client?.status as "active" | "inactive") || "active",
    });
  }, [editMode, client]);

  const filtered = useMemo(() => {
    const needle = (q || "").trim().toLowerCase();
    if (!needle) return jobs;
    return jobs.filter((j) => {
      const hay = `${j.external_id} ${j.title} ${j.department} ${j.status}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [jobs, q]);

  const doSave = async () => {
    if (!clientId) return;
    const name = (editDraft.name || "").trim();
    if (!name) {
      toast.error("Client name is required");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateClient(clientId, {
        name,
        company_name: (editDraft.company_name || "").trim(),
        contact_person: (editDraft.contact_person || "").trim(),
        email: (editDraft.email || "").trim(),
        status: (editDraft.status as "active" | "inactive") || "active",
      });
      toast.success("Client updated");
      setClient(updated);
      setEditMode(false);
      await reload();
    } catch (e) {
      toast.error((e as Error).message || "Failed to update client");
    } finally {
      setSaving(false);
    }
  };

  const doDelete = async () => {
    if (!clientId) return;
    setSaving(true);
    try {
      await deleteClient(clientId);
      toast.success("Client deleted");
      nav("/clients");
    } catch (e) {
      toast.error((e as Error).message || "Failed to delete client");
    } finally {
      setSaving(false);
      setDeleteOpen(false);
    }
  };

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Client: {client?.name || "—"}</div>
            <div className="cand-search">
              <input
                value={q}
                placeholder="Search jobs by title, department, id…"
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
            <Link
              to="/jobs/add"
              className="small-btn cand-primary-btn"
              title="Create job"
              aria-label="Create job"
              style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 5v14M5 12h14" strokeLinecap="round" />
              </svg>
              Create job
            </Link>
          </div>
          <div className="cand-toolbar-row">
            <Link to="/clients" className="cand-table-toolbar-action" style={{ textDecoration: "none" }}>
              ← Back
            </Link>
            <div className="cand-toolbar-actions">
              {editMode ? (
                <>
                  <button type="button" className="small-btn" disabled={saving} onClick={() => setEditMode(false)}>
                    Cancel
                  </button>
                  <button type="button" className="small-btn cand-primary-btn" disabled={saving} onClick={() => void doSave()}>
                    Save
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className="small-btn" disabled={!client || saving} onClick={() => setEditMode(true)}>
                    Edit client
                  </button>
                  <button
                    type="button"
                    className="small-btn cand-bulk-danger"
                    disabled={!client || saving}
                    onClick={() => setDeleteOpen(true)}
                  >
                    Delete client
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      }
    >
      <div className="job-overview-grid" style={{ marginBottom: 14 }}>
        <div className="job-card">
          <div className="job-card-title">Client info</div>
          {editMode ? (
            <div className="client-form" style={{ marginTop: 8 }}>
              <div className="job-kv-row">
                <div className="muted">Client name</div>
                <div>
                  <input value={editDraft.name || ""} onChange={(e) => setEditDraft((d) => ({ ...d, name: e.target.value }))} />
                </div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Company</div>
                <div>
                  <input
                    value={editDraft.company_name || ""}
                    onChange={(e) => setEditDraft((d) => ({ ...d, company_name: e.target.value }))}
                  />
                </div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Contact</div>
                <div>
                  <input
                    value={editDraft.contact_person || ""}
                    onChange={(e) => setEditDraft((d) => ({ ...d, contact_person: e.target.value }))}
                  />
                </div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Email</div>
                <div>
                  <input value={editDraft.email || ""} onChange={(e) => setEditDraft((d) => ({ ...d, email: e.target.value }))} />
                </div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Status</div>
                <div>
                  <select
                    value={(editDraft.status as string) || "active"}
                    onChange={(e) => setEditDraft((d) => ({ ...d, status: e.target.value as "active" | "inactive" }))}
                  >
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                  </select>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="job-kv-row">
                <div className="muted">Company</div>
                <div>{client?.company_name || <span className="muted">—</span>}</div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Contact</div>
                <div>{client?.contact_person || <span className="muted">—</span>}</div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Email</div>
                <div>{client?.email || <span className="muted">—</span>}</div>
              </div>
              <div className="job-kv-row">
                <div className="muted">Status</div>
                <div>
                  <span className={`job-pill job-status ${(client?.status || "active").toLowerCase()}`}>
                    {(client?.status || "active").toLowerCase() === "inactive" ? "Inactive" : "Active"}
                  </span>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="job-card">
          <div className="job-card-title">Jobs</div>
          <div className="job-kv-row">
            <div className="muted">Total</div>
            <div>{jobs.length}</div>
          </div>
          <div className="job-kv-row">
            <div className="muted">Active</div>
            <div>{jobs.filter((j) => (j.status || "").toLowerCase() === "active").length}</div>
          </div>
          <div className="job-kv-row">
            <div className="muted">On hold</div>
            <div>{jobs.filter((j) => ["on_hold", "inactive"].includes((j.status || "").toLowerCase())).length}</div>
          </div>
        </div>
      </div>

      <div className="jobs-table-wrap">
        <table className="jobs-table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Title</th>
              <th>Department</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="muted">
                  Loading…
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  No jobs found for this client.
                </td>
              </tr>
            ) : (
              filtered.map((j) => (
                <tr
                  key={j.external_id}
                  className="jobs-row"
                  onClick={() => {
                    setSp((prev) => {
                      const next = new URLSearchParams(prev);
                      next.set("job", j.external_id);
                      next.set("tab", "matching");
                      return next;
                    });
                  }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      setSp((prev) => {
                        const next = new URLSearchParams(prev);
                        next.set("job", j.external_id);
                        next.set("tab", "matching");
                        return next;
                      });
                    }
                  }}
                >
                  <td>{j.external_id}</td>
                  <td>{j.title || <span className="muted">—</span>}</td>
                  <td>{j.department || <span className="muted">—</span>}</td>
                  <td>
                    <span className={`job-pill job-status ${(j.status || "active").toLowerCase()}`}>
                      {(j.status || "active").replaceAll("_", " ")}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <JobModal
        open={Boolean(sp.get("job"))}
        externalId={sp.get("job") || ""}
        onClose={() => {
          setSp((prev) => {
            const next = new URLSearchParams(prev);
            next.delete("job");
            next.delete("tab");
            return next;
          });
        }}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Delete client?"
        message="This will delete the client. Jobs will remain but will be unassigned from the client."
        danger
        confirmLabel="Delete"
        busy={saving}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => void doDelete()}
      />
    </DashFrame>
  );
}

