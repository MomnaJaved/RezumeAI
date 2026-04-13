import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { loginUser } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useAuth } from "../auth";

export default function LoginPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const { login } = useAuth();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);
  const registered = params.get("registered") === "1";
  const verified = params.get("verified") === "1";
  const prefillEmail = params.get("email") ?? "";

  const [email, setEmail] = useState(prefillEmail);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      const r = await loginUser(email, password);
      login(r.access_token, email.trim().toLowerCase());
      const to = (loc.state as { from?: string } | null)?.from ?? "/dashboard";
      nav(to);
    } catch (e) {
      setErr((e as Error).message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/register">Register</Link>}>
      <h1 className="landing-auth-title">Welcome back</h1>
      <p className="landing-auth-lead">Sign in to continue to your hiring workspace.</p>
      <p className="landing-auth-switch">
        Don’t have an account? <Link to="/register">Create one</Link>
      </p>
      {registered ? (
        <p className="banner banner-info landing-auth-banner">Account created successfully. Please log in.</p>
      ) : null}
      {verified ? (
        <p className="banner banner-info landing-auth-banner">Email verified successfully. Please log in.</p>
      ) : null}
      {err ? <p className="banner banner-error landing-auth-banner">{err}</p> : null}

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
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
        />
      </div>

      <div className="landing-auth-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !email.trim() || password.length < 6}
          onClick={() => void submit()}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <Link to="/" className="btn btn-ghost landing-auth-back">
          Back to home
        </Link>
      </div>
    </AuthMarketingShell>
  );
}
