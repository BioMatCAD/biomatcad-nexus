import { NavLink } from "react-router-dom";

// Espaços de trabalho iniciais (Prompt Mestre §8.1). Apenas "Início" tem rota real neste
// incremento; os demais aparecem desabilitados e rotulados como planejados, para não simular
// funções inexistentes (Prompt Mestre §3.1).
// Espaços de trabalho reais do Incremento 2.1 -- têm rota funcional, ao contrário dos
// planejados abaixo (Prompt Mestre §3.1: nunca simular funções inexistentes).
const REAL_WORKSPACES = [
  { label: "Materiais", to: "/app/materials" },
  { label: "Projetos BioMatCAD", to: "/app/projects" },
  { label: "Observabilidade", to: "/app/observability" },
];

const PLANNED_WORKSPACES = [
  "BioMat Constructor",
  "CAD/Scaffolds",
  "Simulações",
  "Otimização",
  "Cristalografia",
  "Imagens médicas",
  "Fabricação",
  "Laboratório",
  "Terapia celular",
  "Estudos e ELN",
  "Clínica",
  "Teleatendimento",
  "Pacientes",
  "Agenda",
  "Qualidade",
  "Relatórios",
  "Administração",
];

export function Sidebar() {
  return (
    <nav aria-label="Navegação principal" style={styles.nav}>
      <ul style={styles.list}>
        <li>
          <NavLink to="/app" end style={({ isActive }) => ({ ...styles.link, ...(isActive ? styles.linkActive : {}) })}>
            Início
          </NavLink>
        </li>
        {REAL_WORKSPACES.map((workspace) => (
          <li key={workspace.to}>
            <NavLink to={workspace.to} style={({ isActive }) => ({ ...styles.link, ...(isActive ? styles.linkActive : {}) })}>
              {workspace.label}
            </NavLink>
          </li>
        ))}
        {PLANNED_WORKSPACES.map((workspace) => (
          <li key={workspace}>
            <span style={styles.linkDisabled} aria-disabled="true" title="Planejado — ainda não implementado">
              {workspace}
              <span style={styles.badge}>planejado</span>
            </span>
          </li>
        ))}
      </ul>
    </nav>
  );
}

const styles: Record<string, React.CSSProperties> = {
  nav: {
    width: 240,
    borderRight: "1px solid var(--color-border)",
    padding: "var(--space-4)",
    flexShrink: 0,
  },
  list: { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 4 },
  link: {
    display: "block",
    padding: "var(--space-2) var(--space-3)",
    borderRadius: "var(--radius-sm)",
    color: "var(--color-text-primary)",
    textDecoration: "none",
  },
  linkActive: {
    background: "var(--color-accent)",
    color: "white",
  },
  linkDisabled: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "var(--space-2) var(--space-3)",
    color: "var(--color-text-secondary)",
    cursor: "not-allowed",
  },
  badge: {
    fontSize: "0.625rem",
    textTransform: "uppercase",
    background: "var(--color-border)",
    borderRadius: "var(--radius-sm)",
    padding: "1px 6px",
  },
};
