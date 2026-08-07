import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { parseStl } from "../../lib/stlParser";
import { fetchArtifactBuffer } from "../../lib/artifactDownload";
import { EmptyState } from "../feedback/EmptyState";
import { ErrorState } from "../feedback/ErrorState";
import { Loading } from "../feedback/Loading";

type ViewerStatus =
  | "empty"
  | "size-warning"
  | "loading"
  | "ready"
  | "error"
  | "cancelled"
  | "webgl-unavailable"
  | "context-lost";

const DEFAULT_MAX_BYTES = 50 * 1024 * 1024; // 50 MiB -- configurável via prop
const DEFAULT_MAX_TRIANGLES_DIRECT = 500_000; // acima disso, aviso de malha densa (sem decimar)

export interface StlViewerProps {
  /** URL de download do artefato (ex.: client.artifactDownloadUrl(id)). `null`/`undefined` = sem artefato. */
  artifactUrl?: string | null;
  /** Token Bearer para download autenticado. Omitir para assets públicos (ex.: demo do GitHub Pages). */
  token?: string | null;
  /** SHA-256 já conhecido do artefato (via API), verificado contra os bytes recebidos. */
  expectedSha256?: string | null;
  /** Tamanho declarado do artefato (Artifact.size_bytes), conhecido ANTES do download. */
  declaredSizeBytes?: number | null;
  /** Limite de bytes para carregamento direto sem confirmação explícita do usuário. */
  maxBytes?: number;
  /** Limite de triângulos acima do qual um aviso de "malha densa" é mostrado (sem decimar). */
  maxTrianglesForDirectRender?: number;
  levelOfDetail?: string;
  /** Quando presente, mostra um selo de demonstração sintética (uso no build do GitHub Pages). */
  demoLabel?: string;
}

// Visualizador 3D real via Three.js direto (sem react-three-fiber) -- Incremento 2.1, item 6;
// consolidado no Incremento 2.2 ("consolidar visualizador 3D", ver
// docs/architecture/viewer-3d-audit.md para a auditoria que motivou cada mudança desta rodada).
export function StlViewer({
  artifactUrl,
  token,
  expectedSha256,
  declaredSizeBytes,
  maxBytes = DEFAULT_MAX_BYTES,
  maxTrianglesForDirectRender = DEFAULT_MAX_TRIANGLES_DIRECT,
  levelOfDetail,
  demoLabel,
}: StlViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const meshRef = useRef<THREE.Mesh | null>(null);
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const clipPlaneRef = useRef<THREE.Plane | null>(null);
  const axesHelperRef = useRef<THREE.AxesHelper | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);
  const boxHelperRef = useRef<THREE.BoxHelper | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const initialCameraRef = useRef<{ position: THREE.Vector3; target: THREE.Vector3 } | null>(null);
  const isMountedRef = useRef(true);
  // Ref separada do containerRef (que só envolve o <canvas>) para o elemento que efetivamente
  // entra em tela cheia -- ver comentário completo acima de handleToggleFullscreen sobre o bug
  // real corrigido nesta rodada (controles inacessíveis dentro do modo tela cheia).
  const viewerRootRef = useRef<HTMLDivElement | null>(null);

  const [status, setStatus] = useState<ViewerStatus>(
    !artifactUrl ? "empty" : declaredSizeBytes && declaredSizeBytes > maxBytes ? "size-warning" : "loading",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [triangleCount, setTriangleCount] = useState(0);
  const [uniqueVertexCount, setUniqueVertexCount] = useState(0);
  const [stlFormat, setStlFormat] = useState<"binary" | "ascii" | null>(null);
  const [loadToken, setLoadToken] = useState(0); // incrementado para forçar recarregar após "size-warning" ou retry

  const [wireframe, setWireframe] = useState(false);
  const [transparent, setTransparent] = useState(false);
  const [opacity, setOpacity] = useState(40);
  const [showAxes, setShowAxes] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showBoundingBox, setShowBoundingBox] = useState(false);
  const [clippingEnabled, setClippingEnabled] = useState(false);
  const [clipPosition, setClipPosition] = useState(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Reage a mudanças externas de artifactUrl (novo job/artefato): decide se carrega direto ou
  // se precisa do gate de confirmação por tamanho. IMPORTANTE: este efeito NUNCA inclui `status`
  // em suas dependências, e o efeito de carregamento abaixo depende só de [artifactUrl,
  // loadToken] -- nunca de `status` -- porque um bug real foi encontrado nos testes desta
  // rodada: quando o efeito de carregamento dependia de `status === "loading"`, o próprio
  // `setStatus("ready")` (chamado por ELE MESMO ao terminar) mudava essa dependência de
  // true->false, disparando a limpeza do efeito (dispose do renderer, refs zeradas a null)
  // logo em seguida à conclusão do carregamento -- o botão de screenshot (e qualquer outro
  // controle) parava de funcionar silenciosamente porque `rendererRef.current` já era `null`.
  useEffect(() => {
    if (!artifactUrl) {
      setStatus("empty");
      return;
    }
    if (declaredSizeBytes && declaredSizeBytes > maxBytes) {
      setStatus("size-warning");
      return;
    }
    setLoadToken((v) => v + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactUrl]);

  const handleProceedDespiteSize = () => {
    setLoadToken((v) => v + 1);
  };

  const handleCancelLoad = () => {
    abortControllerRef.current?.abort();
  };

  const handleRetry = () => {
    if (!artifactUrl) return;
    setErrorMessage(null);
    setLoadToken((v) => v + 1);
  };

  useEffect(() => {
    if (loadToken === 0 || !artifactUrl || !containerRef.current) return;
    setStatus("loading");

    const container = containerRef.current;
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch {
      if (isMountedRef.current) setStatus("webgl-unavailable");
      return;
    }
    renderer.setSize(width, height);
    renderer.localClippingEnabled = true;
    rendererRef.current = renderer;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f4f6);
    sceneRef.current = scene;

    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 10000);
    camera.position.set(50, 50, 50);
    cameraRef.current = camera;

    const controls = new OrbitControls(camera, renderer.domElement); // orbit + pan + zoom
    controls.enableDamping = true;
    controlsRef.current = controls;

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(1, 1, 1);
    scene.add(dirLight);

    const axesHelper = new THREE.AxesHelper(50);
    axesHelper.visible = showAxes;
    axesHelperRef.current = axesHelper;
    scene.add(axesHelper);

    const gridHelper = new THREE.GridHelper(200, 20); // 200mm totais / 20 divisões = 10mm por divisão
    gridHelper.visible = showGrid;
    gridHelperRef.current = gridHelper;
    scene.add(gridHelper);

    const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
    clipPlaneRef.current = clipPlane;

    const handleContextLost = (event: Event) => {
      event.preventDefault();
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      if (isMountedRef.current) setStatus("context-lost");
    };
    const handleContextRestored = () => {
      // O buffer já foi parseado e a geometria/material ainda existem em memória -- não é
      // necessário rebaixar de novo; apenas retoma o loop de renderização.
      if (isMountedRef.current) setStatus("ready");
      animate();
    };
    renderer.domElement.addEventListener("webglcontextlost", handleContextLost, false);
    renderer.domElement.addEventListener("webglcontextrestored", handleContextRestored, false);

    // ResizeObserver pode não existir em todo ambiente (ex.: jsdom em testes, embarcadores
    // antigos) -- degrada de forma graciosa em vez de quebrar o carregamento inteiro do
    // visualizador; a responsividade via observer é um extra, não um requisito de carregamento.
    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => {
        if (!containerRef.current || !cameraRef.current || !rendererRef.current) return;
        const w = containerRef.current.clientWidth || width;
        const h = containerRef.current.clientHeight || height;
        cameraRef.current.aspect = w / h;
        cameraRef.current.updateProjectionMatrix();
        rendererRef.current.setSize(w, h);
      });
      resizeObserver.observe(container);
      resizeObserverRef.current = resizeObserver;
    }

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    let animationFrame: number;
    function animate() {
      controls.update();
      renderer.render(scene, camera);
      animationFrame = requestAnimationFrame(animate);
      animationFrameRef.current = animationFrame;
    }

    fetchArtifactBuffer(artifactUrl, {
      token: token ?? undefined,
      signal: abortController.signal,
      maxBytes,
      expectedSha256: expectedSha256 ?? undefined,
    })
      .then(({ buffer }) => {
        if (!isMountedRef.current) return;
        const parsed = parseStl(buffer);

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(parsed.positions, 3));
        geometry.setAttribute("normal", new THREE.BufferAttribute(parsed.normals, 3));
        geometry.computeBoundingSphere();
        geometryRef.current = geometry;

        const material = new THREE.MeshStandardMaterial({
          color: 0x2b6f76, // azul-petróleo (paleta do projeto)
          side: THREE.DoubleSide,
          clippingPlanes: [],
        });
        materialRef.current = material;

        const mesh = new THREE.Mesh(geometry, material);
        meshRef.current = mesh;
        scene.add(mesh);

        const boxHelper = new THREE.BoxHelper(mesh, 0xff6600);
        boxHelper.visible = showBoundingBox;
        boxHelperRef.current = boxHelper;
        scene.add(boxHelper);

        const sphere = geometry.boundingSphere;
        if (sphere) {
          const distance = sphere.radius * 2.5;
          camera.position.set(distance, distance, distance);
          controls.target.copy(sphere.center);
          camera.lookAt(sphere.center);
          initialCameraRef.current = { position: camera.position.clone(), target: sphere.center.clone() };
        }

        // Contagem de vértices únicos calculada localmente é apenas informativa sobre a malha
        // NÃO-indexada renderizada aqui (3 vértices por triângulo, sem deduplicação) -- é
        // deliberadamente diferente do `vertex_count_unique` calculado pelo worker (que
        // deduplica de verdade); os dois são exibidos separadamente no painel de proveniência
        // para nunca confundir um com o outro.
        setTriangleCount(parsed.triangleCount);
        setUniqueVertexCount(parsed.positions.length / 3);
        setStlFormat(parsed.format);
        setStatus("ready");
        animate();
      })
      .catch((err: unknown) => {
        if (!isMountedRef.current) return;
        if (err instanceof DOMException && err.name === "AbortError") {
          setStatus("cancelled");
          return;
        }
        // Todas as mensagens aqui são strings próprias, criadas por nós (parser/artifactDownload)
        // ou o texto fixo de status HTTP -- nunca expomos err.stack, só err.message.
        setErrorMessage(err instanceof Error ? err.message : "Falha ao carregar o artefato STL.");
        setStatus("error");
      });

    return () => {
      abortController.abort();
      if (animationFrameRef.current) cancelAnimationFrame(animationFrameRef.current);
      resizeObserver?.disconnect();
      renderer.domElement.removeEventListener("webglcontextlost", handleContextLost, false);
      renderer.domElement.removeEventListener("webglcontextrestored", handleContextRestored, false);
      controls.dispose();
      geometryRef.current?.dispose();
      materialRef.current?.dispose();
      axesHelperRef.current?.dispose();
      gridHelperRef.current?.dispose();
      boxHelperRef.current?.dispose();
      renderer.dispose();
      container.innerHTML = "";
      rendererRef.current = null;
      sceneRef.current = null;
      cameraRef.current = null;
      controlsRef.current = null;
      meshRef.current = null;
      geometryRef.current = null;
      materialRef.current = null;
      axesHelperRef.current = null;
      gridHelperRef.current = null;
      boxHelperRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifactUrl, loadToken]);

  useEffect(() => {
    if (materialRef.current) materialRef.current.wireframe = wireframe;
  }, [wireframe]);

  useEffect(() => {
    if (axesHelperRef.current) axesHelperRef.current.visible = showAxes;
  }, [showAxes]);

  useEffect(() => {
    if (gridHelperRef.current) gridHelperRef.current.visible = showGrid;
  }, [showGrid]);

  useEffect(() => {
    if (boxHelperRef.current) boxHelperRef.current.visible = showBoundingBox;
  }, [showBoundingBox]);

  useEffect(() => {
    if (!materialRef.current) return;
    materialRef.current.transparent = transparent;
    materialRef.current.opacity = transparent ? opacity / 100 : 1.0;
  }, [transparent, opacity]);

  useEffect(() => {
    if (!materialRef.current || !clipPlaneRef.current) return;
    clipPlaneRef.current.constant = clipPosition;
    materialRef.current.clippingPlanes = clippingEnabled ? [clipPlaneRef.current] : [];
  }, [clippingEnabled, clipPosition]);

  const handleScreenshot = () => {
    if (!rendererRef.current) return;
    const dataUrl = rendererRef.current.domElement.toDataURL("image/png");
    const link = document.createElement("a");
    link.href = dataUrl;
    link.download = "biomatcad-scaffold-screenshot.png";
    link.click();
  };

  const handleResetCamera = () => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const initial = initialCameraRef.current;
    if (!camera || !controls || !initial) return;
    camera.position.copy(initial.position);
    controls.target.copy(initial.target);
    camera.lookAt(initial.target);
  };

  const [isFullscreen, setIsFullscreen] = useState(false);
  // Bug real encontrado na 3a execucao Windows real (viewer.spec.ts:192, commit 85b58c4, ver
  // TEST_EVIDENCE.md): `requestFullscreen()` era chamado em `containerRef.current` -- o elemento
  // que envolve SOMENTE o <canvas>, sem os controles (wireframe/eixos/grade/.../o proprio botao
  // de tela cheia), que ficam FORA dele como irmaos no DOM. A API de Fullscreen promove o
  // elemento (e so ele + seus descendentes) para a "top layer" do navegador, renderizada acima
  // de todo o resto do documento -- os controles, por serem irmaos e nao descendentes,
  // continuavam no fluxo normal por baixo dessa camada. Resultado real (nao so no Playwright):
  // ao entrar em tela cheia, o <canvas> passava a interceptar TODOS os eventos de ponteiro sobre
  // a area onde os controles apareceriam, inclusive o proprio botao "Sair de tela cheia" --
  // qualquer usuario real do Chrome ficaria com os controles inacessiveis dentro do modo tela
  // cheia (Playwright reportou honestamente via "subtree intercepts pointer events", sem
  // precisar de click({force:true}), que so esconderia o defeito real). Corrigido chamando
  // `requestFullscreen()`/`exitFullscreen()` em `viewerRootRef` (o `<div>` mais externo, que
  // envolve tanto os controles quanto o container do canvas) -- assim os controles entram na
  // mesma "top layer" que o canvas, permanecendo clicaveis (nao se sobrepoem espacialmente: os
  // controles ficam em uma linha acima do canvas no fluxo normal do documento, sem necessidade
  // de z-index/position manual).
  const fullscreenSupported = typeof document !== "undefined" && Boolean(document.fullscreenEnabled ?? true) && Boolean(viewerRootRef.current?.requestFullscreen);
  const handleToggleFullscreen = () => {
    if (!viewerRootRef.current) return;
    if (!isFullscreen) {
      viewerRootRef.current.requestFullscreen?.().then(() => setIsFullscreen(true)).catch(() => undefined);
    } else {
      document.exitFullscreen?.().then(() => setIsFullscreen(false)).catch(() => undefined);
    }
  };

  const isHeavyMesh = triangleCount > maxTrianglesForDirectRender;

  // "empty" e "size-warning" PRECISAM continuar montando a div do container mais abaixo (mesmo
  // padrão do bug corrigido para "loading"): um bug real foi encontrado na 2a execução Windows
  // real deste E2E (viewer.spec.ts, commit f8490d9, ver TEST_EVIDENCE.md) -- "empty" ainda tinha
  // um `return` antecipado (igual ao que já havia sido corrigido para "loading"), o que impedia a
  // div de containerRef de existir enquanto o job ainda não tinha artefato carregado (mount
  // inicial, artifactUrl=null). Quando o artefato chegava um instante depois (JobDetailPage
  // primeiro renderiza com `artifacts=[]` e só popula via setArtifacts após um round-trip HTTP
  // assíncrono), o efeito que reage a `[artifactUrl]` disparava corretamente e incrementava
  // `loadToken`, mas o efeito de carregamento abortava sempre no guard `!containerRef.current`,
  // porque a div nunca tinha sido montada (o componente ainda retornava só o EmptyState) --
  // deadlock permanente: preso em "empty" para sempre, mesmo com artefato válido. Corrigido
  // removendo o `return` antecipado de "empty" também, mantendo a div sempre presente e usando
  // overlays condicionais, como já era feito para "size-warning"/"loading". Coberto por teste de
  // regressão em StlViewer.test.tsx ("transição empty -> ready quando artifactUrl chega depois
  // do mount").

  // IMPORTANTE: a partir daqui (empty/size-warning/loading/ready/error/cancelled/
  // webgl-unavailable/context-lost), a div referenciada por containerRef precisa continuar
  // montada em TODOS esses estados -- o efeito de carregamento só consegue anexar o
  // WebGLRenderer a ela se `containerRef.current` já existir no momento em que o efeito roda
  // (logo após o commit deste render).
  return (
    <div ref={viewerRootRef}>
      {status === "empty" && (
        <EmptyState title="Nenhum artefato disponível" description="Este job ainda não gerou um STL para visualização." />
      )}

      {status === "size-warning" && (() => {
        const mb = ((declaredSizeBytes ?? 0) / (1024 * 1024)).toFixed(1);
        const limitMb = (maxBytes / (1024 * 1024)).toFixed(0);
        return (
          <EmptyState
            title={`Arquivo grande (${mb} MB)`}
            description={`Este artefato excede o limite padrão de carregamento direto (${limitMb} MB). Carregar mesmo assim pode consumir bastante memória do navegador.`}
          >
            <button type="button" data-testid="viewer-proceed-despite-size" onClick={handleProceedDespiteSize}>
              Carregar mesmo assim
            </button>
          </EmptyState>
        );
      })()}

      {status === "loading" && (
        <div>
          <Loading label="Carregando visualização 3D…" />
          <button type="button" data-testid="viewer-cancel-button" onClick={handleCancelLoad}>
            Cancelar
          </button>
        </div>
      )}

      {status === "cancelled" && (
        <EmptyState title="Carregamento cancelado" description="O carregamento do artefato foi cancelado.">
          <button type="button" data-testid="viewer-retry-button" onClick={handleRetry}>
            Carregar novamente
          </button>
        </EmptyState>
      )}

      {status === "webgl-unavailable" && (
        <EmptyState
          title="WebGL indisponível"
          description="Este navegador/ambiente não conseguiu criar um contexto WebGL. Não é possível exibir a visualização 3D aqui -- os artefatos continuam disponíveis para download."
        />
      )}

      {status === "context-lost" && (
        <EmptyState title="Contexto WebGL perdido" description="O navegador liberou os recursos gráficos (comum sob pressão de memória). Recarregue a página para retomar a visualização." />
      )}

      {status === "error" && <ErrorState message={errorMessage ?? "Falha ao carregar o artefato."} onRetry={handleRetry} />}

      {status === "ready" && (
        <>
          {demoLabel && (
            <p data-testid="viewer-demo-label" style={{ ...styles.badge, background: "var(--color-accent)", color: "white" }}>
              {demoLabel}
            </p>
          )}
          <p data-testid="viewer-experimental-warning" style={styles.experimentalWarning}>
            Resultado computacional — não validado experimentalmente.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
            <label>
              <input
                type="checkbox"
                data-testid="viewer-wireframe-toggle"
                checked={wireframe}
                onChange={(e) => setWireframe(e.target.checked)}
              />{" "}
              Wireframe
            </label>
            <label>
              <input
                type="checkbox"
                data-testid="viewer-transparency-toggle"
                checked={transparent}
                onChange={(e) => setTransparent(e.target.checked)}
              />{" "}
              Transparência
            </label>
            {transparent && (
              <input
                type="range"
                min={5}
                max={100}
                value={opacity}
                data-testid="viewer-opacity-slider"
                aria-label="Opacidade"
                onChange={(e) => setOpacity(Number(e.target.value))}
              />
            )}
            <label>
              <input type="checkbox" data-testid="viewer-axes-toggle" checked={showAxes} onChange={(e) => setShowAxes(e.target.checked)} /> Eixos
            </label>
            <label>
              <input type="checkbox" data-testid="viewer-grid-toggle" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Grade
              (10 mm/divisão)
            </label>
            <label>
              <input
                type="checkbox"
                data-testid="viewer-bbox-toggle"
                checked={showBoundingBox}
                onChange={(e) => setShowBoundingBox(e.target.checked)}
              />{" "}
              Bounding box
            </label>
            <label>
              <input
                type="checkbox"
                data-testid="viewer-clipping-toggle"
                checked={clippingEnabled}
                onChange={(e) => setClippingEnabled(e.target.checked)}
              />{" "}
              Plano de corte
            </label>
            {clippingEnabled && (
              <input
                type="range"
                min={-100}
                max={100}
                value={clipPosition}
                data-testid="viewer-clipping-position"
                onChange={(e) => setClipPosition(Number(e.target.value))}
                aria-label="Posição do plano de corte"
              />
            )}
            <button type="button" data-testid="viewer-reset-camera" onClick={handleResetCamera}>
              Reset câmera
            </button>
            <button type="button" data-testid="viewer-screenshot" onClick={handleScreenshot}>
              Screenshot
            </button>
            {fullscreenSupported && (
              <button type="button" data-testid="viewer-fullscreen" onClick={handleToggleFullscreen}>
                {isFullscreen ? "Sair de tela cheia" : "Tela cheia"}
              </button>
            )}
          </div>
        </>
      )}

      {/* data-viewer-status expõe o estado interno da máquina de estados (nunca dados
          sensíveis -- só um dos valores do enum ViewerStatus) como um marcador estável e
          observável, independente da presença do <canvas>. Necessário desde que o container
          abaixo passou a ficar permanentemente montado (ver comentário grande acima sobre o
          bug do deadlock "empty" -> URL, corrigido em rodada anterior): um teste que dependesse
          de `<canvas>` count para inferir o estado (ex.: "cancelado" = canvas ausente) deixou de
          ser válido, porque o <canvas> É criado assim que o carregamento começa (antes mesmo do
          fetch do STL resolver -- ver efeito acima), não só quando a malha termina de carregar,
          e permanece montado mesmo após um cancelamento (só o fetch em andamento é abortado, não
          o WebGLRenderer/cena base, que só são descartados no cleanup do efeito quando
          `[artifactUrl, loadToken]` muda de novo -- outra tentativa/retry -- ou no unmount). Bug
          real encontrado na 3a execução Windows real (viewer.spec.ts:229, commit 85b58c4, ver
          TEST_EVIDENCE.md): o teste de cancelamento assumia canvas count=0 após cancelar, o que
          nunca foi verdade desde a correção do deadlock -- corrigido usando este marcador em vez
          de inferir do <canvas>. */}
      <div
        ref={containerRef}
        data-testid="viewer-container"
        data-viewer-status={status}
        style={{
          width: "100%",
          height: 480,
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-md)",
          display: status === "ready" ? "block" : "none",
        }}
      />

      {status === "ready" && (
        <>
          <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem", marginTop: "var(--space-2)" }} data-testid="viewer-triangle-count">
            Formato: {stlFormat === "ascii" ? "STL ASCII" : "STL binário"} · {triangleCount.toLocaleString("pt-BR")} triângulos ·{" "}
            {uniqueVertexCount.toLocaleString("pt-BR")} vértices (malha renderizada, não-indexada)
            {levelOfDetail ? ` · nível de detalhe: ${levelOfDetail}` : ""}
          </p>
          {isHeavyMesh && (
            <p data-testid="viewer-heavy-mesh-warning" style={styles.warning}>
              Malha densa ({triangleCount.toLocaleString("pt-BR")} triângulos) -- a renderização pode
              ficar lenta. Nenhuma simplificação/decimação é aplicada automaticamente (o artefato
              original é sempre preservado; ver documentação do visualizador).
            </p>
          )}
        </>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  badge: {
    display: "inline-block",
    padding: "2px 10px",
    borderRadius: "var(--radius-sm)",
    fontSize: "0.75rem",
    fontWeight: 700,
    marginBottom: "var(--space-2)",
  },
  experimentalWarning: {
    fontSize: "0.8rem",
    fontWeight: 600,
    color: "var(--color-text-secondary)",
    marginTop: 0,
  },
  warning: {
    fontSize: "0.8rem",
    color: "var(--color-text-secondary)",
    background: "color-mix(in srgb, orange 12%, transparent)",
    border: "1px solid orange",
    borderRadius: "var(--radius-sm)",
    padding: "var(--space-2)",
  },
};
