import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { registerUser } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useToast } from "../toast";

export default function RegisterPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await registerUser(email, password);
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
      <p className="landing-auth-lead">Start screening and ranking candidates with Rezume AI.</p>
      <p className="landing-auth-switch">
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
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
