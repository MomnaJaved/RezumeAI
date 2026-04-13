import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { registerUser } from "../api";

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
    <div style={{ maxWidth: "520px", margin: "0 auto" }}>
      <h1>Register</h1>
      <p className="muted">
        Already have an account? <Link to="/login">Login</Link>
      </p>
      {err ? <p className="banner banner-error">{err}</p> : null}
      {ok ? <p className="banner banner-info">{ok}</p> : null}
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
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 6 characters"
        />
        <div style={{ marginTop: "0.9rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button
            type="button"
            className="primary"
            disabled={busy || !email.trim() || password.length < 6}
            onClick={() => void submit()}
          >
            {busy ? "Creating…" : "Create account"}
          </button>
          <Link className="muted" to="/">
            Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}

