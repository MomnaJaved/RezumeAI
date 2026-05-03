import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { requestForgotPassword, resetPasswordWithCode } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useToast } from "../toast";

export default function ForgotPasswordPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPwd, setNewPwd] = useState("");
  const [confirmPwd, setConfirmPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function sendCode() {
    setFormError(null);
    if (!email.trim()) {
      setFormError("Enter your email address.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setFormError("Enter a valid email address.");
      return;
    }
    setBusy(true);
    try {
      await requestForgotPassword(email.trim());
      setStep(2);
      setCode("");
      setNewPwd("");
      setConfirmPwd("");
      toast.info(
        "If that address has a verified account, a reset code was issued. Check your inbox — or the API server terminal if email is not configured (SMTP_HOST).",
      );
    } catch (e) {
      const msg = (e as Error).message || "Could not send reset email.";
      setFormError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  async function submitReset() {
    setFormError(null);
    if (newPwd !== confirmPwd) {
      setFormError("New password and confirmation do not match.");
      return;
    }
    if (newPwd.length < 8) {
      setFormError("New password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await resetPasswordWithCode(email.trim(), code.trim(), newPwd);
      toast.success("Password updated. Sign in with your new password.");
      nav(`/login?email=${encodeURIComponent(email.trim())}`);
    } catch (e) {
      const msg = (e as Error).message || "Reset failed.";
      setFormError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/login">Sign in</Link>}>
      <h1 className="landing-auth-title">Reset password</h1>
      <p className="landing-auth-lead">
        {step === 1
          ? "Enter the email you use for Rezume AI. We will send a one-time code if the account exists and is verified."
          : `Enter the code from your email and choose a new password for ${email}.`}
      </p>

      {formError ? (
        <div className="landing-auth-form-error" role="alert">
          {formError}
        </div>
      ) : null}

      {step === 1 ? (
        <>
          <div className="landing-auth-fields">
            <label htmlFor="fp-email">Email</label>
            <input
              id="fp-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setFormError(null);
              }}
              placeholder="you@example.com"
            />
          </div>
          <div className="landing-auth-role-actions" style={{ marginTop: "1.35rem" }}>
            <Link to="/login" className="landing-auth-role-action-btn ghost">
              Back to sign in
            </Link>
            <button type="button" className="landing-auth-role-action-btn primary" disabled={busy || !email.trim()} onClick={() => void sendCode()}>
              {busy ? "Sending…" : "Send reset code →"}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="landing-auth-fields">
            <label htmlFor="fp-code">Reset code</label>
            <input
              id="fp-code"
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
            <label htmlFor="fp-new">New password</label>
            <input
              id="fp-new"
              type="password"
              autoComplete="new-password"
              value={newPwd}
              onChange={(e) => {
                setNewPwd(e.target.value);
                setFormError(null);
              }}
              placeholder="At least 8 characters"
            />
            <label htmlFor="fp-confirm">Confirm new password</label>
            <input
              id="fp-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPwd}
              onChange={(e) => {
                setConfirmPwd(e.target.value);
                setFormError(null);
              }}
              placeholder="Repeat new password"
            />
          </div>
          <div className="landing-auth-role-actions" style={{ marginTop: "1.35rem" }}>
            <button
              type="button"
              className="landing-auth-role-action-btn ghost"
              disabled={busy}
              onClick={() => {
                setStep(1);
                setFormError(null);
              }}
            >
              Different email
            </button>
            <button
              type="button"
              className="landing-auth-role-action-btn primary"
              disabled={busy || code.trim().length < 4 || newPwd.length < 8}
              onClick={() => void submitReset()}
            >
              {busy ? "Updating…" : "Update password →"}
            </button>
          </div>
        </>
      )}
    </AuthMarketingShell>
  );
}
