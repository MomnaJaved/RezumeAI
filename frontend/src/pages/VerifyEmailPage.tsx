import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { verifyEmailCode } from "../api";
import { useToast } from "../toast";

export default function VerifyEmailPage() {
  const nav = useNavigate();
  const toast = useToast();
  const loc = useLocation();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);
  const email = params.get("email") ?? "";

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await verifyEmailCode(email, code.trim());
      toast.success("Email verified. Redirecting to sign in…");
      nav(`/login?verified=1&email=${encodeURIComponent(email)}`);
    } catch (e) {
      toast.error((e as Error).message || "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: "520px", margin: "0 auto" }}>
      <h1>Verify your email</h1>
      <p className="muted">Enter the 6-digit code sent to <strong>{email || "your email"}</strong>.</p>
      <div className="card">
        <label htmlFor="code">Verification code</label>
        <input
          id="code"
          inputMode="numeric"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="123456"
        />
        <div style={{ marginTop: "0.9rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <button type="button" className="primary" disabled={busy || !email || code.trim().length < 4} onClick={() => void submit()}>
            {busy ? "Verifying…" : "Verify"}
          </button>
          <Link className="muted" to="/register">
            Back to register
          </Link>
        </div>
      </div>
    </div>
  );
}

