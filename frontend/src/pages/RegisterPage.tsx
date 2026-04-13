import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { registerUser } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";

export default function RegisterPage() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      await registerUser(email, password);
      const e = email.trim().toLowerCase();
      setOk("Verification code sent. Check your email.");
      nav(`/verify-email?email=${encodeURIComponent(e)}`);
    } catch (e) {
      setErr((e as Error).message || "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/login">Login</Link>}>
      <h1 className="landing-auth-title">Create your account</h1>
      <p className="landing-auth-lead">Start screening and ranking candidates with Rezume AI.</p>
      <p className="landing-auth-switch">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
      {err ? <p className="banner banner-error landing-auth-banner">{err}</p> : null}
      {ok ? <p className="banner banner-info landing-auth-banner">{ok}</p> : null}

      <div className="landing-auth-fields">
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
          placeholder="At least 6 characters"
        />
      </div>

      <div className="landing-auth-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !email.trim() || password.length < 6}
          onClick={() => void submit()}
        >
          {busy ? "Creating…" : "Create account"}
        </button>
        <Link to="/" className="btn btn-ghost landing-auth-back">
          Back to home
        </Link>
      </div>
    </AuthMarketingShell>
  );
}
