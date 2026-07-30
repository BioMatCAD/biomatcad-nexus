// Componente de marca (Incremento 2.2, Seção "Identidade Visual"). Reutiliza os arquivos
// PNG reais gerados a partir do arquivo-fonte original (nunca incorporados como Base64 --
// ver docs/brand/ASSETS_NOTICE.md para origem, autoria e situação de licença completas).
//
// Caminho-base: usa `import.meta.env.BASE_URL`, o mesmo padrão já usado por
// `src/api/demoClient.ts` para os assets de demonstração -- isso garante que os arquivos
// resolvam corretamente tanto no build normal (`base: "/"`) quanto no build de demonstração
// do GitHub Pages (`base: "/biomatcad-nexus/"`, ver vite.config.ts).
//
// Nenhuma variante colorida diferente é usada por tema: o próprio PNG de fundo transparente
// é usado em ambos os temas (claro/escuro). Uma limitação real e mensurada de contraste no
// tema escuro (segmento azul-marinho do símbolo, ~1,12:1 contra o fundo escuro) está
// documentada em docs/brand/ASSETS_NOTICE.md como pendência -- não foi "corrigida" recolorindo
// ou distorcendo a marca, conforme instrução explícita de nunca redesenhar o símbolo.
export type BrandLogoVariant = "horizontal" | "symbol";

export type BrandLogoSize = "small" | "medium" | "large";

interface BrandLogoProps {
  variant?: BrandLogoVariant;
  size?: BrandLogoSize;
  className?: string;
  style?: React.CSSProperties;
}

const HORIZONTAL_SRC_BY_SIZE: Record<BrandLogoSize, string> = {
  small: "brand/biomatcad-nexus-logo-horizontal-web-480.png",
  medium: "brand/biomatcad-nexus-logo-horizontal-web-960.png",
  large: "brand/biomatcad-nexus-logo-horizontal-transparent.png",
};

const SYMBOL_SRC = "brand/biomatcad-nexus-symbol-transparent.png";

const HEIGHT_BY_SIZE: Record<BrandLogoSize, number> = {
  small: 28,
  medium: 40,
  large: 96,
};

export function BrandLogo({ variant = "horizontal", size = "medium", className, style }: BrandLogoProps) {
  const base = import.meta.env.BASE_URL;
  const src = variant === "symbol" ? `${base}${SYMBOL_SRC}` : `${base}${HORIZONTAL_SRC_BY_SIZE[size]}`;
  const alt = variant === "symbol" ? "Símbolo BioMatCAD Nexus" : "BioMatCAD Nexus";

  return (
    <img
      src={src}
      alt={alt}
      className={className}
      style={{ height: HEIGHT_BY_SIZE[size], width: "auto", display: "block", ...style }}
    />
  );
}
