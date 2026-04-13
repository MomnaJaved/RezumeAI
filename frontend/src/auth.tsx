import React, { createContext, useContext, useMemo, useState } from "react";

const TOKEN_KEY = "rezume.token";
const EMAIL_KEY = "rezume.email";

type AuthState = {
  token: string | null;
  email: string | null;
};

type AuthContextValue = AuthState & {
  login: (token: string, email?: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [email, setEmail] = useState<string | null>(() => localStorage.getItem(EMAIL_KEY));

  const value = useMemo<AuthContextValue>(() => {
    return {
      token,
      email,
      login: (t: string, e?: string) => {
        localStorage.setItem(TOKEN_KEY, t);
        setToken(t);
        if (e) {
          localStorage.setItem(EMAIL_KEY, e);
          setEmail(e);
        }
      },
      logout: () => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(EMAIL_KEY);
        setToken(null);
        setEmail(null);
      },
    };
  }, [token, email]);

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

