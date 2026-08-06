import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { MissingE2EPythonBinError, currentModuleDir, resolvePythonBin } from "../e2e/global-setup";

// Guarda de regressão para dois bugs reais reportados por execução no Windows:
// 1. "ReferenceError: __dirname is not defined" no global-setup.ts do E2E Playwright.
// 2. (rodada Voronoi, validação Windows 20260806-112714) resolvePythonBin caía
//    silenciosamente para "python" (o Python GLOBAL do Windows, sem as dependências do
//    backend) quando E2E_PYTHON_BIN não estava definida -- causou
//    "ModuleNotFoundError: No module named 'psycopg'" no meio do seed do E2E, porque o
//    Python global não tem o virtualenv do projeto instalado. Corrigido para EXIGIR
//    E2E_PYTHON_BIN explicitamente, com um erro claro e acionável em vez de uma falha tardia
//    e confusa dentro de um subprocesso.
//
// Ver e2e/global-setup.ts e apps/web/e2e/README.md para o relato completo.
//
// Nota: este arquivo fica em apps/web/tests/ (não em apps/web/e2e/) de propósito -- o vitest.
// config exclui explicitamente "e2e/**" da coleta, pois aquele diretório contém specs do
// Playwright (test.describe do @playwright/test), incompatíveis com o runner do vitest. Este
// teste importa o módulo de dentro de e2e/ normalmente; só o ARQUIVO DE TESTE precisa morar
// fora da pasta excluída.

describe("e2e/global-setup.ts -- resolvePythonBin (exige E2E_PYTHON_BIN explicitamente)", () => {
  it("usa E2E_PYTHON_BIN quando definida e o caminho existe", () => {
    const existsSync = (p: string) => p === "/custom/venv/bin/python";
    expect(resolvePythonBin({ E2E_PYTHON_BIN: "/custom/venv/bin/python" }, existsSync)).toBe(
      "/custom/venv/bin/python"
    );
  });

  it("lança MissingE2EPythonBinError quando E2E_PYTHON_BIN não está definida", () => {
    expect(() => resolvePythonBin({}, () => true)).toThrow(MissingE2EPythonBinError);
  });

  it("a mensagem de erro sem E2E_PYTHON_BIN é clara e acionável (menciona o venv, não apenas 'defina a variável')", () => {
    try {
      resolvePythonBin({}, () => true);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(MissingE2EPythonBinError);
      expect((err as Error).message).toContain("E2E_PYTHON_BIN");
      expect((err as Error).message).toContain(".venv");
      expect((err as Error).message).toContain("psycopg");
    }
  });

  it("lança MissingE2EPythonBinError quando E2E_PYTHON_BIN aponta para um caminho inexistente", () => {
    const existsSync = () => false;
    expect(() =>
      resolvePythonBin({ E2E_PYTHON_BIN: "/caminho/que/nao/existe/python" }, existsSync)
    ).toThrow(MissingE2EPythonBinError);
  });

  it("nunca cai silenciosamente para 'python'/'python3' do PATH do sistema", () => {
    // Regressão direta do bug real: antes desta correção, {} (env vazio) retornava "python"
    // (Windows) ou "python3" (Linux/macOS) sem lançar nada.
    expect(() => resolvePythonBin({}, () => true)).toThrow();
  });
});

describe("e2e/global-setup.ts -- currentModuleDir (substituto de __dirname compatível com ESM)", () => {
  it("resolve o diretório do próprio módulo a partir de import.meta.url, sem lançar", () => {
    const dir = currentModuleDir(import.meta.url);
    expect(dir).toBe(path.dirname(fileURLToPath(import.meta.url)));
    expect(path.isAbsolute(dir)).toBe(true);
  });
});

describe("e2e/global-setup.ts -- guarda textual contra regressão das incompatibilidades reais", () => {
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
    expect(source).toMatch(/fileURLToPath\(\s*moduleUrl\s*\)/);
    expect(source).toMatch(/currentModuleDir\(\s*import\.meta\.url\s*\)/);
  });

  it("exige E2E_PYTHON_BIN explicitamente -- nunca um fallback silencioso para 'python'/'python3'", () => {
    expect(source).toContain("E2E_PYTHON_BIN");
    expect(source).toContain("MissingE2EPythonBinError");
    // Guarda específica contra a regressão real desta rodada: um fallback incondicional tipo
    // `?? "python3"` ou `?? (platform === "win32" ? "python" : "python3")`.
    expect(source).not.toMatch(/\?\?\s*["']python3?["']/);
    expect(source).not.toMatch(/\?\?\s*\(\s*platform/);
  });
});
