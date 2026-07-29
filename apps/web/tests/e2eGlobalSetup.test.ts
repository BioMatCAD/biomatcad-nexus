import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { currentModuleDir, resolvePythonBin } from "../e2e/global-setup";

// Guarda de regressão para o bug real reportado por execução no Windows:
// "ReferenceError: __dirname is not defined" no global-setup.ts do E2E Playwright, e a escolha
// hardcoded de "python3" (que não existe por padrão no PATH do Windows). Ver
// e2e/global-setup.ts e apps/web/e2e/README.md para o relato completo.
//
// Nota: este arquivo fica em apps/web/tests/ (não em apps/web/e2e/) de propósito -- o vitest.
// config exclui explicitamente "e2e/**" da coleta, pois aquele diretório contém specs do
// Playwright (test.describe do @playwright/test), incompatíveis com o runner do vitest. Este
// teste importa o módulo de dentro de e2e/ normalmente; só o ARQUIVO DE TESTE precisa morar
// fora da pasta excluída.

describe("e2e/global-setup.ts -- resolvePythonBin (seleção multiplataforma do interpretador Python)", () => {
  it("usa E2E_PYTHON_BIN quando definido, em qualquer plataforma", () => {
    expect(resolvePythonBin({ E2E_PYTHON_BIN: "/custom/venv/bin/python" }, "win32")).toBe(
      "/custom/venv/bin/python"
    );
    expect(resolvePythonBin({ E2E_PYTHON_BIN: "/custom/venv/bin/python" }, "linux")).toBe(
      "/custom/venv/bin/python"
    );
    expect(resolvePythonBin({ E2E_PYTHON_BIN: "/custom/venv/bin/python" }, "darwin")).toBe(
      "/custom/venv/bin/python"
    );
  });

  it("usa 'python' no Windows quando E2E_PYTHON_BIN não está definido", () => {
    expect(resolvePythonBin({}, "win32")).toBe("python");
  });

  it("usa 'python3' em Linux/macOS quando E2E_PYTHON_BIN não está definido", () => {
    expect(resolvePythonBin({}, "linux")).toBe("python3");
    expect(resolvePythonBin({}, "darwin")).toBe("python3");
  });

  it("nunca retorna 'python3' no Windows nem 'python' (sem override) fora do Windows", () => {
    expect(resolvePythonBin({}, "win32")).not.toBe("python3");
    expect(resolvePythonBin({}, "linux")).not.toBe("python");
    expect(resolvePythonBin({}, "darwin")).not.toBe("python");
  });
});

describe("e2e/global-setup.ts -- currentModuleDir (substituto de __dirname compatível com ESM)", () => {
  it("resolve o diretório do próprio módulo a partir de import.meta.url, sem lançar", () => {
    const dir = currentModuleDir(import.meta.url);
    expect(dir).toBe(path.dirname(fileURLToPath(import.meta.url)));
    expect(path.isAbsolute(dir)).toBe(true);
  });
});

describe("e2e/global-setup.ts -- guarda textual contra regressão das duas incompatibilidades reais", () => {
  const testFileDir = path.dirname(fileURLToPath(import.meta.url));
  const sourcePath = path.resolve(testFileDir, "../e2e/global-setup.ts");
  const source = fs.readFileSync(sourcePath, "utf-8");

  it("NÃO usa __dirname diretamente para resolver caminhos (ReferenceError real em ESM no Windows)", () => {
    // O único uso aceitável de "__dirname" neste arquivo é dentro de comentários que
    // documentam o próprio bug corrigido -- nunca como identificador executável (ex.:
    // "path.resolve(__dirname" ou "= __dirname").
    expect(source).not.toMatch(/path\.resolve\(\s*__dirname/);
    expect(source).not.toMatch(/[^"'`.\w]__dirname\s*[,)]/);
  });

  it("deriva o diretório atual via import.meta.url + fileURLToPath", () => {
    expect(source).toContain("fileURLToPath");
    expect(source).toContain("import.meta.url");
    // A chamada real, testável (currentModuleDir), deve invocar fileURLToPath sobre o
    // parâmetro recebido -- e o ponto de uso em produção deve passar import.meta.url a ela.
    expect(source).toMatch(/fileURLToPath\(\s*moduleUrl\s*\)/);
    expect(source).toMatch(/currentModuleDir\(\s*import\.meta\.url\s*\)/);
  });

  it("preserva E2E_PYTHON_BIN e diferencia win32 de outras plataformas para o binário Python", () => {
    expect(source).toContain("E2E_PYTHON_BIN");
    expect(source).toMatch(/platform\s*===\s*["']win32["']/);
    // Guarda específica contra a regressão anterior: um "python3" hardcoded sem condicional de
    // plataforma nem fallback para "python" no Windows.
    expect(source).not.toMatch(/\?\?\s*["']python3["']\s*[;,)]/);
  });
});
