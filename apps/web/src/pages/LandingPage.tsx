import { Link } from "react-router-dom";
import { BrandLogo } from "../components/brand/BrandLogo";
import { DemoBanner } from "../components/DemoBanner";

export function LandingPage() {
  return (
    <div>
      <DemoBanner />
      <header style={styles.hero}>
        <BrandLogo variant="horizontal" size="large" style={{ margin: "0 auto var(--space-4)" }} />
        <p style={styles.eyebrow}>Incremento 1 — fundação executável</p>
        <h1 style={styles.h1}>BioMatCAD Nexus</h1>
        <p style={styles.lead}>
          Plataforma integrada de engenharia computacional de biomateriais: CAD 3D paramétrico,
          simulação FEM, banco de materiais, machine learning local e otimização multiobjetivo —
          com evolução planejada para laboratório, terapia celular e telemedicina.
        </p>
        <div style={styles.ctaRow}>
          <Link to="/login" style={styles.ctaPrimary}>
            Entrar
          </Link>
        </div>
        <p style={{ marginTop: "var(--space-4)" }}>
          <Link to="/about">Sobre o projeto</Link>
        </p>
      </header>

      <section style={styles.status}>
        <h2>Status real deste incremento</h2>
        <p>
          Esta é a fundação técnica do produto: autenticação mínima, painel autenticado,
          verificação de saúde do sistema e o contrato de estados operacionais. Os módulos
          científicos (CAD, FEM, materiais, ML) e o envelope clínico/laboratorial ainda não
          foram implementados — consulte <code>IMPLEMENTATION_STATUS.md</code> no repositório
          para o inventário completo do que é real, demonstrativo ou planejado.
        </p>
      </section>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  hero: { padding: "var(--space-8) var(--space-6)", maxWidth: 720, margin: "0 auto", textAlign: "center" },
  eyebrow: { color: "var(--color-accent)", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", fontSize: "0.75rem" },
  h1: { fontSize: "2.5rem", margin: "var(--space-2) 0" },
  lead: { color: "var(--color-text-secondary)", fontSize: "1.125rem", lineHeight: 1.6 },
  ctaRow: { marginTop: "var(--space-6)" },
  ctaPrimary: {
    display: "inline-block",
    background: "var(--color-accent)",
    color: "white",
    padding: "var(--space-3) var(--space-6)",
    borderRadius: "var(--radius-md)",
    textDecoration: "none",
    fontWeight: 600,
  },
  status: {
    maxWidth: 640,
    margin: "var(--space-8) auto",
    padding: "var(--space-4)",
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
  },
};
