import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { demoApiClient } from "../api/demoClient";
import type { GeometryRecipeBody, RecipeValidateResponse } from "../api/types";
import { AuthenticatedLayout } from "../components/layout/AuthenticatedLayout";
import { ErrorState } from "../components/feedback/ErrorState";
import { useAuth } from "../context/AuthContext";

const isDemoMode = Boolean(__BIOMATCAD_DEMO_MODE__);
const client = isDemoMode ? demoApiClient : apiClient;

const DEFAULT_RECIPE: GeometryRecipeBody = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: { kind: "gyroid", cell_size_mm: 2, wall_thickness_mm: 0.4, isovalue: 0, target_porosity_pct: 60 },
  resolution: { voxel_size_mm: 0.2 },
  mode: "preview",
  seed: 1,
  compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
  output_formats: ["stl"],
};

const EMPTY_VALIDATION: RecipeValidateResponse = { valid: false, errors: [], checksum_sha256: null, schema_version: "1.0.0" };

// Espelha o registro real de providers de topologia (Incremento 2.2, Seção 4 -- ver
// apps/api/src/biomatcad_api/services/topology_providers.py e
// apps/geometry-worker/TopologyProviderRegistry.cs). Nunca invente um provider "implementado"
// aqui que não exista de verdade nos dois lados -- Voronoi aparece listado (para deixar o
// contrato futuro visível) mas permanece desabilitado até ter uma implementação real.
const TOPOLOGY_PROVIDERS: Array<{ kind: string; label: string; implemented: boolean }> = [
  { kind: "gyroid", label: "Gyroid (TPMS) -- implementado", implemented: true },
  { kind: "voronoi", label: "Voronoi -- em preparação, ainda não implementado", implemented: false },
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
            <select id="topology-provider-select" value="gyroid" disabled>
              {TOPOLOGY_PROVIDERS.map((p) => (
                <option key={p.kind} value={p.kind} disabled={!p.implemented}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <p style={{ fontSize: "0.85em", color: "var(--color-text-secondary)" }}>
            Apenas Gyroid está implementado e testado nesta versão. Outras topologias (Voronoi,
            outras TPMS, híbridas) exigem um novo provider registrado antes de ficarem
            selecionáveis -- nunca uma opção decorativa sem execução real por trás.
          </p>
        </fieldset>

        <fieldset>
          <legend>Topologia (gyroid)</legend>
          <label>
            Tamanho da célula (mm)
            <input
              type="number"
              step="0.1"
              value={recipe.topology.cell_size_mm}
              onChange={(e) => setRecipe((prev) => ({ ...prev, topology: { ...prev.topology, cell_size_mm: Number(e.target.value) } }))}
            />
          </label>
          <label>
            Espessura de parede (mm) -- obrigatório, único controlador de espessura
            <input
              type="number"
              step="0.05"
              value={recipe.topology.wall_thickness_mm}
              onChange={(e) => setRecipe((prev) => ({ ...prev, topology: { ...prev.topology, wall_thickness_mm: Number(e.target.value) } }))}
            />
          </label>
          <label>
            Isovalor (centro da banda -- não controla espessura, default 0)
            <input
              type="number"
              step="0.1"
              value={recipe.topology.isovalue ?? 0}
              onChange={(e) => setRecipe((prev) => ({ ...prev, topology: { ...prev.topology, isovalue: Number(e.target.value) } }))}
            />
          </label>
          <label>
            Porosidade-alvo (%)
            <input
              type="number"
              value={recipe.topology.target_porosity_pct ?? 60}
              onChange={(e) =>
                setRecipe((prev) => ({ ...prev, topology: { ...prev.topology, target_porosity_pct: Number(e.target.value) } }))
              }
            />
          </label>
        </fieldset>

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
