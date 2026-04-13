import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { loginUser } from "../api";
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
    <div style={{ maxWidth: "520px", margin: "0 auto" }}>
      <h1>Login</h1>
      <p className="muted">
        Don’t have an account? <Link to="/register">Register</Link>
      </p>
      {registered ? <p className="banner banner-info">Account created successfully. Please log in.</p> : null}
      {verified ? <p className="banner banner-info">Email verified successfully. Please log in.</p> : null}
      {err ? <p className="banner banner-error">{err}</p> : null}
      <div className="card">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
        />
        <div style={{ height: "0.75rem" }} />
        <label htmlFor="pw">Password</label>
        <input
          id="pw"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
        />
        <div style={{ marginTop: "0.9rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            type="button"
            className="primary"
            disabled={busy || !email.trim() || password.length < 6}
            onClick={() => void submit()}
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <Link className="muted" to="/">
            Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}

