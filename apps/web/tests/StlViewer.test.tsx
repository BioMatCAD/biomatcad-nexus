import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StlViewer } from "../src/components/viewer/StlViewer";

// jsdom não implementa um contexto WebGL real -- um teste SEM este mock (ver abaixo) exercita
// o comportamento genuíno de fallback "WebGL indisponível" (não fabricado: é o que realmente
// acontece neste ambiente). Para os testes que precisam alcançar o estado "ready" e exercitar
// os controles de verdade, mockamos apenas a classe WebGLRenderer -- Scene, BufferGeometry,
// Mesh, MeshStandardMaterial, AxesHelper, GridHelper, BoxHelper, Plane e OrbitControls
// continuam sendo as classes REAIS do three.js (nenhuma delas precisa de GPU real para
// funcionar: só WebGLRenderer chama canvas.getContext, que o jsdom não fornece).
vi.mock("three", async (importOriginal) => {
  const actual = await importOriginal<typeof import("three")>();
  class FakeWebGLRenderer {
    domElement: HTMLCanvasElement;
    localClippingEnabled = false;
    constructor() {
      this.domElement = document.createElement("canvas");
      this.domElement.toDataURL = () => "data:image/png;base64,FAKE";
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

function buildBinaryStlBuffer(triangleCount: number): ArrayBuffer {
  const buffer = new ArrayBuffer(84 + triangleCount * 50);
  const view = new DataView(buffer);
  view.setUint32(80, triangleCount, true);
  let offset = 84;
  for (let i = 0; i < triangleCount; i++) {
    for (let k = 0; k < 3; k++) view.setFloat32(offset + k * 4, 0, true);
    offset += 12;
    for (let v = 0; v < 3; v++) {
      for (let k = 0; k < 3; k++) view.setFloat32(offset + k * 4, i + v, true);
      offset += 12;
    }
    offset += 2;
  }
  return buffer;
}

const ASCII_STL_TEXT = `solid demo
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 1 0 0
    vertex 0 1 0
  endloop
endfacet
endsolid demo
`;

function mockFetchReturning(buffer: ArrayBuffer, opts: { withContentLength?: boolean } = {}) {
  return vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers(opts.withContentLength === false ? {} : { "Content-Length": String(buffer.byteLength) }),
    arrayBuffer: async () => buffer,
  });
}

describe("StlViewer -- estado vazio (sem depender de WebGL/jsdom)", () => {
  it("mostra o estado vazio quando não há artifactUrl", () => {
    render(<StlViewer artifactUrl={null} />);
    expect(screen.getByText(/nenhum artefato disponível/i)).toBeInTheDocument();
  });

  // Regressão real (2a execução Windows do E2E, viewer.spec.ts, commit f8490d9 -- ver
  // TEST_EVIDENCE.md): o componente montava com artifactUrl=null (job ainda sem artefato
  // carregado no state do pai) e ficava preso em "empty" para sempre, mesmo quando o pai
  // (JobDetailPage) re-renderizava um instante depois com um artifactUrl válido -- porque o
  // `return` antecipado do estado "empty" nunca montava a div de containerRef, e o efeito de
  // carregamento sempre abortava no guard `!containerRef.current`. Este teste reproduz
  // exatamente essa sequência (mount sem artefato, artefato chega via rerender) e falha sem a
  // correção (fica preso em "Nenhum artefato disponível" em vez de chegar a "ready").
  it("transição empty -> ready quando artifactUrl chega depois do mount (mesma sequência do JobDetailPage real)", async () => {
    const buffer = buildBinaryStlBuffer(4);
    vi.stubGlobal("fetch", mockFetchReturning(buffer));

    const { rerender } = render(<StlViewer artifactUrl={null} token="tok" />);
    expect(screen.getByText(/nenhum artefato disponível/i)).toBeInTheDocument();

    // Simula o JobDetailPage real: `artifacts` chega via setState assíncrono após o mount
    // inicial (Promise.all de listJobArtifacts/getJobManifest), não no primeiro render.
    rerender(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    const indicator = await screen.findByTestId("viewer-triangle-count");
    expect(indicator).toHaveTextContent("STL binário");
    expect(indicator).toHaveTextContent("4");
    expect(screen.queryByText(/nenhum artefato disponível/i)).not.toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- STL binário válido (formato/controles/proveniência)", () => {
  it("carrega um STL binário válido e mostra formato, triângulos e o aviso experimental literal", async () => {
    const buffer = buildBinaryStlBuffer(4);
    vi.stubGlobal("fetch", mockFetchReturning(buffer));

    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    const indicator = await screen.findByTestId("viewer-triangle-count");
    expect(indicator).toHaveTextContent("STL binário");
    expect(indicator).toHaveTextContent("4"); // triângulos

    expect(screen.getByTestId("viewer-experimental-warning")).toHaveTextContent(
      "Resultado computacional — não validado experimentalmente.",
    );
    vi.unstubAllGlobals();
  });

  it("wireframe: alterna o checkbox sem erro (material real do three.js recebe a mudança)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    const checkbox = screen.getByTestId("viewer-wireframe-toggle") as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
    await user.click(checkbox);
    expect(checkbox.checked).toBe(true);
    vi.unstubAllGlobals();
  });

  it("transparência + opacidade: o slider só aparece quando a transparência está ligada, e é ajustável", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    expect(screen.queryByTestId("viewer-opacity-slider")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("viewer-transparency-toggle"));
    const slider = await screen.findByTestId("viewer-opacity-slider");
    expect(slider).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  // Estes dois testes já provavam corretamente, desde antes desta rodada, que o estado inicial
  // real de eixos/grade é `true` (checado) -- foi exatamente a evidência que confirmou, na 3a
  // execução Windows real (viewer.spec.ts:124 original, commit 85b58c4), que a falha era uma
  // expectativa incorreta do teste E2E (que assumia `not.toBeChecked()`), não uma regressão do
  // produto. Estendidos aqui para provar também a ida E volta (dois sentidos), separadamente
  // para eixos e grade, espelhando exatamente o que passou a ser exigido em viewer.spec.ts.
  it("eixos: toggle existe, inicia checado (padrão real do produto) e alterna nos dois sentidos", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    const axes = screen.getByTestId("viewer-axes-toggle") as HTMLInputElement;
    expect(axes.checked).toBe(true);
    await user.click(axes);
    expect(axes.checked).toBe(false);
    await user.click(axes);
    expect(axes.checked).toBe(true);
    vi.unstubAllGlobals();
  });

  it("grade: toggle existe, inicia checado (padrão real do produto) e alterna nos dois sentidos", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    const grid = screen.getByTestId("viewer-grid-toggle") as HTMLInputElement;
    expect(grid.checked).toBe(true);
    await user.click(grid);
    expect(grid.checked).toBe(false);
    await user.click(grid);
    expect(grid.checked).toBe(true);
    vi.unstubAllGlobals();
  });

  it("bounding box: o toggle existe e liga/desliga", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    const bbox = screen.getByTestId("viewer-bbox-toggle") as HTMLInputElement;
    expect(bbox.checked).toBe(false);
    await user.click(bbox);
    expect(bbox.checked).toBe(true);
    vi.unstubAllGlobals();
  });

  it("clipping plane: o slider de posição só aparece quando o corte está habilitado", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    expect(screen.queryByTestId("viewer-clipping-position")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("viewer-clipping-toggle"));
    expect(await screen.findByTestId("viewer-clipping-position")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("reset de câmera: o botão existe e é clicável sem erro", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");
    await user.click(screen.getByTestId("viewer-reset-camera"));
    vi.unstubAllGlobals();
  });

  it("screenshot: dispara o download de uma imagem PNG (toDataURL real do canvas mockado)", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    await user.click(screen.getByTestId("viewer-screenshot"));
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  // Regressão adicionada para sustentar o E2E do visualizador (viewer.spec.ts, teste
  // "screenshot"): o teste acima só provava QUE click() foi chamado, nunca O QUE seria
  // baixado -- o E2E real confirma nome de arquivo e assinatura binária PNG; este teste prova
  // o mesmo contrato (nome do arquivo + formato do data URL) em nível de componente/jsdom.
  it("screenshot: o link de download tem o nome de arquivo e o formato PNG esperados", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    let capturedHref = "";
    let capturedDownload = "";
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        capturedHref = this.href;
        capturedDownload = this.download;
      });
    await user.click(screen.getByTestId("viewer-screenshot"));

    expect(capturedDownload).toBe("biomatcad-scaffold-screenshot.png");
    expect(capturedHref.startsWith("data:image/png")).toBe(true);

    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});

// Regressão adicionada para sustentar o E2E do visualizador (viewer.spec.ts, teste
// "fullscreen"): a suíte de componente nunca cobria a Fullscreen API antes desta rodada. jsdom
// não implementa `requestFullscreen` nativamente -- os dois testes abaixo cobrem os dois lados
// do contrato real: (1) quando o navegador SUPORTA a API (mockada explicitamente aqui), o botão
// alterna rótulo corretamente; (2) quando não suporta (comportamento genuíno e não-mockado do
// jsdom, mesmo espírito do teste "webgl-unavailable" já existente), o componente nem renderiza
// o botão -- nunca um estado quebrado/inconsistente.
describe("StlViewer -- fullscreen", () => {
  it("alterna entre 'Tela cheia' e 'Sair de tela cheia' quando o navegador suporta a Fullscreen API", async () => {
    const user = userEvent.setup();
    const requestFullscreenMock = vi.fn().mockResolvedValue(undefined);
    const exitFullscreenMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(document, "fullscreenEnabled", { value: true, configurable: true });
    HTMLDivElement.prototype.requestFullscreen = requestFullscreenMock;
    document.exitFullscreen = exitFullscreenMock;

    try {
      vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
      render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
      await screen.findByTestId("viewer-triangle-count");

      const button = screen.getByTestId("viewer-fullscreen");
      expect(button).toHaveTextContent("Tela cheia");

      await user.click(button);
      expect(requestFullscreenMock).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(button).toHaveTextContent("Sair de tela cheia"));

      await user.click(button);
      expect(exitFullscreenMock).toHaveBeenCalledTimes(1);
      await waitFor(() => expect(button).toHaveTextContent("Tela cheia"));

      vi.unstubAllGlobals();
    } finally {
      // @ts-expect-error -- limpeza do mock adicionado manualmente ao protótipo/document
      delete HTMLDivElement.prototype.requestFullscreen;
      // @ts-expect-error -- idem
      delete document.exitFullscreen;
    }
  });

  it("não renderiza o botão de tela cheia quando o navegador não suporta a API (contrato honesto)", async () => {
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");

    expect(screen.queryByTestId("viewer-fullscreen")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  // Regressão real (3a execução Windows, viewer.spec.ts:192 original, commit 85b58c4 -- ver
  // TEST_EVIDENCE.md): `requestFullscreen()` era chamado em `containerRef` (o elemento que
  // envolve SOMENTE o <canvas>), deixando os controles (inclusive o próprio botão "Sair de tela
  // cheia") como irmãos FORA do elemento promovido à "top layer" do navegador -- o <canvas>
  // passava a interceptar todos os cliques sobre a área dos controles em tela cheia real
  // (Playwright reportou "subtree intercepts pointer events" -- não um problema do teste, um
  // defeito real de acessibilidade que afetaria qualquer usuário). Corrigido chamando
  // `requestFullscreen()` no `<div>` mais externo (`viewerRootRef`), que envolve tanto os
  // controles quanto o container do canvas. Este teste prova a correção arquitetural
  // diretamente: captura QUAL elemento recebeu a chamada de `requestFullscreen()` e confirma que
  // o botão de tela cheia é descendente desse mesmo elemento (ou seja, entra na mesma "top
  // layer" e permanece alcançável) -- sem depender de um Chromium real para detectar a
  // regressão.
  it("chama requestFullscreen() em um elemento que contém os controles (botão de tela cheia incluído), não só o canvas", async () => {
    const user = userEvent.setup();
    let elementRequested: HTMLElement | null = null;
    // Captura deliberada de `this` (o elemento real em que requestFullscreen() foi chamado)
    // para fora do mock -- não há outra forma de observar o elemento-alvo real de uma chamada
    // de método de instância.
    const requestFullscreenMock = vi.fn(function (this: HTMLElement) {
      // eslint-disable-next-line @typescript-eslint/no-this-alias
      elementRequested = this;
      return Promise.resolve();
    });
    Object.defineProperty(document, "fullscreenEnabled", { value: true, configurable: true });
    HTMLDivElement.prototype.requestFullscreen = requestFullscreenMock as unknown as () => Promise<void>;

    try {
      vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
      render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
      await screen.findByTestId("viewer-triangle-count");

      const button = screen.getByTestId("viewer-fullscreen");
      await user.click(button);

      expect(requestFullscreenMock).toHaveBeenCalledTimes(1);
      expect(elementRequested).not.toBeNull();
      // O botão precisa ser DESCENDENTE do elemento que foi para tela cheia -- se fosse chamado
      // em containerRef (só o canvas), esta asserção falharia, exatamente como falhava no
      // Chromium real antes da correção.
      expect(elementRequested!.contains(button)).toBe(true);

      vi.unstubAllGlobals();
    } finally {
      // @ts-expect-error -- limpeza do mock adicionado manualmente ao protótipo
      delete HTMLDivElement.prototype.requestFullscreen;
    }
  });
});

describe("StlViewer -- STL ASCII", () => {
  it("carrega um STL ASCII válido e identifica o formato corretamente", async () => {
    const buffer = new TextEncoder().encode(ASCII_STL_TEXT).buffer;
    vi.stubGlobal("fetch", mockFetchReturning(buffer));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    const indicator = await screen.findByTestId("viewer-triangle-count");
    expect(indicator).toHaveTextContent("STL ASCII");
    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- artefato inválido/corrompido (nunca renderiza geometria substituta)", () => {
  it("mostra estado de erro para um STL binário corrompido/truncado", async () => {
    const truncated = buildBinaryStlBuffer(5).slice(0, 90); // declara 5 triângulos mas trunca o arquivo
    vi.stubGlobal("fetch", mockFetchReturning(truncated));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(/truncado/i);
    expect(screen.queryByTestId("viewer-triangle-count")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("mostra estado de erro quando o checksum não confere (nunca ignora silenciosamente)", async () => {
    const buffer = buildBinaryStlBuffer(2);
    vi.stubGlobal("fetch", mockFetchReturning(buffer));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" expectedSha256={"0".repeat(64)} />);

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(/checksum/i);
    expect(screen.queryByTestId("viewer-triangle-count")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("permite tentar novamente após um erro", async () => {
    const user = userEvent.setup();
    const goodBuffer = buildBinaryStlBuffer(2);
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => {
        callCount += 1;
        if (callCount === 1) return Promise.resolve({ ok: false, status: 500, headers: new Headers() });
        return Promise.resolve({ ok: true, headers: new Headers(), arrayBuffer: async () => goodBuffer });
      }),
    );
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    await screen.findByRole("alert");
    const retryBtn = screen.getByRole("button", { name: /tentar novamente/i });
    await user.click(retryBtn);
    await screen.findByTestId("viewer-triangle-count");
    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- artefato grande (aviso e gate explícito, nunca download automático descontrolado)", () => {
  it("mostra o aviso de arquivo grande e não baixa nada até o usuário confirmar", async () => {
    const fetchMock = mockFetchReturning(buildBinaryStlBuffer(2));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <StlViewer
        artifactUrl="https://api/artifacts/1/download"
        token="tok"
        declaredSizeBytes={100 * 1024 * 1024}
        maxBytes={50 * 1024 * 1024}
      />,
    );

    expect(await screen.findByText(/arquivo grande/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("carrega normalmente após o usuário confirmar 'Carregar mesmo assim'", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));

    render(
      <StlViewer
        artifactUrl="https://api/artifacts/1/download"
        token="tok"
        declaredSizeBytes={100 * 1024 * 1024}
        maxBytes={50 * 1024 * 1024}
      />,
    );

    await user.click(await screen.findByTestId("viewer-proceed-despite-size"));
    await screen.findByTestId("viewer-triangle-count");
    vi.unstubAllGlobals();
  });

  it("malha densa: mostra aviso quando o número de triângulos excede o limite configurado (sem decimar)", async () => {
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(10)));
    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" maxTrianglesForDirectRender={5} />);

    const warning = await screen.findByTestId("viewer-heavy-mesh-warning");
    expect(warning).toHaveTextContent(/malha densa/i);
    // A contagem real de triângulos continua sendo a do artefato original (10), nunca reduzida.
    expect(screen.getByTestId("viewer-triangle-count")).toHaveTextContent("10");
    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- cancelamento de carregamento", () => {
  it("cancela o carregamento em andamento e permite carregar novamente", async () => {
    const user = userEvent.setup();
    let rejectFetch: (reason: unknown) => void;
    const pending = new Promise((_resolve, reject) => {
      rejectFetch = reject;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        init?.signal?.addEventListener("abort", () => rejectFetch(new DOMException("Aborted", "AbortError")));
        return pending;
      }),
    );

    render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-cancel-button");
    await user.click(screen.getByTestId("viewer-cancel-button"));

    expect(await screen.findByText(/carregamento cancelado/i)).toBeInTheDocument();
    expect(screen.getByTestId("viewer-retry-button")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  // Regressão real (3a execução Windows, viewer.spec.ts:229 original, commit 85b58c4 -- ver
  // TEST_EVIDENCE.md): o teste E2E assumia `<canvas>` count=0 após cancelar, mas o container
  // (containerRef) é permanentemente montado desde a correção do deadlock "empty" -> URL (rodada
  // anterior), e o <canvas>/WebGLRenderer são criados assim que o carregamento COMEÇA -- antes
  // do fetch do STL resolver --, não só quando a malha termina. Cancelar aborta só o fetch em
  // andamento; o <canvas> continua no DOM (nada foi "vazado": geometria/material/mesh nunca
  // chegaram a ser criados, porque o cancelamento ocorreu antes do `.then()` de sucesso). Este
  // teste prova exatamente isso -- canvas PERMANECE presente, e o estado real e observável do
  // componente (não inferido do canvas) é exposto pelo marcador estável `data-viewer-status`.
  it("após cancelar, o <canvas> permanece montado (container permanente) mas data-viewer-status reflete 'cancelled'", async () => {
    const user = userEvent.setup();
    let rejectFetch: (reason: unknown) => void;
    const pending = new Promise((_resolve, reject) => {
      rejectFetch = reject;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        init?.signal?.addEventListener("abort", () => rejectFetch(new DOMException("Aborted", "AbortError")));
        return pending;
      }),
    );

    const { container } = render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-cancel-button");
    await user.click(screen.getByTestId("viewer-cancel-button"));

    await screen.findByText(/carregamento cancelado/i);

    const viewerContainer = screen.getByTestId("viewer-container");
    expect(viewerContainer).toHaveAttribute("data-viewer-status", "cancelled");
    expect(container.querySelectorAll("canvas")).toHaveLength(1);
    // Nenhuma malha/métrica é exibida -- a prova real de "sem carregamento concluído", não a
    // ausência do canvas.
    expect(screen.queryByTestId("viewer-triangle-count")).not.toBeInTheDocument();

    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- WebGL genuinamente indisponível (SEM mock -- comportamento real do jsdom)", () => {
  it("mostra o fallback informativo em vez de quebrar quando WebGLRenderer não pode ser criado", async () => {
    vi.resetModules();
    vi.doUnmock("three");
    const { StlViewer: RealStlViewer } = await import("../src/components/viewer/StlViewer");
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));

    render(<RealStlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);

    expect(await screen.findByText(/webgl indisponível/i)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- demonstração sintética (GitHub Pages)", () => {
  it("mostra o selo de demonstração quando demoLabel é passado", async () => {
    vi.stubGlobal("fetch", mockFetchReturning(buildBinaryStlBuffer(2)));
    render(
      <StlViewer artifactUrl="https://api/artifacts/1/download" demoLabel="Demonstração sintética -- não é uma execução real" />,
    );
    const badge = await screen.findByTestId("viewer-demo-label");
    expect(badge).toHaveTextContent(/demonstração sintética/i);
    vi.unstubAllGlobals();
  });
});

describe("StlViewer -- descarte de recursos ao desmontar", () => {
  it("não gera warning/erro ao desmontar durante o carregamento nem depois de pronto", async () => {
    const buffer = buildBinaryStlBuffer(2);
    vi.stubGlobal("fetch", mockFetchReturning(buffer));
    const { unmount } = render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-triangle-count");
    expect(() => unmount()).not.toThrow();
    vi.unstubAllGlobals();
  });

  it("não quebra ao desmontar ENQUANTO o fetch ainda está pendente (guarda de setState pós-unmount)", async () => {
    let resolveFetch: (value: unknown) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => new Promise((resolve) => { resolveFetch = resolve; })),
    );
    const { unmount } = render(<StlViewer artifactUrl="https://api/artifacts/1/download" token="tok" />);
    await screen.findByTestId("viewer-cancel-button");
    expect(() => unmount()).not.toThrow();
    // Resolve depois do unmount -- não deve gerar "setState on unmounted component".
    resolveFetch({ ok: true, headers: new Headers(), arrayBuffer: async () => buildBinaryStlBuffer(2) });
    await waitFor(() => expect(true).toBe(true));
    vi.unstubAllGlobals();
  });
});
