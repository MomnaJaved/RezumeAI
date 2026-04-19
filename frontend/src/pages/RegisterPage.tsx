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
      toast.success(
        "Verification code sent. Check your email — or the API server terminal if SMTP is not configured.",
      );
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
        <div className="landing-auth-fields" style={{ display: "grid", gap: "0.65rem" }}>
          <p style={{ margin: 0, fontSize: "0.9rem", color: "rgba(255,255,255,0.75)" }}>Sign up as:</p>
          <label className="landing-auth-role">
            <input type="radio" name="role" checked={accountRole === "recruiter"} onChange={() => setAccountRole("recruiter")} />
            <span>
              <strong>Recruiter</strong> — post jobs, search the candidate pool, shortlist, and hire.
            </span>
          </label>
          <label className="landing-auth-role">
            <input type="radio" name="role" checked={accountRole === "candidate"} onChange={() => setAccountRole("candidate")} />
            <span>
              <strong>Candidate</strong> — upload your resume, browse jobs, apply, and track your status.
            </span>
          </label>
          <div className="landing-auth-actions">
            <button type="button" className="btn btn-primary" onClick={() => setStep(1)}>
              Continue
            </button>
            <Link to="/" className="btn btn-ghost landing-auth-back">
              Back to home
            </Link>
          </div>
        </div>
      ) : (
        <>
          <div className="landing-auth-fields">
            <button type="button" className="btn btn-ghost landing-auth-back" style={{ marginBottom: "0.5rem" }} onClick={() => setStep(0)}>
              ← Change role
            </button>
            <p style={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.65)", marginBottom: "0.5rem" }}>
              Signing up as: <strong>{accountRole === "candidate" ? "Candidate" : "Recruiter"}</strong>
            </p>
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
          <div className="landing-auth-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !email.trim() || password.length < 8}
              onClick={() => void submit()}
            >
              {busy ? "Creating…" : "Create account"}
            </button>
            <Link to="/" className="btn btn-ghost landing-auth-back">
              Back to home
            </Link>
          </div>
        </>
      )}
    </AuthMarketingShell>
  );
}
