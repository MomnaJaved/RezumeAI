import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  User,
  Briefcase,
  GraduationCap,
  Award,
  Star,
  TrendingUp,
  FileText,
  Mail,
  BarChart2,
  Trophy,
  Upload,
  CheckCircle2,
  Clock,
  ArrowRight,
  X,
  Plus,
} from "lucide-react";
import {
  fetchCandidate,
  fetchCandidateMe,
  fetchCandidateMatches,
  fetchCandidateFileBlob,
  normalizedBestJobMatchPercent,
  type CandidateMe,
  type CandidateDto,
  type CandidateMatchItem,
} from "../../api";
import CandidateResumeUploadModal, { CandidateResumeUploadTrigger } from "../../components/CandidateResumeUploadModal";

/* ── Status display ──────────────────────────────────────────────── */
const STATUS_MAP: Record<string, { label: string; color: string; bg: string; border: string }> = {
  new:         { label: "New",         color: "#93c5fd", bg: "rgba(59,130,246,0.15)",  border: "rgba(59,130,246,0.3)"  },
  screened:    { label: "Screened",    color: "#fcd34d", bg: "rgba(251,191,36,0.15)",  border: "rgba(251,191,36,0.3)"  },
  shortlisted: { label: "Shortlisted", color: "#a78bfa", bg: "rgba(139,92,246,0.15)",  border: "rgba(139,92,246,0.3)"  },
  interviewed: { label: "Interviewing",color: "#67e8f9", bg: "rgba(6,182,212,0.15)",   border: "rgba(6,182,212,0.3)"   },
  hired:       { label: "Hired",       color: "#86efac", bg: "rgba(34,197,94,0.15)",   border: "rgba(34,197,94,0.3)"   },
  selected:    { label: "Selected",    color: "#86efac", bg: "rgba(34,197,94,0.15)",   border: "rgba(34,197,94,0.3)"   },
  rejected:    { label: "Not selected",color: "#fca5a5", bg: "rgba(239,68,68,0.12)",   border: "rgba(239,68,68,0.25)"  },
};

function statusCfg(st?: string) {
  if (!st) return null;
  return STATUS_MAP[st.toLowerCase()] ?? { label: st, color: "rgba(255,255,255,0.7)", bg: "rgba(255,255,255,0.06)", border: "rgba(255,255,255,0.12)" };
}

function scoreColor(n: number) {
  return n >= 75 ? "#86efac" : n >= 50 ? "#fcd34d" : "#fca5a5";
}
function scoreBg(n: number) {
  return n >= 75 ? "rgba(34,197,94,0.15)" : n >= 50 ? "rgba(251,191,36,0.15)" : "rgba(239,68,68,0.12)";
}

/* ── Skill tag ───────────────────────────────────────────────────── */
function SkillTag({ label }: { label: string }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "0.25rem 0.65rem",
      borderRadius: 999,
      fontSize: "0.78rem", fontWeight: 600,
      background: "rgba(99,102,241,0.15)",
      border: "1px solid rgba(99,102,241,0.3)",
      color: "#a5b4fc",
      whiteSpace: "nowrap",
    }}>
      {label}
    </span>
  );
}

/* ── Section card ────────────────────────────────────────────────── */
function SectionCard({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div style={{
      padding: "1.1rem 1.25rem",
      borderRadius: 18,
      border: "1px solid rgba(255,255,255,0.1)",
      background: "rgba(2,6,23,0.22)",
      backdropFilter: "blur(10px)",
      display: "flex",
      flexDirection: "column",
      gap: "0.85rem",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
        <span style={{ color: "rgba(255,255,255,0.5)" }}>{icon}</span>
        <h2 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700, color: "rgba(255,255,255,0.9)" }}>
          {title}
        </h2>
      </div>
      {children}
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────────────── */
export default function CandidateProfilePage() {
  const [me, setMe]       = useState<CandidateMe | null>(null);
  const [dto, setDto]     = useState<CandidateDto | null>(null);
  const [matches, setMatches] = useState<CandidateMatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr]     = useState<string | null>(null);
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumePreview, setResumePreview] = useState<{ url: string; mime: string } | null>(null);
  const [resumePreviewErr, setResumePreviewErr] = useState<string | null>(null);
  const resumeBlobUrlRef = useRef<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const m = await fetchCandidateMe();
      setMe(m);
      if (!m.linked || !m.candidate_id) {
        setDto(null);
        setMatches([]);
        return;
      }
      const [d, mm] = await Promise.all([
        fetchCandidate(m.candidate_id),
        fetchCandidateMatches(m.candidate_id, 25),
      ]);
      setDto(d);
      setMatches(mm.items ?? []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load profile");
    } finally {
      setLoading(false);
    }
  }, []);

  const closeResumePreview = useCallback(() => {
    if (resumeBlobUrlRef.current) {
      URL.revokeObjectURL(resumeBlobUrlRef.current);
      resumeBlobUrlRef.current = null;
    }
    setResumePreview(null);
    setResumePreviewErr(null);
  }, []);

  useEffect(() => {
    if (!resumePreview && !resumePreviewErr) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeResumePreview();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [resumePreview, resumePreviewErr, closeResumePreview]);

  useEffect(() => {
    return () => {
      if (resumeBlobUrlRef.current) {
        URL.revokeObjectURL(resumeBlobUrlRef.current);
        resumeBlobUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  /* ── Error ── */
  if (err) {
    return (
      <div>
        <h1 className="dash-title" style={{ textAlign: "left" }}>Profile</h1>
        <p className="dash-inbox-banner dash-inbox-banner-error">{err}</p>
      </div>
    );
  }

  /* ── Not linked ── */
  if (!loading && me && !me.linked) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
          <h1 className="dash-title" style={{ textAlign: "left", marginBottom: 0 }}>Profile</h1>
          <CandidateResumeUploadTrigger onClick={() => setUploadOpen(true)} title="Upload resume" />
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: "0.75rem",
          padding: "1rem 1.25rem", borderRadius: 16,
          background: "rgba(251,191,36,0.1)", border: "1px solid rgba(251,191,36,0.3)",
        }}>
          <Upload size={20} color="#fcd34d" style={{ flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 650, fontSize: "0.92rem", marginBottom: "0.2rem" }}>No profile yet</div>
            <div style={{ fontSize: "0.84rem", color: "rgba(255,255,255,0.6)" }}>
              Upload a resume to create your profile.
            </div>
          </div>
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            style={{
              marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: "0.35rem",
              padding: "0.45rem 0.9rem", borderRadius: 10,
              background: "rgba(251,191,36,0.15)", border: "1px solid rgba(251,191,36,0.35)",
              color: "#fcd34d", fontWeight: 650, fontSize: "0.84rem",
              whiteSpace: "nowrap", cursor: "pointer",
            }}
          >
            <Plus size={16} strokeWidth={2.25} /> Add resume
          </button>
        </div>
        <CandidateResumeUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={() => void reload()} />
      </div>
    );
  }

  /* ── Loading skeleton ── */
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <h1 className="dash-title" style={{ textAlign: "left", marginBottom: 0 }}>Profile</h1>
        <p style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.9rem" }}>Loading your profile…</p>
      </div>
    );
  }

  /* ── Data helpers ── */
  const name     = dto?.full_name || me?.full_name || "—";
  const title    = dto?.title || me?.title || "";
  const roleLabel = dto?.role_label || "";
  const email    = dto?.contact_email || me?.email || "";
  const extId    = dto?.external_id || me?.external_id || "";
  const hasFile  = !!dto?.filename;

  async function viewResume() {
    if (!extId) return;
    closeResumePreview();
    setResumeBusy(true);
    setResumePreviewErr(null);
    try {
      const { blob, contentType } = await fetchCandidateFileBlob(extId);
      let mime = (contentType || blob.type || "application/octet-stream").split(";")[0].trim().toLowerCase();
      const fn = (dto?.filename || "").toLowerCase();
      if ((mime === "application/octet-stream" || !mime) && fn.endsWith(".pdf")) mime = "application/pdf";
      const url = URL.createObjectURL(new Blob([blob], { type: mime || "application/octet-stream" }));
      resumeBlobUrlRef.current = url;
      setResumePreview({ url, mime });
    } catch {
      setResumePreview(null);
      setResumePreviewErr("Could not load this file. Try uploading again from the home screen (+) or here.");
    } finally {
      setResumeBusy(false);
    }
  }

  function resumePreviewKind(mime: string, filename: string): "pdf" | "image" | "other" {
    const m = mime.toLowerCase();
    const f = filename.toLowerCase();
    if (m.includes("pdf") || f.endsWith(".pdf")) return "pdf";
    if (m.startsWith("image/")) return "image";
    return "other";
  }

  const rawStatus = dto?.status_effective || dto?.status || me?.status;
  const stCfg    = statusCfg(rawStatus);

  const yearsExp  = dto?.years_experience;
  const skills    = dto?.skills ? dto.skills.split(",").map(s => s.trim()).filter(Boolean) : [];
  const eduLines  = dto?.education_lines?.split("\n").filter(Boolean) ?? [];
  const degree    = dto?.highest_degree || "";
  const certs     = dto?.certifications?.split(",").map(s => s.trim()).filter(Boolean) ?? [];

  const bestScore = normalizedBestJobMatchPercent(dto?.best_job_match_score ?? me?.best_job_match_score);
  const bestJobTitle = dto?.best_job_title || (me?.best_job_external_id ? `Job ${me.best_job_external_id}` : null);

  const initials = name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}>

      {/* ── Page title ── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 className="dash-title" style={{ textAlign: "left", marginBottom: "0.2rem" }}>Your profile</h1>
          <p style={{ margin: 0, color: "rgba(255,255,255,0.5)", fontSize: "0.88rem" }}>
            This is the profile recruiters see when ranking candidates.
          </p>
        </div>
        <CandidateResumeUploadTrigger onClick={() => setUploadOpen(true)} title="Upload or replace resume" />
      </div>

      <CandidateResumeUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={() => void reload()} />

      {/* ── Profile header card ── */}
      <div style={{
        padding: "1.25rem 1.5rem",
        borderRadius: 20,
        border: "1px solid rgba(255,255,255,0.12)",
        background: "rgba(2,6,23,0.28)",
        backdropFilter: "blur(12px)",
        display: "flex",
        alignItems: "flex-start",
        gap: "1.25rem",
        flexWrap: "wrap",
      }}>
        {/* Avatar */}
        <div style={{
          width: 64, height: 64, borderRadius: 18, flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(99,102,241,0.2)", border: "2px solid rgba(99,102,241,0.4)",
          fontSize: "1.35rem", fontWeight: 800, color: "#a5b4fc",
        }}>
          {initials || <User size={28} />}
        </div>

        {/* Info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem", flexWrap: "wrap" }}>
            <h2 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 700 }}>{name}</h2>
            {stCfg && (
              <span style={{
                padding: "0.2rem 0.65rem", borderRadius: 999,
                fontSize: "0.76rem", fontWeight: 700,
                color: stCfg.color, background: stCfg.bg, border: `1px solid ${stCfg.border}`,
              }}>
                {stCfg.label}
              </span>
            )}
          </div>
          {title && (
            <div style={{ color: "rgba(255,255,255,0.65)", fontSize: "0.92rem", marginTop: "0.25rem" }}>
              {title}{roleLabel && roleLabel !== title ? ` · ${roleLabel}` : ""}
            </div>
          )}
          <div style={{ display: "flex", gap: "1.25rem", marginTop: "0.55rem", flexWrap: "wrap" }}>
            {email && (
              <span style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", color: "rgba(255,255,255,0.5)" }}>
                <Mail size={13} /> {email}
              </span>
            )}
            {hasFile && (
              <button
                onClick={() => void viewResume()}
                disabled={resumeBusy}
                style={{
                  display: "flex", alignItems: "center", gap: "0.35rem",
                  fontSize: "0.8rem", color: "rgba(255,255,255,0.5)",
                  background: "none", border: "none", padding: 0,
                  cursor: resumeBusy ? "wait" : "pointer",
                  textDecoration: "underline", textUnderlineOffset: "3px",
                  textDecorationColor: "rgba(255,255,255,0.25)",
                }}
              >
                <FileText size={13} />
                {resumeBusy ? "Opening…" : "View resume"}
              </button>
            )}
          </div>
        </div>

        {/* Best score */}
        {bestScore != null && (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            padding: "0.75rem 1.1rem", borderRadius: 14,
            background: scoreBg(bestScore), border: `1px solid ${scoreColor(bestScore)}40`,
          }}>
            <Trophy size={18} color={scoreColor(bestScore)} style={{ marginBottom: "0.3rem" }} />
            <div style={{ fontSize: "1.5rem", fontWeight: 800, color: scoreColor(bestScore), lineHeight: 1 }}>
              {bestScore}%
            </div>
            <div style={{ fontSize: "0.72rem", color: "rgba(255,255,255,0.5)", marginTop: "0.25rem", textAlign: "center" }}>
              Best match
              {bestJobTitle && <><br /><span style={{ color: "rgba(255,255,255,0.35)", fontSize: "0.7rem" }}>{bestJobTitle}</span></>}
            </div>
          </div>
        )}
      </div>

      {/* ── Main 2-col grid ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.9rem" }}>

        {/* Experience */}
        <SectionCard icon={<Briefcase size={16} />} title="Experience">
          {yearsExp != null ? (
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <div style={{
                width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                background: "rgba(56,189,248,0.15)", border: "1px solid rgba(56,189,248,0.25)",
                fontSize: "1.2rem", fontWeight: 800, color: "#38bdf8",
              }}>
                {yearsExp}
              </div>
              <div>
                <div style={{ fontWeight: 650, fontSize: "0.92rem" }}>
                  {yearsExp === 0 ? "Fresher / Entry level" : `${yearsExp} year${yearsExp !== 1 ? "s" : ""} of experience`}
                </div>
                {title && <div style={{ fontSize: "0.8rem", color: "rgba(255,255,255,0.5)", marginTop: "0.15rem" }}>{title}</div>}
              </div>
            </div>
          ) : (
            <p style={{ margin: 0, color: "rgba(255,255,255,0.4)", fontSize: "0.85rem" }}>Not extracted from resume.</p>
          )}
        </SectionCard>

        {/* Education */}
        <SectionCard icon={<GraduationCap size={16} />} title="Education">
          {eduLines.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
              {eduLines.map((line, i) => (
                <div key={i} style={{ fontSize: "0.86rem", color: i === 0 ? "rgba(255,255,255,0.88)" : "rgba(255,255,255,0.6)", lineHeight: 1.45 }}>
                  {line}
                </div>
              ))}
            </div>
          ) : degree ? (
            <div style={{ fontSize: "0.88rem", color: "rgba(255,255,255,0.85)" }}>{degree}</div>
          ) : (
            <p style={{ margin: 0, color: "rgba(255,255,255,0.4)", fontSize: "0.85rem" }}>Not extracted from resume.</p>
          )}
        </SectionCard>

        {/* Skills — full width */}
        <div style={{ gridColumn: "1 / -1" }}>
          <SectionCard icon={<Star size={16} />} title={`Skills${skills.length ? ` · ${skills.length}` : ""}`}>
            {skills.length > 0 ? (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {skills.map((s, i) => <SkillTag key={i} label={s} />)}
              </div>
            ) : (
              <p style={{ margin: 0, color: "rgba(255,255,255,0.4)", fontSize: "0.85rem" }}>
                No skills extracted yet. Upload or re-upload your resume to extract skills.
              </p>
            )}
          </SectionCard>
        </div>

        {/* Certifications */}
        {certs.length > 0 && (
          <div style={{ gridColumn: "1 / -1" }}>
            <SectionCard icon={<Award size={16} />} title="Certifications">
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {certs.map((c, i) => (
                  <span key={i} style={{
                    display: "inline-flex", alignItems: "center",
                    padding: "0.25rem 0.65rem", borderRadius: 999,
                    fontSize: "0.78rem", fontWeight: 600,
                    background: "rgba(251,191,36,0.12)", border: "1px solid rgba(251,191,36,0.28)",
                    color: "#fcd34d",
                  }}>
                    {c}
                  </span>
                ))}
              </div>
            </SectionCard>
          </div>
        )}

        {/* Match scores — full width */}
        <div style={{ gridColumn: "1 / -1" }}>
          <SectionCard icon={<BarChart2 size={16} />} title="Job match scores">
            {matches.length === 0 ? (
              <div style={{ textAlign: "center", padding: "1rem 0" }}>
                <TrendingUp size={28} color="rgba(255,255,255,0.15)" style={{ marginBottom: "0.5rem" }} />
                <p style={{ margin: 0, color: "rgba(255,255,255,0.4)", fontSize: "0.85rem" }}>
                  No match scores yet. Apply to jobs so recruiters can rank you.
                </p>
                <Link to="/candidate/jobs" style={{
                  display: "inline-flex", alignItems: "center", gap: "0.3rem",
                  marginTop: "0.6rem", fontSize: "0.82rem", color: "#38bdf8", textDecoration: "none",
                }}>
                  Browse jobs <ArrowRight size={13} />
                </Link>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
                {matches.map((m) => {
                  const pct = m.match_score > 1 ? Math.round(m.match_score) : Math.round(m.match_score * 100);
                  return (
                    <div key={m.job_external_id} style={{
                      display: "flex", alignItems: "center", gap: "0.75rem",
                      padding: "0.6rem 0.85rem", borderRadius: 12,
                      background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
                    }}>
                      {/* Score bar + number */}
                      <div style={{ position: "relative", width: 44, height: 44, flexShrink: 0 }}>
                        <svg width="44" height="44" viewBox="0 0 44 44">
                          <circle cx="22" cy="22" r="18" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="4" />
                          <circle
                            cx="22" cy="22" r="18" fill="none"
                            stroke={scoreColor(pct)} strokeWidth="4"
                            strokeDasharray={`${2 * Math.PI * 18 * pct / 100} ${2 * Math.PI * 18}`}
                            strokeLinecap="round"
                            transform="rotate(-90 22 22)"
                          />
                        </svg>
                        <span style={{
                          position: "absolute", inset: 0,
                          display: "flex", alignItems: "center", justifyContent: "center",
                          fontSize: "0.68rem", fontWeight: 800, color: scoreColor(pct),
                        }}>
                          {pct}%
                        </span>
                      </div>

                      {/* Job info */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 650, fontSize: "0.88rem", color: "rgba(255,255,255,0.9)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {m.job_title}
                        </div>
                        <div style={{ fontSize: "0.76rem", color: "rgba(255,255,255,0.4)", marginTop: "0.1rem" }}>
                          {m.job_external_id}
                          {m.run_at ? ` · ${new Date(m.run_at).toLocaleDateString()}` : ""}
                        </div>
                      </div>

                      {/* Rank */}
                      {m.rank_position > 0 && (
                        <span style={{
                          padding: "0.2rem 0.55rem", borderRadius: 8, flexShrink: 0,
                          fontSize: "0.76rem", fontWeight: 700,
                          background: "rgba(167,139,250,0.15)", border: "1px solid rgba(167,139,250,0.3)",
                          color: "#c4b5fd",
                        }}>
                          #{m.rank_position}
                        </span>
                      )}

                      {/* Job status */}
                      <span style={{ flexShrink: 0 }}>
                        {m.job_status === "active"
                          ? <CheckCircle2 size={15} color="#86efac" />
                          : <Clock size={15} color="rgba(255,255,255,0.3)" />
                        }
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </SectionCard>
        </div>

      </div>

      {(resumePreview || resumePreviewErr) ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="resume-preview-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeResumePreview();
          }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 5000,
            background: "rgba(0,0,0,0.72)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "1rem",
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(920px, 96vw)",
              maxHeight: "min(88vh, 900px)",
              display: "flex",
              flexDirection: "column",
              borderRadius: 16,
              border: "1px solid rgba(255,255,255,0.14)",
              background: "rgba(15,23,42,0.98)",
              boxShadow: "0 24px 80px rgba(0,0,0,0.55)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                flexShrink: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.75rem",
                padding: "0.65rem 1rem",
                borderBottom: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <div id="resume-preview-title" style={{ fontWeight: 700, fontSize: "0.95rem", color: "#fff", minWidth: 0 }}>
                {dto?.filename || "Resume"}
              </div>
              <button
                type="button"
                onClick={closeResumePreview}
                aria-label="Close"
                style={{
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  border: "1px solid rgba(255,255,255,0.12)",
                  background: "rgba(255,255,255,0.06)",
                  color: "#fff",
                  cursor: "pointer",
                }}
              >
                <X size={18} />
              </button>
            </div>
            <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", position: "relative" }}>
              {resumePreviewErr && !resumePreview ? (
                <p style={{ margin: 0, padding: "1.5rem", color: "rgba(255,255,255,0.75)", fontSize: "0.9rem" }}>
                  {resumePreviewErr}
                </p>
              ) : resumePreview ? (
                (() => {
                  const kind = resumePreviewKind(resumePreview.mime, dto?.filename || "");
                  if (kind === "pdf") {
                    return (
                      <iframe
                        title="Resume preview"
                        src={resumePreview.url}
                        style={{ width: "100%", flex: 1, minHeight: "min(72vh, 720px)", border: "none", background: "#111" }}
                      />
                    );
                  }
                  if (kind === "image") {
                    return (
                      <div style={{ padding: "1rem", display: "flex", justifyContent: "center", alignItems: "center", flex: 1, overflow: "auto" }}>
                        <img src={resumePreview.url} alt="Resume" style={{ maxWidth: "100%", maxHeight: "72vh", objectFit: "contain" }} />
                      </div>
                    );
                  }
                  return (
                    <div style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1rem", alignItems: "flex-start" }}>
                      <p style={{ margin: 0, color: "rgba(255,255,255,0.7)", fontSize: "0.88rem" }}>
                        Inline preview is not available for this file type. Download to open it.
                      </p>
                      <a
                        href={resumePreview.url}
                        download={dto?.filename || "resume"}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          padding: "0.5rem 1rem",
                          borderRadius: 10,
                          background: "rgba(56,189,248,0.2)",
                          border: "1px solid rgba(56,189,248,0.4)",
                          color: "#7dd3fc",
                          fontWeight: 650,
                          textDecoration: "none",
                        }}
                      >
                        Download file
                      </a>
                    </div>
                  );
                })()
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

    </div>
  );
}
