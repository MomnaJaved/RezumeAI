import { useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { verifyEmailCode } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useToast } from "../toast";

export default function VerifyEmailPage() {
  const nav = useNavigate();
  const toast = useToast();
  const loc = useLocation();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);
  const email = params.get("email") ?? "";

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function submit() {
    setFormError(null);
    if (!email.trim()) {
      setFormError("No email in the link. Go back to register and create your account again.");
      return;
    }
    if (code.trim().length < 4) {
      setFormError("Enter the code from your email.");
      return;
    }
    setBusy(true);
    try {
      await verifyEmailCode(email, code.trim());
      toast.success("Email verified. Redirecting to sign in…");
      nav(`/login?verified=1&email=${encodeURIComponent(email)}`);
    } catch (e) {
      const msg = (e as Error).message || "Verification failed";
      setFormError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/login">Sign in</Link>}>
      <h1 className="landing-auth-title">Verify your email</h1>
      <p className="landing-auth-lead">
        Enter the 6-digit code sent to <strong>{email || "your email"}</strong>. If you run the API locally without SMTP,
        the code is printed in the terminal where the server runs.
      </p>
      <p className="landing-auth-switch">
        Wrong address? <Link to="/register">Register again</Link>
      </p>

      {formError ? (
        <div className="landing-auth-form-error" role="alert">
          {formError}
        </div>
      ) : null}

      <div className="landing-auth-fields">
        <label htmlFor="code">Verification code</label>
        <input
          id="code"
          type="text"
          inputMode="numeric"
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => {
            setCode(e.target.value.replace(/\D/g, "").slice(0, 8));
            setFormError(null);
          }}
          placeholder="000000"
        />
      </div>

      <div className="landing-auth-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !email.trim() || code.trim().length < 4}
          onClick={() => void submit()}
        >
          {busy ? "Verifying…" : "Verify and continue"}
        </button>
        <Link to="/register" className="btn btn-ghost landing-auth-back">
          Back to register
        </Link>
        <Link to="/" className="btn btn-ghost landing-auth-back">
          Back to home
        </Link>
      </div>
    </AuthMarketingShell>
  );
}
