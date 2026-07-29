// Reimplementação em JS puro das regras de schemas/biomatcem/geometry-recipe-v1.schema.json,
// usada EXCLUSIVAMENTE pelo modo demo (GitHub Pages, sem backend real) -- ver ADR-0006.
// Nunca substitui a validação real do backend (jsonschema.Draft202012Validator em
// services/recipe_service.py), que roda de novo sempre que o modo real está ativo.
import type { GeometryRecipeBody, RecipeValidateResponse, RecipeValidationErrorItem } from "./types";

export function validateRecipeBodyOffline(recipe: Partial<GeometryRecipeBody>): RecipeValidationErrorItem[] {
  const errors: RecipeValidationErrorItem[] = [];
  const push = (path: string, message: string, validator: string) => errors.push({ path, message, validator });

  if (recipe.schema_version !== "1.0.0") {
    push("schema_version", 'schema_version deve ser exatamente "1.0.0".', "const");
  }

  const domain = recipe.domain;
  if (!domain) {
    push("domain", "domain é obrigatório.", "required");
  } else if (domain.shape === "block") {
    const d = domain.dimensions_mm as { x_mm?: number; y_mm?: number; z_mm?: number };
    for (const [key, value] of [
      ["x_mm", d?.x_mm],
      ["y_mm", d?.y_mm],
      ["z_mm", d?.z_mm],
    ] as const) {
      if (typeof value !== "number" || value <= 0 || value > 200) {
        push(`domain/dimensions_mm/${key}`, `${key} deve ser um número entre 0 (exclusivo) e 200mm.`, "range");
      }
    }
  } else if (domain.shape === "cylinder") {
    const d = domain.dimensions_mm as { radius_mm?: number; height_mm?: number };
    if (typeof d?.radius_mm !== "number" || d.radius_mm <= 0 || d.radius_mm > 100) {
      push("domain/dimensions_mm/radius_mm", "radius_mm deve ser um número entre 0 (exclusivo) e 100mm.", "range");
    }
    if (typeof d?.height_mm !== "number" || d.height_mm <= 0 || d.height_mm > 200) {
      push("domain/dimensions_mm/height_mm", "height_mm deve ser um número entre 0 (exclusivo) e 200mm.", "range");
    }
  } else {
    push("domain/shape", 'shape deve ser "block" ou "cylinder".', "enum");
  }

  const topology = recipe.topology;
  if (!topology) {
    push("topology", "topology é obrigatório.", "required");
  } else {
    if (topology.kind !== "gyroid") push("topology/kind", 'kind deve ser "gyroid" nesta versão.', "const");
    if (typeof topology.cell_size_mm !== "number" || topology.cell_size_mm <= 0.1 || topology.cell_size_mm > 20) {
      push("topology/cell_size_mm", "cell_size_mm deve ser um número entre 0.1 (exclusivo) e 20mm.", "range");
    }
    if (typeof topology.isovalue !== "number" || topology.isovalue < -1.5 || topology.isovalue > 1.5) {
      push("topology/isovalue", "isovalue deve ser um número entre -1.5 e 1.5.", "range");
    }
  }

  if (recipe.mode !== "preview" && recipe.mode !== "final") {
    push("mode", 'mode deve ser "preview" ou "final".', "enum");
  }

  if (typeof recipe.seed !== "number" || recipe.seed < 0 || !Number.isInteger(recipe.seed)) {
    push("seed", "seed deve ser um inteiro >= 0.", "type");
  }

  const limits = recipe.compute_limits;
  if (!limits) {
    push("compute_limits", "compute_limits é obrigatório.", "required");
  } else {
    if (!Number.isInteger(limits.max_duration_seconds) || limits.max_duration_seconds < 1 || limits.max_duration_seconds > 3600) {
      push("compute_limits/max_duration_seconds", "max_duration_seconds deve ser um inteiro entre 1 e 3600.", "range");
    }
    if (!Number.isInteger(limits.max_memory_mb) || limits.max_memory_mb < 64 || limits.max_memory_mb > 16384) {
      push("compute_limits/max_memory_mb", "max_memory_mb deve ser um inteiro entre 64 e 16384.", "range");
    }
    if (!Number.isInteger(limits.max_voxel_count) || limits.max_voxel_count < 1000) {
      push("compute_limits/max_voxel_count", "max_voxel_count deve ser um inteiro >= 1000.", "range");
    }
  }

  if (!Array.isArray(recipe.output_formats) || recipe.output_formats.length === 0) {
    push("output_formats", "output_formats deve ter ao menos um formato.", "minItems");
  } else if (recipe.output_formats.some((f) => f !== "stl" && f !== "vdb")) {
    push("output_formats", 'output_formats só aceita "stl" e/ou "vdb".', "enum");
  }

  return errors;
}

/**
 * Fingerprint NÃO-criptográfico (FNV-1a) usado apenas como indicador visual de mudança no
 * modo demo. NUNCA é comparado contra o checksum_sha256 real calculado pelo backend
 * (services/recipe_service.py::compute_checksum) -- ver ADR-0006.
 */
export function fingerprint(recipe: unknown): string {
  const text = JSON.stringify(recipe, Object.keys(recipe as object).sort());
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function offlineValidateResponse(recipe: Partial<GeometryRecipeBody>): RecipeValidateResponse {
  const errors = validateRecipeBodyOffline(recipe);
  return {
    valid: errors.length === 0,
    errors,
    checksum_sha256: errors.length === 0 ? `demo-fingerprint-${fingerprint(recipe)}` : null,
    schema_version: "1.0.0",
  };
}
