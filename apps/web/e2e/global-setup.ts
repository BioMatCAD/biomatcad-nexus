import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Roda o script Python de seed (apps/api/scripts/seed_e2e_user.py) antes da suíte E2E --
// cria/reaproveita um usuário determinístico e um job 'succeeded' pré-semeado (via
// FakeWorkerClient rotulado, ver docstring do script) para a verificação do visualizador/
// download não depender do PicoGK real (que é o próprio objeto do bloqueio parcial deste
// incremento).
//
// Este arquivo é carregado pelo Playwright como um módulo ES (ver "type": "module" em
// package.json). Em módulos ES não existem as variáveis globais de CommonJS `__dirname` /
// `__filename` -- usar `__dirname` diretamente aqui falha em runtime com
// "ReferenceError: __dirname is not defined", como reportado por execução real no Windows. A
// forma correta e multiplataforma de obter o diretório do módulo atual em ESM é via
// import.meta.url + fileURLToPath (funciona identicamente em Linux/macOS/Windows; parsear a
// string de import.meta.url manualmente quebraria no Windows por causa do prefixo
// "file:///C:/...").
export function currentModuleDir(moduleUrl: string): string {
  return path.dirname(fileURLToPath(moduleUrl));
}

const currentDir = currentModuleDir(import.meta.url);

export class MissingE2EPythonBinError extends Error {
  constructor(invalidPath?: string) {
    super(
      invalidPath
        ? `E2E_PYTHON_BIN aponta para um caminho que não existe: '${invalidPath}'. Defina ` +
          "E2E_PYTHON_BIN com o caminho real do interprete do virtualenv do backend " +
          "(ex.: apps/api/.venv/Scripts/python.exe no Windows, apps/api/.venv/bin/python em " +
          "Linux/macOS)."
        : "E2E_PYTHON_BIN não foi definida. O E2E Playwright depende de bibliotecas do " +
          "backend (psycopg, sqlalchemy, etc.) instaladas apenas no virtualenv do projeto -- " +
          "um 'python'/'python3' genérico do PATH do sistema quase certamente NÃO as tem " +
          "(bug real observado na validação Windows de 2026-08-06: " +
          "'ModuleNotFoundError: No module named psycopg' ao cair silenciosamente para o " +
          "Python global). Defina E2E_PYTHON_BIN explicitamente antes de rodar " +
          "'npm run test:e2e', apontando para o interpretador do venv -- por exemplo " +
          "(Windows): apps\\api\\.venv\\Scripts\\python.exe " +
          "(Linux/macOS): apps/api/.venv/bin/python"
    );
    this.name = "MissingE2EPythonBinError";
  }
}

// Seleção do interpretador Python -- correção real (rodada Voronoi, auditoria da execução
// Windows 20260806-112714): a versão anterior desta função caía silenciosamente para
// "python"/"python3" do PATH do sistema quando E2E_PYTHON_BIN não estava definida -- na prática
// isso executou o Python GLOBAL do Windows (sem as dependências do backend instaladas),
// causando "ModuleNotFoundError: No module named 'psycopg'" bem no meio do seed do E2E. Um
// interpretador genérico do PATH nunca é garantidamente o mesmo ambiente do virtualenv do
// projeto -- por isso E2E_PYTHON_BIN agora é OBRIGATÓRIA, com uma mensagem de erro clara e
// acionável em vez de uma falha tardia e confusa dentro de um subprocesso.
export function resolvePythonBin(
  env: NodeJS.ProcessEnv = process.env,
  existsSync: (p: string) => boolean = fs.existsSync
): string {
  const bin = env.E2E_PYTHON_BIN;
  if (!bin) {
    throw new MissingE2EPythonBinError();
  }
  if (!existsSync(bin)) {
    throw new MissingE2EPythonBinError(bin);
  }
  return bin;
}

export default async function globalSetup(): Promise<void> {
  const apiDir = path.resolve(currentDir, "../../api");
  const pythonBin = resolvePythonBin();
  try {
    const output = execFileSync(pythonBin, ["scripts/seed_e2e_user.py"], {
      cwd: apiDir,
      env: process.env,
      encoding: "utf-8",
    });
    console.log("[e2e global-setup] seed:", output.trim());
  } catch (err) {
    console.error("[e2e global-setup] Falha ao semear usuário/job E2E:", err);
    throw err;
  }

  // Adendo de Interface Científica Mínima (Incremento 2.3, Rodada 2, Fase R) --
  // scientific-data.spec.ts precisa de: (a) um usuário researcher e um usuário admin (para
  // provar que o painel PubChem só aparece para admin), e (b) entidades científicas/
  // observações/proveniência/conflito sintéticos já persistidos no Postgres real. Os dois
  // módulos abaixo já existem desde as Rodadas 1/2 (Fases E e C respectivamente) e já são
  // idempotentes (get-or-create, nunca duplicam nem tocam dado de outro usuário/organização) --
  // reaproveitados aqui em vez de inventar um terceiro script de seed científico exclusivo
  // para E2E. Nenhuma chamada de rede real (PubChem ou qualquer outra) acontece em nenhum dos
  // dois: são inserções diretas via SQLAlchemy.
  try {
    const seedUsersOutput = execFileSync(pythonBin, ["-m", "biomatcad_api.seed"], {
      cwd: apiDir,
      env: process.env,
      encoding: "utf-8",
    });
    console.log("[e2e global-setup] seed (usuários demo/admin):", seedUsersOutput.trim());

    const seedScientificOutput = execFileSync(pythonBin, ["-m", "biomatcad_api.seed_scientific_data"], {
      cwd: apiDir,
      env: process.env,
      encoding: "utf-8",
    });
    console.log("[e2e global-setup] seed científico:", seedScientificOutput.trim());
  } catch (err) {
    console.error("[e2e global-setup] Falha ao semear dados científicos sintéticos:", err);
    throw err;
  }
}
