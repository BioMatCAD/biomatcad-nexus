import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { UserResponse } from "../api/types";

// Prompt Mestre §6.1 / §9: "Não armazene tokens de longa duração ... em localStorage".
// Esta implementação guarda o token de sessão SOMENTE em memória (estado React). Isso significa
// que um refresh de página derruba a sessão — limitação conhecida e documentada em
// IMPLEMENTATION_STATUS.md, aceita neste incremento em favor de segurança sobre conveniência.
// Refresh token / persistência seguro-por-design é backlog (PM-ONLY-04).

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

interface AuthContextValue {
  user: UserResponse | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const loginResponse = await client.login({ email, password });
      const me = await client.me(loginResponse.access_token);
      setToken(loginResponse.access_token);
      setUser(me);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao autenticar.");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, token, isAuthenticated: Boolean(token && user), isLoading, error, login, logout }),
    [user, token, isLoading, error, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de AuthProvider");
  return ctx;
}
