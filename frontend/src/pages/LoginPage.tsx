import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { completeLoginOtp, loginUser, requestForgotPassword, resetPasswordWithCode } from "../api";
import AuthMarketingShell from "../AuthMarketingShell";
import { useAuth } from "../auth";
import { useToast } from "../toast";

export default function LoginPage() {
  const nav = useNavigate();
  const loc = useLocation();
  const toast = useToast();
  const { login } = useAuth();
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search]);
  const registered = params.get("registered") === "1";
  const verified = params.get("verified") === "1";
  const prefillEmail = params.get("email") ?? "";

  const [email, setEmail] = useState(prefillEmail);
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpChallengeId, setOtpChallengeId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  /** Inline forgot-password: same email as Rezume account → code → new password (no separate page required). */
  const [loginPane, setLoginPane] = useState<"signin" | "reset-email" | "reset-code">("signin");
  const [resetEmail, setResetEmail] = useState("");
  const [resetCode, setResetCode] = useState("");
  const [resetNewPwd, setResetNewPwd] = useState("");
  const [resetConfirmPwd, setResetConfirmPwd] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);
  const regShown = useRef(false);
  const verShown = useRef(false);

  useEffect(() => {
    if (registered && !regShown.current) {
      regShown.current = true;
      toast.info("Account created. Sign in below.");
    }
  }, [registered, toast]);
  useEffect(() => {
    if (verified && !verShown.current) {
      verShown.current = true;
      toast.success("Email verified. Sign in below.");
    }
  }, [verified, toast]);

  async function submitPassword() {
    setLoginError(null);
    if (!email.trim()) {
      setLoginError("Enter your email address.");
      return;
    }
    if (!password) {
      setLoginError("Enter your password.");
      return;
    }
    setBusy(true);
    try {
      const r = await loginUser(email, password);
      if (r.requires_otp && r.otp_challenge_id) {
        setOtpChallengeId(r.otp_challenge_id);
        setOtpCode("");
        toast.info("Enter the sign-in code we emailed you.");
        return;
      }
      const token = r.access_token;
      if (!token) {
        const msg = "Unexpected response from server. Try again.";
        setLoginError(msg);
        toast.error(msg);
        return;
      }
      const ar = (r as { account_role?: string | null }).account_role === "candidate" ? "candidate" : "recruiter";
      login(token, email.trim().toLowerCase(), ar);
      const from = (loc.state as { from?: string } | null)?.from;
      const to = from && from !== "/login" ? from : ar === "candidate" ? "/candidate" : "/dashboard";
      nav(to);
    } catch (e) {
      const raw = (e as Error).message || "Sign-in failed.";
      let msg = raw;
      if (raw.includes("Invalid email or password")) {
        msg = "Wrong email or password. Check both and try again, or use “Forgot password?” below.";
      } else if (raw.toLowerCase().includes("not verified") || raw.toLowerCase().includes("email not verified")) {
        msg = "This email is not verified yet. Complete registration from the link in your inbox, or register again.";
      }
      setLoginError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  async function submitOtp() {
    if (!otpChallengeId) return;
    setBusy(true);
    try {
      const r = await completeLoginOtp(otpChallengeId, otpCode.trim());
      const ar = r.account_role === "candidate" ? "candidate" : "recruiter";
      login(r.access_token, email.trim().toLowerCase(), ar);
      setOtpChallengeId(null);
      setOtpCode("");
      const from = (loc.state as { from?: string } | null)?.from;
      const to = from && from !== "/login" ? from : ar === "candidate" ? "/candidate" : "/dashboard";
      nav(to);
    } catch (e) {
      toast.error((e as Error).message || "Invalid or expired code");
    } finally {
      setBusy(false);
    }
  }

  function openForgotPassword() {
    setLoginError(null);
    setResetError(null);
    setResetEmail(email.trim());
    setResetCode("");
    setResetNewPwd("");
    setResetConfirmPwd("");
    setLoginPane("reset-email");
  }

  async function sendPasswordResetCode() {
    setResetError(null);
    const em = resetEmail.trim().toLowerCase();
    if (!em) {
      setResetError("Enter the email address for your Rezume AI account.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) {
      setResetError("Enter a valid email address.");
      return;
    }
    setBusy(true);
    try {
      await requestForgotPassword(em);
      setLoginPane("reset-code");
      toast.info(
        "If that email is registered, we sent a 6-digit code. Use it below with a new password — or check the API terminal if email is not configured.",
      );
    } catch (e) {
      const msg = (e as Error).message || "Could not send reset email.";
      setResetError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  async function submitPasswordReset() {
    setResetError(null);
    const em = resetEmail.trim().toLowerCase();
    if (resetNewPwd !== resetConfirmPwd) {
      setResetError("New password and confirmation do not match.");
      return;
    }
    if (resetNewPwd.length < 8) {
      setResetError("New password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await resetPasswordWithCode(em, resetCode.trim(), resetNewPwd);
      toast.success("Password updated. Sign in with your new password.");
      setEmail(em);
      setPassword("");
      setLoginPane("signin");
      setResetCode("");
      setResetNewPwd("");
      setResetConfirmPwd("");
    } catch (e) {
      const msg = (e as Error).message || "Reset failed. Check the code or request a new one.";
      setResetError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthMarketingShell navRight={<Link to="/register">Register</Link>}>
      {otpChallengeId ? (
        <>
          <h1 className="landing-auth-title">Two-step sign-in</h1>
          <div className="landing-auth-fields">
            <p className="landing-auth-lead" style={{ marginBottom: "0.75rem" }}>
              Two-factor sign-in is on for this account. Enter the 6-digit code from your email.
            </p>
            <label htmlFor="otp">Sign-in code</label>
            <input
              id="otp"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
              placeholder="000000"
            />
          </div>
          <div className="landing-auth-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || otpCode.trim().length < 4}
              onClick={() => void submitOtp()}
            >
              {busy ? "Verifying…" : "Verify and sign in"}
            </button>
            <button
              type="button"
              className="btn btn-ghost landing-auth-back"
              disabled={busy}
              onClick={() => {
                setOtpChallengeId(null);
                setOtpCode("");
              }}
            >
              Back
            </button>
          </div>
        </>
      ) : loginPane === "reset-email" ? (
        <>
          <h1 className="landing-auth-title">Reset password</h1>
          <p className="landing-auth-lead">
            Enter the <strong>same email</strong> you use for your Rezume AI account. We will email a one-time code if that
            account exists.
          </p>
          {resetError ? (
            <div className="landing-auth-form-error" role="alert">
              {resetError}
            </div>
          ) : null}
          <div className="landing-auth-fields">
            <label htmlFor="reset-email">Account email</label>
            <input
              id="reset-email"
              type="email"
              autoComplete="email"
              value={resetEmail}
              onChange={(e) => {
                setResetEmail(e.target.value);
                setResetError(null);
              }}
              placeholder="you@example.com"
            />
          </div>
          <div className="landing-auth-actions">
            <button type="button" className="btn btn-primary" disabled={busy || !resetEmail.trim()} onClick={() => void sendPasswordResetCode()}>
              {busy ? "Sending…" : "Send reset code"}
            </button>
            <button
              type="button"
              className="btn btn-ghost landing-auth-back"
              disabled={busy}
              onClick={() => {
                setLoginPane("signin");
                setResetError(null);
              }}
            >
              Back to sign in
            </button>
          </div>
          <p className="landing-auth-forgot">
            <Link to="/forgot-password">Open full-page reset</Link>
          </p>
        </>
      ) : loginPane === "reset-code" ? (
        <>
          <h1 className="landing-auth-title">Choose a new password</h1>
          <p className="landing-auth-lead">
            We sent a 6-digit code to <strong>{resetEmail.trim() || "your email"}</strong>. Enter it here with your new password
            for this Rezume AI account.
          </p>
          {resetError ? (
            <div className="landing-auth-form-error" role="alert">
              {resetError}
            </div>
          ) : null}
          <div className="landing-auth-fields">
            <label htmlFor="reset-code">Reset code</label>
            <input
              id="reset-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={resetCode}
              onChange={(e) => {
                setResetCode(e.target.value.replace(/\D/g, "").slice(0, 8));
                setResetError(null);
              }}
              placeholder="000000"
            />
            <label htmlFor="reset-new">New password</label>
            <input
              id="reset-new"
              type="password"
              autoComplete="new-password"
              value={resetNewPwd}
              onChange={(e) => {
                setResetNewPwd(e.target.value);
                setResetError(null);
              }}
              placeholder="At least 8 characters"
            />
            <label htmlFor="reset-confirm">Confirm new password</label>
            <input
              id="reset-confirm"
              type="password"
              autoComplete="new-password"
              value={resetConfirmPwd}
              onChange={(e) => {
                setResetConfirmPwd(e.target.value);
                setResetError(null);
              }}
              placeholder="Repeat new password"
            />
          </div>
          <div className="landing-auth-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || resetCode.trim().length < 4 || resetNewPwd.length < 8}
              onClick={() => void submitPasswordReset()}
            >
              {busy ? "Updating…" : "Update password & return to sign in"}
            </button>
            <button
              type="button"
              className="btn btn-ghost landing-auth-back"
              disabled={busy}
              onClick={() => {
                setLoginPane("reset-email");
                setResetError(null);
              }}
            >
              Resend / change email
            </button>
          </div>
        </>
      ) : (
        <>
          <h1 className="landing-auth-title">Welcome back</h1>
          <p className="landing-auth-lead">Sign in to continue to your hiring workspace.</p>
          <p className="landing-auth-switch">
            Don’t have an account? <Link to="/register">Create one</Link>
          </p>
          {loginError ? (
            <div className="landing-auth-form-error" role="alert">
              {loginError}
            </div>
          ) : null}
          <div className="landing-auth-fields">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setLoginError(null);
              }}
              placeholder="you@example.com"
            />
            <label htmlFor="pw">Password</label>
            <input
              id="pw"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setLoginError(null);
              }}
              placeholder="••••••••"
            />
            <p className="landing-auth-hint muted">Accounts use a password of at least 8 characters.</p>
            <p className="landing-auth-forgot">
              <button type="button" className="landing-auth-link-btn" onClick={openForgotPassword}>
                Forgot password?
              </button>
            </p>
          </div>

          <div className="landing-auth-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !email.trim() || !password}
              onClick={() => void submitPassword()}
            >
              {busy ? "Signing in…" : "Sign in"}
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
