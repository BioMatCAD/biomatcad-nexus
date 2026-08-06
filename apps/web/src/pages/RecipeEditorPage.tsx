import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { GeometryRecipeBody, RecipeValidateResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { useAuth } from "../context/AuthContext";
import { estimateComputeCost } from "../lib/computeCostEstimate";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const DEFAULT_GYROID_RECIPE: GeometryRecipeBody = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: { kind: "gyroid", cell_size_mm: 2, wall_thickness_mm: 0.4, isovalue: 0, target_porosity_pct: 60 },
  resolution: { voxel_size_mm: 0.2 },
  mode: "preview",
  seed: 1,
  compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
  output_formats: ["stl"],
};

// Receita padrão ao trocar para Voronoi -- parâmetros conservadores (mesma ordem de grandeza
// das golden recipes preview aprovadas em schemas/biomatcem/golden-recipes/), nunca inventados:
// site_count baixo, distribution uniform_random, strut_radius_mm/node_smoothing/
// node_radius_factor nos defaults documentados pelo schema.
const DEFAULT_VORONOI_RECIPE: GeometryRecipeBody = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: {
    kind: "voronoi_cell_edges_v1",
    site_count: 12,
    distribution: "uniform_random",
    strut_radius_mm: 0.4,
    node_smoothing: 0.5,
    node_radius_factor: 1.3,
    boundary_behavior: "clip",
    target_porosity_pct: 65,
  },
  resolution: { voxel_size_mm: 0.4 },
  mode: "preview",
  seed: 1,
  compute_limits: { max_duration_seconds: 30, max_memory_mb: 512, max_voxel_count: 200000 },
  output_formats: ["stl"],
};

const DEFAULT_RECIPE: GeometryRecipeBody = DEFAULT_GYROID_RECIPE;

const EMPTY_VALIDATION: RecipeValidateResponse = { valid: false, errors: [], checksum_sha256: null, schema_version: "1.0.0" };

// Espelha o registro real de providers de topologia (Incremento 2.2, Seção 4 -- ver
// apps/api/src/biomatcad_api/services/topology_providers.py e
// apps/geometry-worker/TopologyProviderRegistry.cs). Nunca invente um provider "implementado"
// aqui que não exista de verdade nos dois lados. Voronoi (voronoi_cell_edges_v1) passou a
// status="implemented" nos dois registros na rodada Voronoi (Incremento 2.2, Seção 8) --
// habilitado aqui apenas depois disso ser verdade, nunca antes.
const TOPOLOGY_PROVIDERS: Array<{ kind: "gyroid" | "voronoi_cell_edges_v1"; label: string; implemented: boolean }> = [
  { kind: "gyroid", label: "Gyroid (TPMS) -- implementado", implemented: true },
  { kind: "voronoi_cell_edges_v1", label: "Voronoi (voronoi_cell_edges_v1) -- implementado", implemented: true },
];

export function RecipeEditorPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { token } = useAuth();

  const [name, setName] = useState("Nova receita");
  const [recipe, setRecipe] = useState<GeometryRecipeBody>(DEFAULT_RECIPE);
  const [validation, setValidation] = useState<RecipeValidateResponse>(EMPTY_VALIDATION);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timeout = setTimeout(() => {
      client
        .validateRecipe(recipe)
        .then(setValidation)
        .catch(() => setValidation({ valid: false, errors: [], checksum_sha256: null, schema_version: "1.0.0" }));
    }, 300);
    return () => clearTimeout(timeout);
  }, [recipe]);

  const updateDomainShape = (shape: "block" | "cylinder") => {
    setRecipe((prev) => ({
      ...prev,
      domain:
        shape === "block"
          ? { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } }
          : { shape: "cylinder", dimensions_mm: { kind: "cylinder", radius_mm: 5, height_mm: 12 } },
    }));
  };

  // Troca de provider de topologia: reconstrói a receita inteira a partir de um default
  // conservador conhecido (nunca tenta "adaptar" campos de uma topologia para a outra --
  // gyroid e voronoi_cell_edges_v1 não compartilham nenhum campo de topology).
  const updateTopologyKind = (kind: "gyroid" | "voronoi_cell_edges_v1") => {
    setRecipe((prev) => {
      const base = kind === "gyroid" ? DEFAULT_GYROID_RECIPE : DEFAULT_VORONOI_RECIPE;
      return { ...base, domain: prev.domain, mode: prev.mode, seed: prev.seed };
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token || !projectId || !validation.valid) return;
    setSubmitting(true);
    try {
      const created = await client.createRecipe(token, projectId, name, recipe);
      navigate(`/app/recipes/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao criar receita.");
    } finally {
      setSubmitting(false);
    }
  };

  const costEstimate = estimateComputeCost(recipe);

  return (
    <AuthenticatedLayout>
      <h1>Editor de receita BioMatCEM</h1>
      {error && <ErrorState message={error} />}

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", maxWidth: 480 }}>
        <label>
          Nome da receita
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>

        <fieldset>
          <legend>Domínio</legend>
          <label>
            <input
              type="radio"
              name="shape"
              checked={recipe.domain.shape === "block"}
              onChange={() => updateDomainShape("block")}
            />{" "}
            Bloco
          </label>
          <label>
            <input
              type="radio"
              name="shape"
              checked={recipe.domain.shape === "cylinder"}
              onChange={() => updateDomainShape("cylinder")}
            />{" "}
            Cilindro
          </label>

          {recipe.domain.shape === "block" ? (
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <label>
                X (mm)
                <input
                  type="number"
                  value={recipe.domain.dimensions_mm.x_mm}
                  onChange={(e) =>
                    setRecipe((prev) =>
                      prev.domain.shape === "block"
                        ? { ...prev, domain: { ...prev.domain, dimensions_mm: { ...prev.domain.dimensions_mm, x_mm: Number(e.target.value) } } }
                        : prev,
                    )
                  }
                />
              </label>
              <label>
                Y (mm)
                <input
                  type="number"
                  value={recipe.domain.dimensions_mm.y_mm}
                  onChange={(e) =>
                    setRecipe((prev) =>
                      prev.domain.shape === "block"
                        ? { ...prev, domain: { ...prev.domain, dimensions_mm: { ...prev.domain.dimensions_mm, y_mm: Number(e.target.value) } } }
                        : prev,
                    )
                  }
                />
              </label>
              <label>
                Z (mm)
                <input
                  type="number"
                  value={recipe.domain.dimensions_mm.z_mm}
                  onChange={(e) =>
                    setRecipe((prev) =>
                      prev.domain.shape === "block"
                        ? { ...prev, domain: { ...prev.domain, dimensions_mm: { ...prev.domain.dimensions_mm, z_mm: Number(e.target.value) } } }
                        : prev,
                    )
                  }
                />
              </label>
            </div>
          ) : (
            <div style={{ display: "flex", gap: "var(--space-2)" }}>
              <label>
                Raio (mm)
                <input
                  type="number"
                  value={recipe.domain.dimensions_mm.radius_mm}
                  onChange={(e) =>
                    setRecipe((prev) =>
                      prev.domain.shape === "cylinder"
                        ? { ...prev, domain: { ...prev.domain, dimensions_mm: { ...prev.domain.dimensions_mm, radius_mm: Number(e.target.value) } } }
                        : prev,
                    )
                  }
                />
              </label>
              <label>
                Altura (mm)
                <input
                  type="number"
                  value={recipe.domain.dimensions_mm.height_mm}
                  onChange={(e) =>
                    setRecipe((prev) =>
                      prev.domain.shape === "cylinder"
                        ? { ...prev, domain: { ...prev.domain, dimensions_mm: { ...prev.domain.dimensions_mm, height_mm: Number(e.target.value) } } }
                        : prev,
                    )
                  }
                />
              </label>
            </div>
          )}
        </fieldset>

        <fieldset>
          <legend>Provider de topologia</legend>
          <label htmlFor="topology-provider-select">
            Topologia
            <select
              id="topology-provider-select"
              value={recipe.topology.kind}
              onChange={(e) => updateTopologyKind(e.target.value as "gyroid" | "voronoi_cell_edges_v1")}
            >
              {TOPOLOGY_PROVIDERS.map((p) => (
                <option key={p.kind} value={p.kind} disabled={!p.implemented}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <p style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
            Gyroid e Voronoi (voronoi_cell_edges_v1) estão implementados e testados nesta versão.
            Outras topologias exigem um novo provider registrado antes de ficarem selecionáveis --
            nunca uma opção decorativa sem execução real por trás.
          </p>
        </fieldset>

        {recipe.topology.kind === "gyroid" ? (
          <fieldset>
            <legend>Topologia (gyroid)</legend>
            <p style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
              Superfície mínima periódica (TPMS): F(x,y,z) = sin(x)cos(y) + sin(y)cos(z) + sin(z)cos(x).
              O sólido gerado é a banda em torno de <code>isovalue</code> cuja meia-largura é derivada de{" "}
              <code>wall_thickness_mm</code>.
            </p>
            <label>
              Tamanho da célula (mm)
              <input
                type="number"
                step="0.1"
                value={recipe.topology.cell_size_mm}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "gyroid"
                      ? { ...prev, topology: { ...prev.topology, cell_size_mm: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Espessura de parede (mm) -- obrigatório, único controlador de espessura
              <input
                type="number"
                step="0.05"
                value={recipe.topology.wall_thickness_mm}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "gyroid"
                      ? { ...prev, topology: { ...prev.topology, wall_thickness_mm: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Isovalor (centro da banda -- não controla espessura, default 0)
              <input
                type="number"
                step="0.1"
                value={recipe.topology.isovalue ?? 0}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "gyroid"
                      ? { ...prev, topology: { ...prev.topology, isovalue: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Porosidade-alvo (%)
              <input
                type="number"
                value={recipe.topology.target_porosity_pct ?? 60}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "gyroid"
                      ? { ...prev, topology: { ...prev.topology, target_porosity_pct: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
          </fieldset>
        ) : (
          <fieldset data-testid="voronoi-topology-fieldset">
            <legend>Topologia (Voronoi -- voronoi_cell_edges_v1)</legend>
            <p style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
              Sítios determinísticos (seed) → tetraedralização de Delaunay → circuncentros →
              arestas REAIS de células de Voronoi 3D (internas e raios de fronteira recortados
              pelo domínio) → struts implícitos (cilindro/cápsula) unidos por um blend suave nos
              nós. Não é um grafo de adjacência de sítios de Delaunay -- ver auditoria matemática
              em docs/architecture/voronoi-cell-edges-v1-math-audit.md.
            </p>
            <label>
              Número de sítios (site_count, 4..500)
              <input
                type="number"
                min={4}
                max={500}
                value={recipe.topology.site_count}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, site_count: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label htmlFor="voronoi-distribution-select">
              Distribuição dos sítios
              <select
                id="voronoi-distribution-select"
                value={recipe.topology.distribution}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, distribution: e.target.value as "uniform_random" | "jittered_grid" } }
                      : prev,
                  )
                }
              >
                <option value="uniform_random">Aleatória uniforme (com distância mínima entre sítios)</option>
                <option value="jittered_grid">Grade jitterada (determinística por célula)</option>
              </select>
            </label>
            <label>
              Raio do strut (strut_radius_mm, mm)
              <input
                type="number"
                step="0.01"
                min={0.02}
                max={3}
                value={recipe.topology.strut_radius_mm}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, strut_radius_mm: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Suavização dos nós (node_smoothing, 0..1 -- 0 = união dura, 1 = suavização máxima)
              <input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={recipe.topology.node_smoothing ?? 0.5}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, node_smoothing: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Fator de raio do nó (node_radius_factor, 1..3 -- raio do nó = strut_radius_mm × este fator)
              <input
                type="number"
                step="0.05"
                min={1}
                max={3}
                value={recipe.topology.node_radius_factor ?? 1.3}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, node_radius_factor: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
            <label htmlFor="voronoi-boundary-behavior-select">
              Comportamento de fronteira
              <select id="voronoi-boundary-behavior-select" value="clip" disabled>
                <option value="clip">Recorte pela SDF do domínio (clip) -- único suportado nesta rodada</option>
              </select>
            </label>
            <label>
              Distância mínima entre sítios (seed_site_min_separation_mm, opcional -- em branco = derivado automaticamente do domínio)
              <input
                type="number"
                step="0.1"
                min={0}
                max={50}
                value={recipe.topology.seed_site_min_separation_mm ?? ""}
                placeholder="auto"
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? {
                          ...prev,
                          topology: {
                            ...prev.topology,
                            seed_site_min_separation_mm: e.target.value === "" ? undefined : Number(e.target.value),
                          },
                        }
                      : prev,
                  )
                }
              />
            </label>
            <label>
              Porosidade-alvo (%, opcional)
              <input
                type="number"
                min={1}
                max={99}
                value={recipe.topology.target_porosity_pct ?? 60}
                onChange={(e) =>
                  setRecipe((prev) =>
                    prev.topology.kind === "voronoi_cell_edges_v1"
                      ? { ...prev, topology: { ...prev.topology, target_porosity_pct: Number(e.target.value) } }
                      : prev,
                  )
                }
              />
            </label>
          </fieldset>
        )}

        <label htmlFor="recipe-mode">
          Modo
          <select
            id="recipe-mode"
            value={recipe.mode}
            onChange={(e) => setRecipe((prev) => ({ ...prev, mode: e.target.value as "preview" | "final" }))}
          >
            <option value="preview">Preview</option>
            <option value="final">Final</option>
          </select>
        </label>

        <label>
          Seed
          <input
            type="number"
            value={recipe.seed}
            onChange={(e) => setRecipe((prev) => ({ ...prev, seed: Number(e.target.value) }))}
          />
        </label>

        <fieldset>
          <legend>Limites computacionais</legend>
          <label>
            Duração máx. (s)
            <input
              type="number"
              value={recipe.compute_limits.max_duration_seconds}
              onChange={(e) =>
                setRecipe((prev) => ({ ...prev, compute_limits: { ...prev.compute_limits, max_duration_seconds: Number(e.target.value) } }))
              }
            />
          </label>
          <label>
            Memória máx. (MB)
            <input
              type="number"
              value={recipe.compute_limits.max_memory_mb}
              onChange={(e) =>
                setRecipe((prev) => ({ ...prev, compute_limits: { ...prev.compute_limits, max_memory_mb: Number(e.target.value) } }))
              }
            />
          </label>
        </fieldset>

        <div data-testid="compute-cost-estimate" style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
          <strong>Estimativa de custo computacional (limite superior conservador):</strong>{" "}
          ~{costEstimate.estimatedVoxelCount.toLocaleString("pt-BR")} voxels, ~
          {costEstimate.estimatedMemoryMbUpperBound.toFixed(1)} MB (grade densa sobre a bounding box do
          domínio no voxel efetivo de {costEstimate.effectiveVoxelSizeMm}mm -- mesma fórmula usada pelo
          worker antes da execução; não é o número real esparso que o PicoGK aloca, nem uma previsão de
          tempo de execução).
        </div>

        {costEstimate.heavy && (
          <p role="alert" data-testid="heavy-recipe-warning" style={{ color: "var(--color-error)" }}>
            Receita potencialmente pesada: {costEstimate.exceedsMaxVoxelCount
              ? "o número estimado de voxels excede max_voxel_count -- o job será rejeitado antes da execução."
              : "o número estimado de voxels está próximo do limite configurado"}
            {recipe.topology.kind === "voronoi_cell_edges_v1" && recipe.mode === "final" && recipe.topology.site_count > 200
              ? ", e um site_count alto em modo final aumenta o custo de avaliação por voxel"
              : ""}
            . Considere reduzir a resolução, o domínio{recipe.topology.kind === "voronoi_cell_edges_v1" ? " ou site_count" : ""}, ou usar o modo preview primeiro.
          </p>
        )}

        <p data-testid="research-result-disclaimer" style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
          Resultado computacional — não validado experimentalmente.
        </p>

        {validation.errors.length > 0 && (
          <ul style={{ color: "var(--color-error)" }}>
            {validation.errors.map((err, i) => (
              <li key={i}>
                {err.path}: {err.message}
              </li>
            ))}
          </ul>
        )}

        <button type="submit" disabled={!validation.valid || submitting}>
          {submitting ? "Enviando…" : "Salvar receita"}
        </button>
      </form>
    </AuthenticatedLayout>
  );
}
