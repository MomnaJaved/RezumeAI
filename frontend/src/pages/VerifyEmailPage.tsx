import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { verifyEmailCode } from "../api";

export default function VerifyEmailPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);
  const email = params.get("email") ?? "";

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      await verifyEmailCode(email, code.trim());
      setOk("Email verified successfully. Please log in.");
      nav(`/login?verified=1&email=${encodeURIComponent(email)}`);
    } catch (e) {
      setErr((e as Error).message || "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: "520px", margin: "0 auto" }}>
      <h1>Verify your email</h1>
      <p className="muted">Enter the 6-digit code sent to <strong>{email || "your email"}</strong>.</p>
      {err ? <p className="banner banner-error">{err}</p> : null}
      {ok ? <p className="banner banner-info">{ok}</p> : null}
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

