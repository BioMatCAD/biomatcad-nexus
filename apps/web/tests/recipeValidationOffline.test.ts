import { describe, expect, it } from "vitest";
import { validateRecipeBodyOffline, fingerprint, offlineValidateResponse } from "../src/api/recipeValidationOffline";
import type { GeometryRecipeBody } from "../src/api/types";

const VALID_RECIPE: GeometryRecipeBody = {
  schema_version: "1.0.0",
  domain: { shape: "block", dimensions_mm: { kind: "block", x_mm: 10, y_mm: 10, z_mm: 10 } },
  topology: { kind: "gyroid", cell_size_mm: 2, isovalue: 0, target_porosity_pct: 60 },
  resolution: { voxel_size_mm: 0.2 },
  mode: "preview",
  seed: 42,
  compute_limits: { max_duration_seconds: 60, max_memory_mb: 512, max_voxel_count: 1000000 },
  output_formats: ["stl"],
};

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
