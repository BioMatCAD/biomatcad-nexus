import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { SystemStatusResponse } from "../api/types";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

interface SystemStatusContextValue {
  status: SystemStatusResponse | null;
  isLoading: boolean;
  error: string | null;
  isDemoMode: boolean;
}

const SystemStatusContext = createContext<SystemStatusContextValue | undefined>(undefined);

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    client
      .systemStatus()
      .then((result) => {
        if (!cancelled) setStatus(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Falha ao obter estado do sistema.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ status, isLoading, error, isDemoMode }), [status, isLoading, error]);

  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}

export function useSystemStatus(): SystemStatusContextValue {
  const ctx = useContext(SystemStatusContext);
  if (!ctx) throw new Error("useSystemStatus deve ser usado dentro de SystemStatusProvider");
  return ctx;
}
