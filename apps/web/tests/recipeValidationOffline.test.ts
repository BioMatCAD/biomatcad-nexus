import { describe, expect, it } from "vitest";
import { validateRecipeBodyOffline, fingerprint, offlineValidateResponse } from "../src/api/recipeValidationOffline";
import type { GeometryRecipeBody } from "../src/api/types";

// Usa `satisfies` (não `: GeometryRecipeBody`) deliberadamente: mantém o tipo literal
// estreito de `topology` (o ramo gyroid concreto, com cell_size_mm/wall_thickness_mm) em vez
// de alargar para a união GyroidTopologyBody | VoronoiTopologyBody -- do contrário,
// `VALID_RECIPE.topology.cell_size_mm` abaixo exigiria uma checagem de narrowing em cada uso
// (Incremento 2.2, rodada Voronoi: topology virou união quando voronoi_cell_edges_v1 foi
// adicionado a GeometryRecipeBody).
const VALID_RECIPE = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: { kind: "gyroid", cell_size_mm: 2, wall_thickness_mm: 0.4, isovalue: 0, target_porosity_pct: 60 },
  resolution: { voxel_size_mm: 0.2 },
  mode: "preview",
  seed: 42,
  compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
  output_formats: ["stl"],
} satisfies GeometryRecipeBody;

describe("validateRecipeBodyOffline", () => {
  it("aceita uma receita válida sem erros", () => {
    expect(validateRecipeBodyOffline(VALID_RECIPE)).toEqual([]);
  });

  it("rejeita schema_version diferente de 1.0.0", () => {
    const errors = validateRecipeBodyOffline({ ...VALID_RECIPE, schema_version: "2.0.0" as "1.0.0" });
    expect(errors.length).toBeGreaterThan(0);
  });

  it("rejeita dimensões de bloco fora do limite", () => {
    const bad: GeometryRecipeBody = {
      ...VALID_RECIPE,
      domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 500, y_mm: 10, z_mm: 10 } },
    };
    expect(validateRecipeBodyOffline(bad).length).toBeGreaterThan(0);
  });

  it("rejeita cell_size_mm fora do limite", () => {
    const bad: GeometryRecipeBody = {
      ...VALID_RECIPE,
      topology: { ...VALID_RECIPE.topology, cell_size_mm: 50 },
    };
    expect(validateRecipeBodyOffline(bad).length).toBeGreaterThan(0);
  });

  it("rejeita seed negativo", () => {
    const bad: GeometryRecipeBody = { ...VALID_RECIPE, seed: -1 };
    expect(validateRecipeBodyOffline(bad).length).toBeGreaterThan(0);
  });

  it("fingerprint é determinístico para o mesmo conteúdo lógico", () => {
    const a = fingerprint(VALID_RECIPE);
    const b = fingerprint({ ...VALID_RECIPE });
    expect(a).toBe(b);
  });

  it("offlineValidateResponse retorna checksum_sha256 apenas quando válida", () => {
    const validResponse = offlineValidateResponse(VALID_RECIPE);
    expect(validResponse.valid).toBe(true);
    expect(validResponse.checksum_sha256).not.toBeNull();

    const invalidResponse = offlineValidateResponse({ ...VALID_RECIPE, seed: -1 });
    expect(invalidResponse.valid).toBe(false);
    expect(invalidResponse.checksum_sha256).toBeNull();
  });
});


describe("validateRecipeBodyOffline -- Incremento 2.1.1 (item 9)", () => {
  it("rejeita a ausência de wall_thickness_mm (agora obrigatório)", () => {
    const bad = { ...VALID_RECIPE, topology: { ...VALID_RECIPE.topology } } as Partial<GeometryRecipeBody>;
    delete (bad.topology as unknown as Record<string, unknown>).wall_thickness_mm;
    expect(validateRecipeBodyOffline(bad).length).toBeGreaterThan(0);
  });

  it("aceita receita sem isovalue (agora opcional)", () => {
    const ok = { ...VALID_RECIPE, topology: { ...VALID_RECIPE.topology } } as Partial<GeometryRecipeBody>;
    delete (ok.topology as unknown as Record<string, unknown>).isovalue;
    expect(validateRecipeBodyOffline(ok)).toEqual([]);
  });

  it("rejeita wall_thickness_mm >= cell_size_mm/2 (camada semântica)", () => {
    const bad: GeometryRecipeBody = {
      ...VALID_RECIPE,
      topology: { ...VALID_RECIPE.topology, cell_size_mm: 1.0, wall_thickness_mm: 0.6 },
    };
    const errors = validateRecipeBodyOffline(bad);
    expect(errors.some((e) => e.validator === "semantic:TOPOLOGY_PARAMETERS_INCONSISTENT")).toBe(true);
  });

  it("rejeita output_formats contendo vdb (não suportado)", () => {
    const bad: GeometryRecipeBody = { ...VALID_RECIPE, output_formats: ["stl", "vdb"] };
    const errors = validateRecipeBodyOffline(bad);
    expect(errors.some((e) => e.validator === "semantic:OUTPUT_FORMAT_UNSUPPORTED")).toBe(true);
  });

  it("rejeita campo desconhecido aninhado (usa o schema real via Ajv, não regras manuais)", () => {
    const bad = {
      ...VALID_RECIPE,
      topology: { ...VALID_RECIPE.topology, eval_expression: "1+1" },
    } as unknown as Partial<GeometryRecipeBody>;
    expect(validateRecipeBodyOffline(bad).length).toBeGreaterThan(0);
  });
});

describe("fingerprint -- canonicalização recursiva determinística (Incremento 2.1.1, item 9)", () => {
  it("muda quando um parâmetro ANINHADO é alterado (bug da auditoria corrigido)", () => {
    const original = fingerprint(VALID_RECIPE);
    const changedNested: GeometryRecipeBody = {
      ...VALID_RECIPE,
      topology: { ...VALID_RECIPE.topology, cell_size_mm: 3.3 },
    };
    expect(fingerprint(changedNested)).not.toBe(original);
  });

  it("muda quando um parâmetro DUPLAMENTE aninhado é alterado (domain.dimensions_mm.x_mm)", () => {
    const original = fingerprint(VALID_RECIPE);
    const changedDeep: GeometryRecipeBody = {
      ...VALID_RECIPE,
      domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 99, y_mm: 10, z_mm: 10 } },
    };
    expect(fingerprint(changedDeep)).not.toBe(original);
  });

  it("é insensível à ordem das chaves em qualquer nível de aninhamento", () => {
    const reordered = {
      output_formats: VALID_RECIPE.output_formats,
      seed: VALID_RECIPE.seed,
      mode: VALID_RECIPE.mode,
      compute_limits: VALID_RECIPE.compute_limits,
      resolution: VALID_RECIPE.resolution,
      topology: {
        target_porosity_pct: VALID_RECIPE.topology.target_porosity_pct,
        isovalue: VALID_RECIPE.topology.isovalue,
        wall_thickness_mm: VALID_RECIPE.topology.wall_thickness_mm,
        cell_size_mm: VALID_RECIPE.topology.cell_size_mm,
        kind: VALID_RECIPE.topology.kind,
      },
      domain: VALID_RECIPE.domain,
      schema_version: VALID_RECIPE.schema_version,
    };
    expect(fingerprint(reordered)).toBe(fingerprint(VALID_RECIPE));
  });

  it("continua explicitamente diferente do formato de um SHA-256 real (64 hex chars)", () => {
    const fp = fingerprint(VALID_RECIPE);
    expect(fp.length).not.toBe(64);
  });
});