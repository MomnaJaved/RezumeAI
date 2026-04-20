import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { registerUser } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useToast } from "../toast";

type RoleChoice = "recruiter" | "candidate";

export default function RegisterPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState<0 | 1>(0);
  const [accountRole, setAccountRole] = useState<RoleChoice>("recruiter");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await registerUser(email, password, accountRole);
      const e = email.trim().toLowerCase();
      toast.success("Verification code sent. Check your email.");
      nav(`/verify-email?email=${encodeURIComponent(e)}`);
    } catch (e) {
      toast.error((e as Error).message || "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/login">Login</Link>}>
      <h1 className="landing-auth-title">Create your account</h1>
      <p className="landing-auth-lead">
        {step === 0 ? "Choose how you will use Rezume AI." : "Enter your email and password to finish signup."}
      </p>
      <p className="landing-auth-switch">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>

      {step === 0 ? (
        <div style={{ display: "grid", gap: "1rem" }}>
          <p className="landing-auth-role-label">Sign up as:</p>
          <div className="landing-auth-role-cards">
            {/* Recruiter card */}
            <button
              type="button"
              className={`landing-auth-role-card${accountRole === "recruiter" ? " selected" : ""}`}
              onClick={() => setAccountRole("recruiter")}
            >
              <span className="landing-auth-role-card-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="26" height="26">
                  <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z" />
                </svg>
              </span>
              {accountRole === "recruiter" && (
                <span className="landing-auth-role-card-check">✓</span>
              )}
              <span className="landing-auth-role-card-title">Recruiter</span>
              <span className="landing-auth-role-card-desc">
                Post jobs, search the candidate pool, shortlist, and hire.
              </span>
            </button>

            {/* Candidate card */}
            <button
              type="button"
              className={`landing-auth-role-card${accountRole === "candidate" ? " selected" : ""}`}
              onClick={() => setAccountRole("candidate")}
            >
              <span className="landing-auth-role-card-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="26" height="26">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v1h16v-1c0-2.66-5.33-4-8-4z" />
                </svg>
              </span>
              {accountRole === "candidate" && (
                <span className="landing-auth-role-card-check">✓</span>
              )}
              <span className="landing-auth-role-card-title">Candidate</span>
              <span className="landing-auth-role-card-desc">
                Upload your resume, browse jobs, apply, and track your status.
              </span>
            </button>
          </div>

          <div className="landing-auth-role-actions">
            <Link to="/" className="landing-auth-role-action-btn ghost">
              Back to home
            </Link>
            <button type="button" className="landing-auth-role-action-btn primary" onClick={() => setStep(1)}>
              Continue as {accountRole === "recruiter" ? "Recruiter" : "Candidate"} →
            </button>
          </div>
        </div>
      ) : (
        <>
          <div className="landing-auth-fields">
            <p style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.65)", margin: "0 0 0.25rem" }}>
              Signing up as: <strong>{accountRole === "candidate" ? "Candidate" : "Recruiter"}</strong>
            </p>
            <div style={{ display: "flex" }}>
              <button type="button" className="landing-auth-role-action-btn ghost" style={{ marginBottom: "1rem" }} onClick={() => setStep(0)}>
                ← Change role
              </button>
            </div>
            
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
            <label htmlFor="pw">Password</label>
            <input
              id="pw"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
            />
          </div>
          <div className="landing-auth-role-actions" style={{ marginTop: "1.35rem" }}>
            <Link to="/" className="landing-auth-role-action-btn ghost">
              Back to home
            </Link>
            <button
              type="button"
              className="landing-auth-role-action-btn primary"
              disabled={busy || !email.trim() || password.length < 8}
              onClick={() => void submit()}
            >
              {busy ? "Creating…" : "Create account →"}
            </button>
          </div>
        </>
      )}
    </AuthMarketingShell>
  );
}
