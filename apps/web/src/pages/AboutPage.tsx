import { Link } from "react-router-dom";
import { BrandLogo } from "../components/brand/BrandLogo";
import { DemoBanner } from "../components/DemoBanner";

// Página "Sobre" (Incremento 2.2, Seção "Identidade Visual"). Pública (não exige login) --
// mesma convenção de LandingPage/LoginPage. Traz a marca oficial e um resumo da proveniência,
// autoria e situação de licença da logomarca; o documento completo vive em
// docs/brand/ASSETS_NOTICE.md no repositório.
export function AboutPage() {
  return (
    <div style={styles.page}>
      <DemoBanner />
      <div style={styles.card}>
        <BrandLogo variant="horizontal" size="medium" style={{ marginBottom: "var(--space-4)" }} />
        <h1 style={{ marginTop: 0 }}>Sobre o BioMatCAD Nexus</h1>
        <p>
          BioMatCAD Nexus é uma plataforma de pesquisa em desenvolvimento para design
          computacional de scaffolds de biomateriais -- geometria paramétrica (TPMS/Gyroid hoje,
          Voronoi em preparação), simulação, banco de materiais e rastreabilidade completa de
          cada execução (receita → job → artefato → manifesto).
        </p>
        <p>
          Este é um protótipo técnico de pesquisa. Não processa dados de pacientes, não realiza
          diagnóstico, não integra com prontuário ou sistemas hospitalares, e nenhum resultado
          aqui produzido constitui validação clínica ou experimental real -- consulte{" "}
          <code>IMPLEMENTATION_STATUS.md</code> no repositório para o inventário completo do que
          é real, sintético ou planejado nesta rodada.
        </p>

        <h2 style={styles.h2}>Identidade visual</h2>
        <p>
          A logomarca oficial é preservada em seu arquivo original, sem redesenho, distorção ou
          alteração de proporções. As variantes usadas nesta interface (horizontal, símbolo
          isolado, favicon, ícones PWA) foram derivadas por operações não-destrutivas (recorte,
          remoção de fundo por conectividade de borda, redimensionamento) -- nunca por
          redesenho manual. Origem, autoria, situação de licença e uma limitação de contraste
          conhecida e documentada (não corrigida por recolorização) estão detalhadas em{" "}
          <code>docs/brand/ASSETS_NOTICE.md</code> no repositório. Nenhuma declaração de marca
          registrada (® ou ™) é feita.
        </p>

        <p style={styles.backRow}>
          <Link to="/">← Voltar à página inicial</Link>
        </p>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: "flex", flexDirection: "column", alignItems: "center", padding: "var(--space-6) var(--space-4)" },
  card: {
    width: "100%",
    maxWidth: 640,
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-lg)",
    padding: "var(--space-6)",
    lineHeight: 1.6,
  },
  h2: { fontSize: "1.125rem", marginTop: "var(--space-6)" },
  backRow: { marginTop: "var(--space-6)" },
};
