import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import DashFrame from "../DashFrame";
import { createJob, fetchClients, type ClientDto } from "../api";
import { useToast } from "../toast";

export default function AddJobPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [clients, setClients] = useState<ClientDto[]>([]);
  const [clientId, setClientId] = useState<string>("all");
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState<"active" | "on_hold" | "completed" | "cancelled">("active");
  const [salaryRange, setSalaryRange] = useState("");
  const [workLocation, setWorkLocation] = useState<"" | "on_site" | "remote">("");
  const [jobType, setJobType] = useState<"" | "full_time" | "part_time">("");
  const [urgency, setUrgency] = useState<"" | "high" | "medium" | "low">("");
  const [onboardDate, setOnboardDate] = useState<string>("");
  const [minExp, setMinExp] = useState<string>("");
  const [education, setEducation] = useState("");
  const [skills, setSkills] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    fetchClients({ status: "active" })
      .then(setClients)
      .catch(() => setClients([]));
  }, []);

  const canSubmit = useMemo(() => title.trim().length > 0, [title]);

  const submit = useCallback(async () => {
    setBusy(true);
    try {
      const min = minExp.trim() === "" ? null : Number(minExp);
      if (minExp.trim() !== "" && !Number.isFinite(min)) throw new Error("Min experience must be a number.");
      const job = await createJob({
        client_id: clientId !== "all" ? clientId : null,
        title: title.trim(),
        department: department.trim(),
        status,
        salary_range: salaryRange.trim(),
        work_location: workLocation || "",
        job_type: jobType || "",
        recruitment_urgency: urgency || "",
        preferred_onboarding_date: onboardDate ? new Date(onboardDate).toISOString() : null,
        min_experience: min,
        education_required: education.trim() || "any",
        skills: skills.trim(),
        description: description.trim(),
      });
      toast.success("Job created.");
      nav(`/jobs?job=${encodeURIComponent(job.external_id)}`, { replace: true });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [
    title,
    department,
    status,
    salaryRange,
    workLocation,
    jobType,
    urgency,
    onboardDate,
    minExp,
    education,
    skills,
    description,
    toast,
    nav,
    clientId,
  ]);

  return (
    <DashFrame
      topExtra={
        <div className="jobs-toolbar">
          <div className="jobs-toolbar-row">
            <div className="jobs-count">Add job</div>
            <div className="jobs-search" />
            <Link to="/jobs" className="muted" style={{ marginLeft: "auto" }}>
              ← Back to jobs
            </Link>
          </div>
        </div>
      }
    >
      <div className="dash-panel">
        <div className="job-form-grid">
          <div className="job-form-wide">
            <label>Job title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Frontend Developer" autoFocus />
          </div>
          <div>
            <label>Client</label>
            <select value={clientId} onChange={(e) => setClientId(e.target.value)}>
              <option value="all">Select client</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value as any)}>
              <option value="active">Active</option>
              <option value="on_hold">On hold</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
          <div>
            <label>Department</label>
            <input value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="Engineering" />
          </div>
          <div>
            <label>Min experience (years)</label>
            <input value={minExp} onChange={(e) => setMinExp(e.target.value)} placeholder="2" />
          </div>
          <div>
            <label>Education required</label>
            <input
              value={education}
              onChange={(e) => setEducation(e.target.value)}
              placeholder="Bachelor's degree or equivalent"
            />
          </div>
          <div>
            <label>Salary range</label>
            <input value={salaryRange} onChange={(e) => setSalaryRange(e.target.value)} placeholder="50,000 – 70,000" />
          </div>
          <div>
            <label>Location</label>
            <select value={workLocation} onChange={(e) => setWorkLocation(e.target.value as any)}>
              <option value="">Select location</option>
              <option value="on_site">On-site</option>
              <option value="remote">Remote</option>
            </select>
          </div>
          <div>
            <label>Job type</label>
            <select value={jobType} onChange={(e) => setJobType(e.target.value as any)}>
              <option value="">Select job type</option>
              <option value="full_time">Full-time</option>
              <option value="part_time">Part-time</option>
            </select>
          </div>
          <div>
            <label>Recruitment urgency</label>
            <select value={urgency} onChange={(e) => setUrgency(e.target.value as any)}>
              <option value="">Select urgency</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
          <div>
            <label>Preferred onboarding date</label>
            <input type="date" value={onboardDate} onChange={(e) => setOnboardDate(e.target.value)} />
          </div>
          <div className="job-form-wide">
            <label>Skills</label>
            <input value={skills} onChange={(e) => setSkills(e.target.value)} placeholder="React, TypeScript, REST APIs" />
          </div>
          <div className="job-form-wide">
            <label>Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={10}
              placeholder="We are looking for a Frontend Developer to build responsive web applications. Responsibilities include…"
            />
          </div>
        </div>

        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end", marginTop: "0.9rem" }}>
          <Link to="/jobs" className="clients-float-btn clients-float-btn--ghost" style={{ textDecoration: "none" }}>
            Cancel
          </Link>
          <button type="button" className="clients-float-btn clients-float-btn--primary" disabled={!canSubmit || busy} onClick={() => void submit()}>
            {busy ? "Creating…" : "Create job"}
          </button>
        </div>
      </div>
    </DashFrame>
  );
}

