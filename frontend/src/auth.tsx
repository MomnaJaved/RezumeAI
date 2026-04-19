import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { fetchMyProfile } from "./api";

const TOKEN_KEY = "rezume.token";
const EMAIL_KEY = "rezume.email";
const ACCOUNT_ROLE_KEY = "rezume.account_role";

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState<string | null>(() => localStorage.getItem(EMAIL_KEY));
  const [accountRole, setAccountRole] = useState<AccountRole | null>(() => roleFromStorage());

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
