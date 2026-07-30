// Incremento 2.2 (Identidade Visual): garante que os assets de marca existem de fato, que
// index.html/manifest.json usam caminhos base-path-corretos (nunca absolutos hardcoded), e que
// o arquivo original nunca é alterado -- mesmo princípio de "nunca fingir sucesso" aplicado a
// assets binários: se um arquivo esperado não existir, o teste falha em vez de assumir.
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const BRAND_DIR = path.resolve(__dirname, "../public/brand");

const EXPECTED_ASSETS = [
  "biomatcad-nexus-logo-original.png",
  "biomatcad-nexus-logo-horizontal-transparent.png",
  "biomatcad-nexus-logo-horizontal-web-960.png",
  "biomatcad-nexus-logo-horizontal-web-480.png",
  "biomatcad-nexus-symbol-transparent.png",
  "favicon-16.png",
  "favicon-32.png",
  "favicon-48.png",
  "apple-touch-icon-180.png",
  "pwa-icon-192.png",
  "pwa-icon-512.png",
];

describe("assets de identidade visual (public/brand/)", () => {
  it.each(EXPECTED_ASSETS)("%s existe", (filename) => {
    expect(existsSync(path.join(BRAND_DIR, filename))).toBe(true);
  });

  it("o arquivo original preserva o SHA-256 documentado em docs/brand/ASSETS_NOTICE.md", () => {
    const original = readFileSync(path.join(BRAND_DIR, "biomatcad-nexus-logo-original.png"));
    const sha256 = createHash("sha256").update(original).digest("hex");
    expect(sha256).toBe("45016352df9caa513502734cc98fd3d49d07b70042d44881a579dca944271daf");
  });
});

describe("index.html referencia favicon/manifest com caminho-base correto", () => {
  const html = readFileSync(path.resolve(__dirname, "../index.html"), "utf-8");

  it("usa o placeholder %BASE_URL% do Vite para favicons (não um caminho absoluto fixo)", () => {
    expect(html).toContain('href="%BASE_URL%brand/favicon-16.png"');
    expect(html).toContain('href="%BASE_URL%brand/favicon-32.png"');
    expect(html).toContain('href="%BASE_URL%brand/favicon-48.png"');
    expect(html).toContain('href="%BASE_URL%brand/apple-touch-icon-180.png"');
  });

  it("referencia o manifest.json também via %BASE_URL%", () => {
    expect(html).toContain('rel="manifest"');
    expect(html).toContain('href="%BASE_URL%manifest.json"');
  });

  it("não contém nenhum caminho absoluto hardcoded para os assets de marca (ex.: /brand/...)", () => {
    expect(html).not.toMatch(/href="\/brand\//);
  });
});

describe("manifest.json (PWA) usa caminhos relativos para os ícones", () => {
  const manifest = JSON.parse(
    readFileSync(path.resolve(__dirname, "../public/manifest.json"), "utf-8"),
  ) as { icons: Array<{ src: string }> };

  it("nenhum ícone usa caminho absoluto (começando com '/') -- deve resolver relativamente ao base path", () => {
    for (const icon of manifest.icons) {
      expect(icon.src.startsWith("/")).toBe(false);
    }
  });

  it("inclui os dois tamanhos de ícone PWA esperados (192 e 512)", () => {
    const srcs = manifest.icons.map((icon) => icon.src);
    expect(srcs).toContain("brand/pwa-icon-192.png");
    expect(srcs).toContain("brand/pwa-icon-512.png");
  });
});
