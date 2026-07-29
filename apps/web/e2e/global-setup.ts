import { execFileSync } from "node:child_process";
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

// Seleção do interpretador Python, multiplataforma e testável isoladamente:
// - E2E_PYTHON_BIN é sempre respeitado quando definido (permite qualquer override explícito,
//   inclusive um caminho completo para um venv específico).
// - No Windows, o instalador oficial do Python normalmente só registra o comando "python" (o
//   launcher py.exe/python.exe); "python3" tipicamente não existe no PATH do Windows.
// - Em Linux/macOS, "python3" é o nome convencional e mais confiável (muitas distros não têm
//   mais "python" sem sufixo).
export function resolvePythonBin(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform
): string {
  return env.E2E_PYTHON_BIN ?? (platform === "win32" ? "python" : "python3");
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
}
