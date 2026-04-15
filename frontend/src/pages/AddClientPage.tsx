import { useState } from "react";
import { useNavigate } from "react-router-dom";
import DashFrame from "../DashFrame";
import { createClient } from "../api";
import { useToast } from "../toast";

export default function AddClientPage() {
  const toast = useToast();
  const nav = useNavigate();

  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"active" | "inactive">("active");

  async function submit() {
    if (!name.trim()) {
      toast.error("Client name is required");
      return;
    }
    setSaving(true);
    try {
      const c = await createClient({
        name: name.trim(),
        company_name: companyName.trim(),
        contact_person: contactPerson.trim(),
        email: email.trim(),
        status,
      });
      toast.success("Client created");
      nav(`/clients/${encodeURIComponent(c.id)}`);
    } catch (e) {
      toast.error((e as Error).message || "Failed to create client");
    } finally {
      setSaving(false);
    }
  }

  return (
    <DashFrame
      topExtra={
        <div className="cand-toolbar">
          <div className="cand-toolbar-row">
            <div className="cand-count">Add Client</div>
            <div className="cand-toolbar-actions">
              <button type="button" className="small-btn" onClick={() => nav("/clients")} disabled={saving}>
                ← Back
              </button>
              <button
                type="button"
                className="small-btn cand-primary-btn"
                onClick={() => void submit()}
                disabled={saving}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      }
    >
      <div className="job-card job-card-wide client-form">
        <div className="job-card-title">Client details</div>
        <div className="job-overview-grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <label>Client name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Titan Scrubs" />
          </div>
          <div>
            <label>Company name</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Titan Scrubs Inc." />
          </div>
          <div>
            <label>Contact person</label>
            <input value={contactPerson} onChange={(e) => setContactPerson(e.target.value)} placeholder="Ayesha Anwar" />
          </div>
          <div>
            <label>Email</label>
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="hiring@titanscrubs.com" />
          </div>
          <div>
            <label>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as "active" | "inactive")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>
      </div>
    </DashFrame>
  );
}

