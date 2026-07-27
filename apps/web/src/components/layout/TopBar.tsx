import { useAuth } from "../../context/AuthContext";
import { useTheme } from "../../theme/ThemeProvider";

export function TopBar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  return (
    <header style={styles.header}>
      <span style={styles.title}>BioMatCAD Nexus</span>
      <div style={styles.actions}>
        <button type="button" onClick={toggleTheme} aria-label="Alternar tema claro/escuro">
          {theme === "light" ? "Modo escuro" : "Modo claro"}
        </button>
        {user && (
          <>
            <span aria-live="polite">{user.full_name}</span>
            <button type="button" onClick={logout}>
              Sair
            </button>
          </>
        )}
      </div>
    </header>
  );
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "var(--space-3) var(--space-4)",
    borderBottom: "1px solid var(--color-border)",
    background: "var(--color-surface)",
  },
  title: { fontWeight: 700 },
  actions: { display: "flex", gap: "var(--space-3)", alignItems: "center" },
};
