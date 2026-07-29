import { execFileSync } from "node:child_process";
import path from "node:path";

// Roda o script Python de seed (apps/api/scripts/seed_e2e_user.py) antes da suíte E2E --
// cria/reaproveita um usuário determinístico e um job 'succeeded' pré-semeado (via
// FakeWorkerClient rotulado, ver docstring do script) para a verificação do visualizador/
// download não depender do PicoGK real (que é o próprio objeto do bloqueio parcial deste
// incremento).
export default async function globalSetup(): Promise<void> {
  const apiDir = path.resolve(__dirname, "../../api");
  const pythonBin = process.env.E2E_PYTHON_BIN ?? "python3";
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
