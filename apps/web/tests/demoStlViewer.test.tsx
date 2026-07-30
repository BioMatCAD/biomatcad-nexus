import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { StlViewer } from "../src/components/viewer/StlViewer";
import { demoApiClient } from "../src/api/demoClient";

// Este arquivo cobre, especificamente, o cenário "demonstração sintética pré-computada do
// GitHub Pages" pedido na Seção 8 da auditoria do visualizador 3D: ele NÃO usa um buffer STL
// fabricado em memória (como os demais testes de StlViewer.test.tsx) -- ele lê os bytes REAIS
// de public/demo-assets/sample-scaffold-block-gyroid.stl do disco e os serve através de um
// fetch mockado, exercitando o mesmo caminho (demoApiClient -> artifactDownloadUrl ->
// StlViewer com verificação de checksum) que roda de verdade no build estático do GitHub
// Pages (import.meta.env.BASE_URL).
//
// Este teste também é a prova de regressão de um bug real encontrado nesta rodada: o
// demoClient.ts declarava sha256: "0".repeat(64) (placeholder) para o artefato STL de
// demonstração, mas o StlViewer agora verifica o checksum do lado do cliente contra o valor
// declarado pela API antes de aceitar os bytes -- um placeholder que nunca bate com o arquivo
// real faria a demonstração do GitHub Pages falhar SEMPRE com "checksum divergente" (nunca
// carregar o modelo sintético). Corrigido substituindo o placeholder pelo SHA-256 real do
// arquivo. Este teste teria falhado antes da correção.

vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class FakeWebGLRenderer {
    domElement: HTMLCanvasElement;
    localClippingEnabled = false;
    constructor() {
      this.domElement = document.createElement("canvas");
    }
    setSize() {
      /* no-op no ambiente de teste -- sem GPU real */
    }
    render() {
      /* no-op no ambiente de teste -- sem GPU real */
    }
    dispose() {
      /* no-op no ambiente de teste -- sem GPU real */
    }
  }
  return { ...actual, WebGLRenderer: FakeWebGLRenderer };
});

const REAL_DEMO_STL_PATH = resolve(
  __dirname,
  "../public/demo-assets/sample-scaffold-block-gyroid.stl",
);

function waitForJobToSucceed(jobId: string, timeoutMs = 5000): Promise<void> {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const check = async () => {
      const job = await demoApiClient.getJob(undefined as unknown as string, jobId);
      if (job.status === "succeeded") {
        resolve();
        return;
      }
      if (job.status === "failed" || job.status === "cancelled") {
        reject(new Error(`job demo terminou em status inesperado: ${job.status}`));
        return;
      }
      if (Date.now() - start > timeoutMs) {
        reject(new Error("timeout esperando job demo chegar a 'succeeded'"));
        return;
      }
      setTimeout(check, 100);
    };
    void check();
  });
}

describe("StlViewer -- demonstração sintética pré-computada do GitHub Pages (arquivo real do disco)", () => {
  it("carrega o STL sintético REAL de public/demo-assets via o fluxo completo do demoApiClient, com checksum batendo (sem geometria substituta, sem erro de checksum)", async () => {
    const realStlBytes = readFileSync(REAL_DEMO_STL_PATH);
    // ArrayBuffer "puro" (sem o offset/tamanho extra que o Buffer do Node pode carregar),
    // para simular fielmente o que um fetch de navegador devolveria.
    const realStlArrayBuffer = realStlBytes.buffer.slice(
      realStlBytes.byteOffset,
      realStlBytes.byteOffset + realStlBytes.byteLength,
    );

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "Content-Length": String(realStlArrayBuffer.byteLength) }),
        arrayBuffer: async () => realStlArrayBuffer,
      }),
    );

    // Fluxo real do cliente de demonstração: cria um design-run sintético, espera a simulação
    // queued -> running -> succeeded (setTimeout reais do demoClient), lê os artefatos
    // resultantes e resolve a URL de download exatamente como o JobDetailPage faz.
    const designRun = await demoApiClient.createDesignRun(undefined as unknown as string, {
      project_id: "demo-project-1",
      recipe_id: "demo-recipe-1",
      idempotency_key: `demo-stl-viewer-test-${Date.now()}`,
    });
    const jobId = designRun.latest_job.id;
    await waitForJobToSucceed(jobId);

    const artifacts = await demoApiClient.listJobArtifacts(undefined as unknown as string, jobId);
    const stlArtifact = artifacts.find((a) => a.kind === "stl");
    expect(stlArtifact).toBeDefined();
    expect(stlArtifact!.sha256).not.toBe("0".repeat(64)); // nunca mais um placeholder

    const artifactUrl = demoApiClient.artifactDownloadUrl(stlArtifact!.id);

    render(
      <StlViewer
        artifactUrl={artifactUrl}
        expectedSha256={stlArtifact!.sha256}
        declaredSizeBytes={stlArtifact!.size_bytes}
        demoLabel="Demonstração sintética -- não é o resultado de uma execução real"
      />,
    );

    // Deve chegar a "ready" com a contagem real de triângulos do arquivo (336, verificado via
    // leitura direta do header binário do STL), nunca a um estado de erro de checksum.
    const triangleInfo = await screen.findByTestId("viewer-triangle-count", {}, { timeout: 5000 });
    expect(triangleInfo).toHaveTextContent("336");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/checksum/i)).not.toBeInTheDocument();

    // Aviso de proveniência experimental e selo de demonstração devem estar visíveis juntos.
    expect(screen.getByTestId("viewer-experimental-warning")).toHaveTextContent(
      "Resultado computacional — não validado experimentalmente.",
    );
    expect(screen.getByTestId("viewer-demo-label")).toHaveTextContent(/demonstração sintética/i);

    vi.unstubAllGlobals();
  }, 10000);

  it("artifactDownloadUrl do demo respeita o BASE_URL do build (caminho relativo, nunca um caminho de servidor absoluto)", () => {
    const url = demoApiClient.artifactDownloadUrl("qualquer-id-de-artefato");
    expect(url).toContain("demo-assets/sample-scaffold-block-gyroid.stl");
    // Nunca deve vazar um caminho de sistema de arquivos do servidor (ex.: /tmp/, /var/,
    // C:\\, home do usuário) -- apenas um caminho relativo ao BASE_URL do build estático.
    expect(url).not.toMatch(/^\/(tmp|var|home)\//);
    expect(url).not.toMatch(/^[a-zA-Z]:\\/);
  });
});
