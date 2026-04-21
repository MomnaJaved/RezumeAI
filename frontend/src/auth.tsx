import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchMyProfile } from "./api";

const TOKEN_KEY = "rezume.token";
const EMAIL_KEY = "rezume.email";
const ACCOUNT_ROLE_KEY = "rezume.account_role";

/**
 * Keys under "rezume.*" that are session/auth markers — never wiped on their
 * own. Any *other* "rezume.*" key is treated as per-user cached data (profile,
 * settings, per-job notes, etc.) and must be cleared when the active account
 * changes, otherwise the new user sees the previous user's data.
 */
const AUTH_STORAGE_KEYS = new Set<string>([TOKEN_KEY, EMAIL_KEY, ACCOUNT_ROLE_KEY]);
const USER_STORAGE_PREFIX = "rezume.";

export type AccountRole = "recruiter" | "candidate";

type AuthContextValue = {
  token: string | null;
  email: string | null;
  accountRole: AccountRole | null;
  login: (token: string, email?: string, accountRole?: AccountRole | null) => void;
  logout: () => void;
  refreshAccountRole: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function roleFromStorage(): AccountRole | null {
  const r = localStorage.getItem(ACCOUNT_ROLE_KEY);
  if (r === "candidate" || r === "recruiter") return r;
  return null;
}

/**
 * Remove every "rezume.*" key except the auth markers. Call on logout or when
 * a different email signs in — prevents leaking the previous account's cached
 * profile, settings, and per-job notes into the new session.
 */
function purgeUserScopedStorage(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const k = localStorage.key(i);
      if (k && k.startsWith(USER_STORAGE_PREFIX) && !AUTH_STORAGE_KEYS.has(k)) {
        keys.push(k);
      }
    }
    for (const k of keys) localStorage.removeItem(k);
  } catch {
    /* storage unavailable — nothing to purge */
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState<string | null>(() => localStorage.getItem(EMAIL_KEY));
  const [accountRole, setAccountRole] = useState<AccountRole | null>(() => roleFromStorage());

  // Auto-logout when any API call returns 401 (expired/invalidated token).
  useEffect(() => {
    const handle = () => {
      purgeUserScopedStorage();
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(EMAIL_KEY);
      localStorage.removeItem(ACCOUNT_ROLE_KEY);
      setToken(null);
      setEmail(null);
      setAccountRole(null);
    };
    window.addEventListener("auth:expired", handle);
    return () => window.removeEventListener("auth:expired", handle);
  }, []);

  useEffect(() => {
    if (!token || accountRole) return;
    let cancelled = false;
    (async () => {
      try {
        const p = await fetchMyProfile();
        const ar: AccountRole = p.account_role === "candidate" ? "candidate" : "recruiter";
        if (!cancelled) {
          localStorage.setItem(ACCOUNT_ROLE_KEY, ar);
          setAccountRole(ar);
        }
      } catch {
        if (!cancelled) {
          const ar: AccountRole = "recruiter";
          localStorage.setItem(ACCOUNT_ROLE_KEY, ar);
          setAccountRole(ar);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, accountRole]);

  const refreshAccountRole = useCallback(async () => {
    if (!token) return;
    const p = await fetchMyProfile();
    const ar: AccountRole = p.account_role === "candidate" ? "candidate" : "recruiter";
    localStorage.setItem(ACCOUNT_ROLE_KEY, ar);
    setAccountRole(ar);
  }, [token]);

  const value = useMemo<AuthContextValue>(() => {
    return {
      token,
      email,
      accountRole,
      login: (t: string, e?: string, ar?: AccountRole | null) => {
        // If a *different* account is signing in (or this is a fresh login
        // after we lost the email marker), drop any cached per-user data so
        // the new session cannot inherit the previous user's profile, saved
        // settings, or per-job notes from localStorage.
        const prevEmail = localStorage.getItem(EMAIL_KEY);
        const nextEmail = e ? e.trim().toLowerCase() : "";
        const prevEmailNorm = prevEmail ? prevEmail.trim().toLowerCase() : "";
        if (!prevEmailNorm || (nextEmail && prevEmailNorm !== nextEmail)) {
          purgeUserScopedStorage();
        }

        localStorage.setItem(TOKEN_KEY, t);
        setToken(t);
        if (e) {
          localStorage.setItem(EMAIL_KEY, e);
          setEmail(e);
        }
        const role: AccountRole = ar === "candidate" ? "candidate" : "recruiter";
        localStorage.setItem(ACCOUNT_ROLE_KEY, role);
        setAccountRole(role);
      },
      logout: () => {
        purgeUserScopedStorage();
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(EMAIL_KEY);
        localStorage.removeItem(ACCOUNT_ROLE_KEY);
        setToken(null);
        setEmail(null);
        setAccountRole(null);
      },
      refreshAccountRole,
    };
  }, [token, email, accountRole, refreshAccountRole]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used inside AuthProvider");
  return v;
}

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
