// Validação offline usada EXCLUSIVAMENTE pelo modo demo (GitHub Pages, sem backend real) --
// ver ADR-0006. Nunca substitui a validação real do backend
// (jsonschema.Draft202012Validator em services/recipe_service.py), que roda de novo sempre
// que o modo real está ativo.
//
// Incremento 2.1.1 (item 9): corrige a divergência frontend/backend -- em vez de reimplementar
// manualmente cada regra do JSON Schema em JS (que inevitavelmente diverge com o tempo), usa o
// MESMO arquivo de schema (src/schemas/geometry-recipe-v1.schema.json, cópia sincronizada e
// testada contra o arquivo canônico -- ver src/schemas/README.md) com um validador real e
// compatível (Ajv, Draft 2020-12). As regras SEMÂNTICAS que o JSON Schema não expressa
// nativamente (comparação entre campos irmãos) são replicadas aqui espelhando
// services/recipe_service.py::_semantic_topology_errors e _semantic_output_format_errors.
import Ajv2020 from "ajv/dist/2020";
import type { ErrorObject } from "ajv/dist/2020";
import schema from "../schemas/geometry-recipe-v1.schema.json";
import type { GeometryRecipeBody, RecipeValidateResponse, RecipeValidationErrorItem } from "./types";

const ajv = new Ajv2020({ allErrors: true, strict: false });
const validateStructural = ajv.compile(schema);

function ajvErrorToItem(error: ErrorObject): RecipeValidationErrorItem {
  const path = error.instancePath.replace(/^\//, "").replace(/\//g, "/") || "(raiz)";
  return {
    path: path || "(raiz)",
    message: error.message ?? "Erro de validação de schema.",
    validator: error.keyword,
  };
}

/** Camada semântica (item 2/9): espelha recipe_service.py::_semantic_topology_errors --
 * wall_thickness_mm >= cell_size_mm/2 é fisicamente contraditório (célula sem poro). */
function semanticTopologyErrors(recipe: Partial<GeometryRecipeBody>): RecipeValidationErrorItem[] {
  const topology = recipe.topology as { cell_size_mm?: unknown; wall_thickness_mm?: unknown } | undefined;
  if (!topology) return [];
  const cellSizeMm = topology.cell_size_mm;
  const wallThicknessMm = topology.wall_thickness_mm;
  if (typeof cellSizeMm !== "number" || typeof wallThicknessMm !== "number") return [];
  if (wallThicknessMm >= cellSizeMm / 2) {
    return [
      {
        path: "topology/wall_thickness_mm",
        message:
          `wall_thickness_mm (${wallThicknessMm}mm) deve ser menor que cell_size_mm/2 ` +
          `(${cellSizeMm / 2}mm) -- caso contrário a célula unitária não teria poro algum.`,
        validator: "semantic:TOPOLOGY_PARAMETERS_INCONSISTENT",
      },
    ];
  }
  return [];
}

const SUPPORTED_OUTPUT_FORMATS = new Set(["stl"]);

/** Espelha recipe_service.py::_semantic_output_format_errors -- 'vdb' é sintaticamente aceito
 * pelo schema mas não implementado por nenhuma versão atual do worker. */
function semanticOutputFormatErrors(recipe: Partial<GeometryRecipeBody>): RecipeValidationErrorItem[] {
  const formats = recipe.output_formats;
  if (!Array.isArray(formats)) return [];
  const unsupported = formats.filter((f) => !SUPPORTED_OUTPUT_FORMATS.has(f));
  if (unsupported.length > 0) {
    return [
      {
        path: "output_formats",
        message: `Formato(s) de saída solicitado(s) não suportado(s) por esta versão do worker: ${unsupported.join(", ")}.`,
        validator: "semantic:OUTPUT_FORMAT_UNSUPPORTED",
      },
    ];
  }
  return [];
}

export function validateRecipeBodyOffline(recipe: Partial<GeometryRecipeBody>): RecipeValidationErrorItem[] {
  const structuralValid = validateStructural(recipe);
  const structuralErrors = structuralValid ? [] : (validateStructural.errors ?? []).map(ajvErrorToItem);
  return [...structuralErrors, ...semanticTopologyErrors(recipe), ...semanticOutputFormatErrors(recipe)];
}

/**
 * Canonicalização recursiva determinística (Incremento 2.1.1, item 9 -- corrige bug da
 * auditoria): ordena as chaves em TODOS os níveis do objeto, não apenas no nível raiz. A
 * implementação anterior usava `JSON.stringify(recipe, Object.keys(recipe).sort())` -- o
 * segundo argumento de JSON.stringify (array de chaves) filtra/ordena chaves com a MESMA lista
 * em QUALQUER profundidade, então objetos aninhados (domain, topology, ...) tinham suas
 * próprias chaves (que não aparecem na lista de chaves do nível raiz) silenciosamente
 * DESCARTADAS -- o fingerprint nunca mudava quando um parâmetro aninhado (ex.: cell_size_mm)
 * era alterado. Corrigido construindo manualmente um objeto com chaves ordenadas em cada
 * nível, recursivamente, antes de serializar.
 */
function canonicalizeForFingerprint(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(canonicalizeForFingerprint);
  }
  if (value !== null && typeof value === "object") {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      sorted[key] = canonicalizeForFingerprint((value as Record<string, unknown>)[key]);
    }
    return sorted;
  }
  return value;
}

/**
 * Fingerprint NÃO-criptográfico (FNV-1a) usado apenas como indicador visual de mudança no
 * modo demo. NUNCA é comparado contra o checksum_sha256 real calculado pelo backend
 * (services/recipe_service.py::compute_checksum) -- ver ADR-0006.
 */
export function fingerprint(recipe: unknown): string {
  const canonical = canonicalizeForFingerprint(recipe);
  const text = JSON.stringify(canonical);
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
