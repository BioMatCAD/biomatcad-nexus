// Estimativa de custo computacional PRÉVIA (antes do envio do job) -- Incremento 2.2, rodada
// Voronoi, Seção 10 (frontend). Mesma fórmula de LIMITE SUPERIOR (grade densa sobre a bounding
// box do domínio, nunca o número real esparso que o PicoGK aloca) já usada pelo worker para
// rejeitar receitas antes da execução -- ver apps/geometry-worker/GyroidMath.cs
// (EffectiveVoxelSizeMm/EstimateVoxelCount/EstimateMemoryMbUpperBound), reaproveitada aqui
// deliberadamente com os MESMOS números (PreviewMinVoxelSizeMm=0.3, 4 bytes/voxel) para que a
// estimativa mostrada no editor nunca divirja da validação real que o worker fará depois.
//
// Esta estimativa depende apenas de domain + resolution + mode -- é INDEPENDENTE da topologia
// (gyroid ou voronoi_cell_edges_v1 ocupam a mesma bounding box). Para Voronoi, o número de
// sítios (site_count) não entra nesta fórmula (que mede apenas o tamanho da grade de voxels),
// mas afeta o custo real de avaliação por voxel (mais sítios = mais formas implícitas
// avaliadas por amostra) -- por isso o aviso de "receita pesada" abaixo também considera
// site_count como um segundo fator heurístico, documentado como tal, nunca apresentado como
// medição real.
import type { GeometryRecipeBody } from "../api/types";

const PREVIEW_MIN_VOXEL_SIZE_MM = 0.3;
const CONSERVATIVE_BYTES_PER_VOXEL_DENSE_GRID = 4.0;

export function effectiveVoxelSizeMm(requestedVoxelSizeMm: number, mode: "preview" | "final"): number {
  if (mode === "preview") return Math.max(requestedVoxelSizeMm, PREVIEW_MIN_VOXEL_SIZE_MM);
  return requestedVoxelSizeMm;
}

export function estimateVoxelCount(domain: GeometryRecipeBody["domain"], effVoxelSizeMm: number): number {
  if (effVoxelSizeMm <= 0) return 0;
  let dimX: number, dimY: number, dimZ: number;
  if (domain.shape === "block") {
    dimX = domain.dimensions_mm.x_mm;
    dimY = domain.dimensions_mm.y_mm;
    dimZ = domain.dimensions_mm.z_mm;
  } else {
    const diameter = 2.0 * domain.dimensions_mm.radius_mm;
    dimX = diameter;
    dimY = diameter;
    dimZ = domain.dimensions_mm.height_mm;
  }
  const nx = Math.ceil(dimX / effVoxelSizeMm);
  const ny = Math.ceil(dimY / effVoxelSizeMm);
  const nz = Math.ceil(dimZ / effVoxelSizeMm);
  return nx * ny * nz;
}

export function estimateMemoryMbUpperBound(voxelCount: number): number {
  const bytes = voxelCount * CONSERVATIVE_BYTES_PER_VOXEL_DENSE_GRID;
  return bytes / (1024.0 * 1024.0);
}

export interface ComputeCostEstimate {
  effectiveVoxelSizeMm: number;
  estimatedVoxelCount: number;
  estimatedMemoryMbUpperBound: number;
  exceedsMaxVoxelCount: boolean;
  // Heurística de "receita pesada" -- combina o limite superior de voxels (>50% do limite
  // configurado) com, para Voronoi, um site_count alto em modo final (mais sítios = mais
  // avaliações de forma implícita por voxel). Nunca uma previsão exata de tempo/memória real.
  heavy: boolean;
}

export function estimateComputeCost(recipe: GeometryRecipeBody): ComputeCostEstimate {
  const requestedVoxelSizeMm = recipe.resolution?.voxel_size_mm ?? 0.2;
  const effVoxelSizeMm = effectiveVoxelSizeMm(requestedVoxelSizeMm, recipe.mode);
  const voxelCount = estimateVoxelCount(recipe.domain, effVoxelSizeMm);
  const memoryMb = estimateMemoryMbUpperBound(voxelCount);
  const exceedsMax = voxelCount > recipe.compute_limits.max_voxel_count;

  const voxelHeavy = voxelCount > 0.5 * recipe.compute_limits.max_voxel_count;
  const voronoiHeavy =
    recipe.topology.kind === "voronoi_cell_edges_v1" &&
    recipe.mode === "final" &&
    recipe.topology.site_count > 200;

  return {
    effectiveVoxelSizeMm: effVoxelSizeMm,
    estimatedVoxelCount: voxelCount,
    estimatedMemoryMbUpperBound: memoryMb,
    exceedsMaxVoxelCount: exceedsMax,
    heavy: exceedsMax || voxelHeavy || voronoiHeavy,
  };
}
