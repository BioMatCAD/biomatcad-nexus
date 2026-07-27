import { type FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { DemoBanner } from "../components/DemoBanner";
import { ClinicalSuiteIndicator } from "../components/layout/ClinicalSuiteIndicator";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { login, isAuthenticated, isLoading, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  if (isAuthenticated) {
    const redirectTo = (location.state as { from?: string } | null)?.from ?? "/app";
    return <Navigate to={redirectTo} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await login(email, password);
      navigate("/app", { replace: true });
    } catch {
      // erro já exposto via useAuth().error
    }
  }

  return (
    <div style={styles.page}>
      <DemoBanner />
      <div style={styles.card}>
        <h1 style={{ marginTop: 0 }}>Entrar</h1>
        <ClinicalSuiteIndicator />

        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor="email" style={styles.label}>
            E-mail
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={styles.input}
          />

          <label htmlFor="password" style={styles.label}>
            Senha
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={styles.input}
          />

          {error && (
            <p role="alert" style={styles.error}>
              {error}
            </p>
          )}

          <button type="submit" disabled={isLoading} style={styles.submit}>
            {isLoading ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <p style={styles.hint}>
          Ambiente de demonstração: <code>demo@biomatcad.example</code> /{" "}
          <code>demo-synthetic-password-123</code> (usuário sintético, seed local).
        </p>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "100vh", padding: "var(--space-4)" },
  card: { width: "100%", maxWidth: 380, background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: "var(--radius-lg)", padding: "var(--space-6)" },
  label: { display: "block", marginTop: "var(--space-3)", marginBottom: "var(--space-1)", fontWeight: 600, fontSize: "0.875rem" },
  input: { width: "100%", padding: "var(--space-2) var(--space-3)", borderRadius: "var(--radius-sm)", border: "1px solid var(--color-border)", background: "var(--color-bg)", color: "var(--color-text-primary)" },
  error: { color: "var(--color-error)", fontSize: "0.875rem" },
  submit: { marginTop: "var(--space-4)", width: "100%", padding: "var(--space-3)", background: "var(--color-accent)", color: "white", border: "none", borderRadius: "var(--radius-sm)", fontWeight: 600, cursor: "pointer" },
  hint: { marginTop: "var(--space-4)", fontSize: "0.75rem", color: "var(--color-text-secondary)" },
};
