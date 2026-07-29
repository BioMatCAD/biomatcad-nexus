import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { parseBinaryStl } from "../../lib/stlParser";
import { EmptyState } from "../feedback/EmptyState";
import { ErrorState } from "../feedback/ErrorState";
import { Loading } from "../feedback/Loading";

type ViewerStatus = "empty" | "loading" | "error" | "ready";

interface StlViewerProps {
  stlUrl?: string | null;
  fetchHeaders?: Record<string, string>;
  levelOfDetail?: string;
}

// Visualizador 3D real via Three.js direto (sem react-three-fiber) -- Incremento 2.1, item 6.
// Recursos exigidos: orbit/pan/zoom, wireframe, transparência, eixos, grade (escala),
// clipping plane, screenshot, indicador de nível de detalhe, tratamento de
// loading/falha/artefato indisponível.
export function StlViewer({ stlUrl, fetchHeaders, levelOfDetail }: StlViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const meshRef = useRef<THREE.Mesh | null>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const clipPlaneRef = useRef<THREE.Plane | null>(null);
  const axesHelperRef = useRef<THREE.AxesHelper | null>(null);
  const gridHelperRef = useRef<THREE.GridHelper | null>(null);

  const [status, setStatus] = useState<ViewerStatus>(stlUrl ? "loading" : "empty");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [triangleCount, setTriangleCount] = useState(0);
  const [wireframe, setWireframe] = useState(false);
  const [transparent, setTransparent] = useState(false);
  const [showAxes, setShowAxes] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [clippingEnabled, setClippingEnabled] = useState(false);
  const [clipPosition, setClipPosition] = useState(0);

  useEffect(() => {
    if (!stlUrl) {
      setStatus("empty");
      return;
    }
    if (!containerRef.current) return;

    setStatus("loading");
    setErrorMessage(null);

    const container = containerRef.current;
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf3f4f6);

    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 10000);
    camera.position.set(50, 50, 50);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(width, height);
    renderer.localClippingEnabled = true;
    rendererRef.current = renderer;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement); // orbit + pan + zoom
    controls.enableDamping = true;

    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(1, 1, 1);
    scene.add(dirLight);

    const axesHelper = new THREE.AxesHelper(50);
    axesHelper.visible = showAxes;
    axesHelperRef.current = axesHelper;
    scene.add(axesHelper);

    const gridHelper = new THREE.GridHelper(200, 20);
    gridHelper.visible = showGrid;
    gridHelperRef.current = gridHelper;
    scene.add(gridHelper);

    const clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 0);
    clipPlaneRef.current = clipPlane;

    let cancelled = false;
    let animationFrame: number;

    fetch(stlUrl, { headers: fetchHeaders })
      .then((resp) => {
        if (!resp.ok) throw new Error(`Falha ao baixar STL (status ${resp.status}).`);
        return resp.arrayBuffer();
      })
      .then((buffer) => {
        if (cancelled) return;
        const parsed = parseBinaryStl(buffer);

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.BufferAttribute(parsed.positions, 3));
        geometry.setAttribute("normal", new THREE.BufferAttribute(parsed.normals, 3));
        geometry.computeBoundingSphere();

        const material = new THREE.MeshStandardMaterial({
          color: 0x2b6f76, // azul-petróleo (paleta do projeto)
          side: THREE.DoubleSide,
          clippingPlanes: [],
        });
        materialRef.current = material;

        const mesh = new THREE.Mesh(geometry, material);
        meshRef.current = mesh;
        scene.add(mesh);

        const sphere = geometry.boundingSphere;
        if (sphere) {
          const distance = sphere.radius * 2.5;
          camera.position.set(distance, distance, distance);
          controls.target.copy(sphere.center);
          camera.lookAt(sphere.center);
        }

        setTriangleCount(parsed.triangleCount);
        setStatus("ready");

        const animate = () => {
          controls.update();
          renderer.render(scene, camera);
          animationFrame = requestAnimationFrame(animate);
        };
        animate();
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorMessage(err instanceof Error ? err.message : "Falha ao carregar o artefato STL.");
        setStatus("error");
      });

    return () => {
      cancelled = true;
      if (animationFrame) cancelAnimationFrame(animationFrame);
      controls.dispose();
      renderer.dispose();
      container.innerHTML = "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stlUrl]);

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
    if (!materialRef.current) return;
    materialRef.current.transparent = transparent;
    materialRef.current.opacity = transparent ? 0.4 : 1.0;
  }, [transparent]);

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

  if (status === "empty") {
    return <EmptyState title="Nenhum artefato disponível" description="Este job ainda não gerou um STL para visualização." />;
  }
  if (status === "loading") {
    return <Loading label="Carregando visualização 3D…" />;
  }
  if (status === "error") {
    return <ErrorState message={errorMessage ?? "Falha ao carregar o artefato."} />;
  }

  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", marginBottom: "var(--space-3)" }}>
        <label>
          <input type="checkbox" checked={wireframe} onChange={(e) => setWireframe(e.target.checked)} /> Wireframe
        </label>
        <label>
          <input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} /> Transparência
        </label>
        <label>
          <input
            type="checkbox"
            checked={showAxes}
            onChange={(e) => {
              setShowAxes(e.target.checked);
            }}
          />{" "}
          Eixos
        </label>
        <label>
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => {
              setShowGrid(e.target.checked);
            }}
          />{" "}
          Grade/escala
        </label>
        <label>
          <input type="checkbox" checked={clippingEnabled} onChange={(e) => setClippingEnabled(e.target.checked)} /> Plano de corte
        </label>
        {clippingEnabled && (
          <input
            type="range"
            min={-100}
            max={100}
            value={clipPosition}
            onChange={(e) => setClipPosition(Number(e.target.value))}
            aria-label="Posição do plano de corte"
          />
        )}
        <button type="button" onClick={handleScreenshot}>
          Screenshot
        </button>
      </div>
      <div
        ref={containerRef}
        style={{ width: "100%", height: 480, border: "1px solid var(--color-border)", borderRadius: "var(--radius-md)" }}
      />
      <p style={{ color: "var(--color-text-secondary)", fontSize: "0.875rem", marginTop: "var(--space-2)" }}>
        Nível de detalhe: {triangleCount.toLocaleString("pt-BR")} triângulos
        {levelOfDetail ? ` (${levelOfDetail})` : ""}
      </p>
    </div>
  );
}
