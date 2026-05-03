import { Link } from "react-router-dom";
import { useCallback, useEffect, useState } from "react";
import {
  Briefcase,
  User,
  ClipboardList,
  Star,
  TrendingUp,
  CheckCircle2,
  Clock,
  AlertCircle,
  ArrowRight,
  Plus,
} from "lucide-react";
import { fetchCandidateMe, fetchCandidateApplications, type CandidateMe, type CandidateApplicationRow } from "../../api";
import CandidateResumeUploadModal, { CandidateResumeUploadTrigger } from "../../components/CandidateResumeUploadModal";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; border: string }> = {
  new:          { label: "Applied",       color: "#93c5fd", bg: "rgba(59,130,246,0.15)",  border: "rgba(59,130,246,0.3)"  },
  screened:     { label: "Screened",      color: "#fcd34d", bg: "rgba(251,191,36,0.15)",  border: "rgba(251,191,36,0.3)"  },
  shortlisted:  { label: "Shortlisted",   color: "#a78bfa", bg: "rgba(139,92,246,0.15)",  border: "rgba(139,92,246,0.3)"  },
  interviewed:  { label: "Interviewing",  color: "#67e8f9", bg: "rgba(6,182,212,0.15)",   border: "rgba(6,182,212,0.3)"   },
  hired:        { label: "Hired",         color: "#86efac", bg: "rgba(34,197,94,0.15)",   border: "rgba(34,197,94,0.3)"   },
  selected:     { label: "Selected",      color: "#86efac", bg: "rgba(34,197,94,0.15)",   border: "rgba(34,197,94,0.3)"   },
  rejected:     { label: "Not selected",  color: "#fca5a5", bg: "rgba(239,68,68,0.12)",   border: "rgba(239,68,68,0.25)"  },
};

function statusCfg(st: string) {
  return STATUS_CONFIG[st.toLowerCase()] ?? { label: st, color: "rgba(255,255,255,0.7)", bg: "rgba(255,255,255,0.06)", border: "rgba(255,255,255,0.12)" };
}

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 75 ? "#86efac" : score >= 50 ? "#fcd34d" : "#fca5a5";
  const bg    = score >= 75 ? "rgba(34,197,94,0.15)" : score >= 50 ? "rgba(251,191,36,0.15)" : "rgba(239,68,68,0.12)";
  return (
    <span style={{
      background: bg,
      border: `1px solid ${color}40`,
      borderRadius: 8,
      padding: "0.2rem 0.6rem",
      fontSize: "0.78rem",
      fontWeight: 700,
      color,
      whiteSpace: "nowrap",
    }}>
      {score.toFixed(1)}%
    </span>
  );
}

export default function CandidateDashboardPage() {
  const [me, setMe] = useState<CandidateMe | null>(null);
  const [apps, setApps] = useState<CandidateApplicationRow[]>([]);
  const [loadingMe, setLoadingMe] = useState(true);
  const [loadingApps, setLoadingApps] = useState(true);
  const [uploadOpen, setUploadOpen] = useState(false);

  const refreshData = useCallback(async () => {
    setLoadingMe(true);
    setLoadingApps(true);
    try {
      const [m, a] = await Promise.all([fetchCandidateMe(), fetchCandidateApplications()]);
      setMe(m);
      setApps(a.items);
    } catch {
      /* ignore */
    } finally {
      setLoadingMe(false);
      setLoadingApps(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [m, a] = await Promise.all([fetchCandidateMe(), fetchCandidateApplications()]);
        if (!cancelled) { setMe(m); setApps(a.items); }
      } catch {
        // silent — cards will show empty state
      } finally {
        if (!cancelled) { setLoadingMe(false); setLoadingApps(false); }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const firstName = me?.full_name?.split(" ")[0] || "there";
  const totalApps = apps.length;
  const activeApps = apps.filter(a => !["rejected"].includes(a.status.toLowerCase())).length;
  const bestScore = me?.best_job_match_score != null ? Math.round(me.best_job_match_score) : null;
  const recentApps = apps.slice(0, 4);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>

      {/* ── Header ── */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 className="dash-title" style={{ textAlign: "left", marginBottom: "0.25rem" }}>
            {loadingMe ? "Welcome back" : `Welcome back, ${firstName}`}
          </h1>
          <p style={{ margin: 0, color: "rgba(255,255,255,0.55)", fontSize: "0.92rem" }}>
            Here's an overview of your job search activity.
          </p>
        </div>
        <CandidateResumeUploadTrigger onClick={() => setUploadOpen(true)} disabled={loadingMe} />
      </div>

      <CandidateResumeUploadModal open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={() => void refreshData()} />

      {/* ── Profile alert ── */}
      {!loadingMe && me && !me.linked && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
          padding: "0.85rem 1rem",
          borderRadius: 14,
          background: "rgba(251,191,36,0.1)",
          border: "1px solid rgba(251,191,36,0.3)",
        }}>
          <AlertCircle size={18} color="#fcd34d" style={{ flexShrink: 0 }} />
          <span style={{ fontSize: "0.88rem", color: "rgba(255,255,255,0.85)", flex: 1 }}>
            Your profile isn't active yet. Upload a resume so recruiters can find you.
          </span>
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            style={{
              display: "inline-flex", alignItems: "center", gap: "0.35rem",
              fontSize: "0.82rem", fontWeight: 650, color: "#fcd34d",
              background: "none", border: "none", cursor: "pointer", whiteSpace: "nowrap",
            }}
          >
            <Plus size={16} strokeWidth={2.25} /> Add resume
          </button>
        </div>
      )}

      {/* ── Stat tiles ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "0.75rem" }}>
        <StatTile
          icon={<ClipboardList size={22} />}
          iconBg="rgba(99,102,241,0.18)"
          iconBorder="rgba(99,102,241,0.35)"
          label="Total applications"
          value={loadingApps ? "…" : String(totalApps)}
        />
        <StatTile
          icon={<TrendingUp size={22} />}
          iconBg="rgba(34,197,94,0.15)"
          iconBorder="rgba(34,197,94,0.3)"
          label="Active applications"
          value={loadingApps ? "…" : String(activeApps)}
          valueColor="#86efac"
        />
        <StatTile
          icon={<Star size={22} />}
          iconBg="rgba(251,191,36,0.15)"
          iconBorder="rgba(251,191,36,0.3)"
          label="Best match score"
          value={loadingMe ? "…" : bestScore != null ? `${bestScore}%` : "—"}
          valueColor={bestScore != null ? (bestScore >= 75 ? "#86efac" : bestScore >= 50 ? "#fcd34d" : "#fca5a5") : undefined}
        />
        <StatTile
          icon={<CheckCircle2 size={22} />}
          iconBg={me?.linked ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.12)"}
          iconBorder={me?.linked ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.25)"}
          label="Profile status"
          value={loadingMe ? "…" : me?.linked ? "Active" : "Incomplete"}
          valueColor={me?.linked ? "#86efac" : "#fca5a5"}
        />
      </div>

      {/* ── Quick actions + recent applications ── */}
      <div className="dash-lower" style={{ alignItems: "start" }}>

        {/* Quick actions */}
        <div className="dash-panel">
          <h2 style={{ margin: "0 0 1rem", fontSize: "1rem", fontWeight: 700, color: "rgba(255,255,255,0.9)" }}>
            Quick actions
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            <ActionCard
              to="/candidate/jobs"
              icon={<Briefcase size={18} />}
              iconBg="rgba(56,189,248,0.15)"
              iconColor="#38bdf8"
              title="Browse jobs"
              desc="Explore open listings and apply"
            />
            <ActionCard
              to="/candidate/applications"
              icon={<ClipboardList size={18} />}
              iconBg="rgba(99,102,241,0.18)"
              iconColor="#a5b4fc"
              title="My applications"
              desc="Track your application status"
            />
            <ActionCard
              onClick={() => setUploadOpen(true)}
              icon={<Plus size={18} strokeWidth={2.5} />}
              iconBg="rgba(56,189,248,0.15)"
              iconColor="#38bdf8"
              title="Resume"
              desc="Upload or replace your CV"
            />
            <ActionCard
              to="/candidate/profile"
              icon={<User size={18} />}
              iconBg="rgba(167,139,250,0.18)"
              iconColor="#c4b5fd"
              title="Profile & match scores"
              desc="See how you rank for each job"
            />
          </div>
        </div>

        {/* Recent applications */}
        <div className="dash-panel">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <h2 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: "rgba(255,255,255,0.9)" }}>
              Recent applications
            </h2>
            {totalApps > 0 && (
              <Link to="/candidate/applications" style={{
                fontSize: "0.78rem", color: "#38bdf8", textDecoration: "none",
                display: "flex", alignItems: "center", gap: "0.25rem",
              }}>
                View all <ArrowRight size={13} />
              </Link>
            )}
          </div>

          {loadingApps ? (
            <div style={{ color: "rgba(255,255,255,0.4)", fontSize: "0.88rem" }}>Loading…</div>
          ) : recentApps.length === 0 ? (
            <div style={{ textAlign: "center", padding: "1.5rem 0" }}>
              <Clock size={28} color="rgba(255,255,255,0.2)" style={{ marginBottom: "0.5rem" }} />
              <p style={{ margin: 0, color: "rgba(255,255,255,0.4)", fontSize: "0.88rem" }}>
                No applications yet.
              </p>
              <Link to="/candidate/jobs" style={{
                display: "inline-flex", alignItems: "center", gap: "0.3rem",
                marginTop: "0.65rem", fontSize: "0.82rem", color: "#38bdf8", textDecoration: "none",
              }}>
                Browse jobs <ArrowRight size={13} />
              </Link>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {recentApps.map((row) => {
                const cfg = statusCfg(row.status);
                return (
                  <div key={`${row.job_external_id}-${row.updated_at}`} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    padding: "0.65rem 0.8rem",
                    borderRadius: 12,
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontWeight: 600,
                        fontSize: "0.88rem",
                        color: "rgba(255,255,255,0.9)",
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                      }}>
                        {row.job_title}
                      </div>
                      {row.company && (
                        <div style={{ fontSize: "0.76rem", color: "rgba(255,255,255,0.45)", marginTop: "0.1rem" }}>
                          {row.company}
                        </div>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexShrink: 0 }}>
                      {row.match_score != null && <ScoreBadge score={row.match_score} />}
                      <span style={{
                        fontSize: "0.75rem", fontWeight: 600,
                        color: cfg.color, background: cfg.bg,
                        border: `1px solid ${cfg.border}`,
                        borderRadius: 8, padding: "0.18rem 0.55rem",
                        whiteSpace: "nowrap",
                      }}>
                        {cfg.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function StatTile({
  icon, iconBg, iconBorder, label, value, valueColor,
}: {
  icon: React.ReactNode;
  iconBg: string;
  iconBorder: string;
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div style={{
      padding: "1rem 1.1rem",
      borderRadius: 16,
      border: "1px solid rgba(255,255,255,0.1)",
      background: "rgba(2,6,23,0.22)",
      backdropFilter: "blur(10px)",
      display: "flex",
      flexDirection: "column",
      gap: "0.6rem",
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 12,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: iconBg, border: `1px solid ${iconBorder}`,
        color: "rgba(255,255,255,0.9)",
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: valueColor ?? "#fff", lineHeight: 1.1 }}>
          {value}
        </div>
        <div style={{ fontSize: "0.78rem", color: "rgba(255,255,255,0.5)", marginTop: "0.2rem" }}>
          {label}
        </div>
      </div>
    </div>
  );
}

function ActionCard({
  to,
  onClick,
  icon,
  iconBg,
  iconColor,
  title,
  desc,
}: {
  to?: string;
  onClick?: () => void;
  icon: React.ReactNode;
  iconBg: string;
  iconColor: string;
  title: string;
  desc: string;
}) {
  const inner = (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "0.75rem",
      padding: "0.65rem 0.8rem",
      borderRadius: 12,
      border: "1px solid rgba(255,255,255,0.08)",
      background: "rgba(255,255,255,0.03)",
      cursor: "pointer",
      transition: "background 0.15s, border-color 0.15s",
      width: "100%",
      textAlign: "left" as const,
    }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.07)";
        (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.14)";
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLDivElement).style.background = "rgba(255,255,255,0.03)";
        (e.currentTarget as HTMLDivElement).style.borderColor = "rgba(255,255,255,0.08)";
      }}
    >
      <div style={{
        width: 36, height: 36, borderRadius: 10, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: iconBg, color: iconColor,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 650, fontSize: "0.88rem", color: "rgba(255,255,255,0.9)" }}>{title}</div>
        <div style={{ fontSize: "0.76rem", color: "rgba(255,255,255,0.45)", marginTop: "0.1rem" }}>{desc}</div>
      </div>
      {onClick ? (
        <Plus size={15} color="rgba(255,255,255,0.35)" style={{ flexShrink: 0 }} />
      ) : (
        <ArrowRight size={15} color="rgba(255,255,255,0.3)" style={{ flexShrink: 0 }} />
      )}
    </div>
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} style={{ all: "unset", display: "block", width: "100%" }}>
        {inner}
      </button>
    );
  }
  return (
    <Link to={to!} style={{ textDecoration: "none", display: "block" }}>
      {inner}
    </Link>
  );
}
