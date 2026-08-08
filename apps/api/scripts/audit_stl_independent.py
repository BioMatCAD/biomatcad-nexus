#!/usr/bin/env python3
"""Auditoria INDEPENDENTE de um STL real, gerado pelo worker PicoGK (Gyroid ou Voronoi) --
Incremento 2.2, rodada Voronoi, Seção 7 ("roteiro único de validação Windows").

"Independente" aqui significa especificamente: este script tem seu PRÓPRIO parser de STL
binário (implementado do zero em Python puro, `struct`, sem reaproveitar nenhum código do
worker C# nem do parser TypeScript do frontend) e sua PRÓPRIA reimplementação da SDF de domínio
(bloco/cilindro, mesma fórmula matemática de `GyroidMath.BoxSignedDistanceMm`/
`CappedCylinderSignedDistanceMm`, mas reescrita aqui, não chamada). O objetivo é que um bug
específico do parser/cálculo do worker C# (ex.: um erro sistemático na leitura do próprio STL
que ele acabou de escrever, ou um erro na SDF que também afeta a métrica de contenção que o
worker relata) tenha uma chance real de ser pego por uma segunda implementação independente,
em vez de comparar o worker consigo mesmo.

O que este script verifica, e como:
  1. Watertight/manifold: cada aresta (par não-ordenado de vértices, após deduplicação de
     vértices por tolerância) deve ser compartilhada por EXATAMENTE 2 triângulos. Reporta o
     número de arestas com contagem != 2 (deveria ser 0 para uma malha watertight/manifold).
  2. Contenção no domínio: para CADA vértice do STL, avalia a SDF do domínio (lida do JSON da
     receita/manifesto -- nunca hardcoded) e reporta a maior violação positiva encontrada (0.0
     = todos os vértices dentro ou na superfície, dentro de uma tolerância pequena e explícita).
  3. Bounding box, contagem de vértices únicos e triângulos -- para comparação cruzada com as
     métricas que o próprio worker reportou no manifesto (nunca aceitas cegamente).

Uso:
    python scripts/audit_stl_independent.py --stl caminho/para/arquivo.stl \\
        --recipe schemas/biomatcem/golden-recipes/block-voronoi-preview-v1.json \\
        [--manifest caminho/para/manifesto.json] [--output-json caminho/para/auditoria.json]

Nunca declara sucesso de execução real do PicoGK -- apenas audita um STL que já existe em
disco (produzido por uma execução real anterior, feita por outro passo do roteiro).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path


class StlParseError(Exception):
    pass


def parse_binary_stl(data: bytes) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    """Parser binário de STL, escrito do zero (formato: 80 bytes de cabeçalho, uint32 de
    contagem de triângulos, depois 50 bytes por triângulo: 12 floats de 4 bytes -- normal +
    3 vértices -- seguidos de 2 bytes de atributo, ignorados). Levanta StlParseError em vez de
    silenciosamente truncar/ignorar dados malformados."""
    if len(data) < 84:
        raise StlParseError(f"arquivo STL binário curto demais ({len(data)} bytes, mínimo 84).")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    expected_size = 84 + triangle_count * 50
    if len(data) < expected_size:
        raise StlParseError(
            f"arquivo STL truncado: esperado {expected_size} bytes para {triangle_count} "
            f"triângulos, encontrado {len(data)}."
        )
    triangles = []
    offset = 84
    for _ in range(triangle_count):
        # Pula a normal (12 bytes) -- recomputável a partir dos vértices se necessário; não
        # confiada aqui porque o objetivo desta auditoria é a geometria, não a normal reportada.
        v1 = struct.unpack_from("<fff", data, offset + 12)
        v2 = struct.unpack_from("<fff", data, offset + 24)
        v3 = struct.unpack_from("<fff", data, offset + 36)
        triangles.append((v1, v2, v3))
        offset += 50
    return triangles


def load_stl_triangles(path: Path) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    data = path.read_bytes()
    # STL ASCII sempre começa com "solid" seguido de espaço/quebra de linha E não contém os
    # bytes binários de um cabeçalho real -- mas o formato binário TAMBÉM pode começar com a
    # string "solid" (implementações antigas às vezes preenchem o cabeçalho assim). O teste
    # definitivo: um STL binário válido tem exatamente 84 + 50*N bytes. Só trata como ASCII se
    # esse teste falhar E o arquivo realmente parecer texto.
    if len(data) >= 5 and data[:5] == b"solid":
        try:
            return parse_binary_stl(data)
        except StlParseError:
            pass
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise StlParseError(
                f"arquivo começa com 'solid' mas não é um STL binário válido nem um STL ASCII "
                f"decodificável como UTF-8: {exc}"
            ) from exc
        return parse_ascii_stl(text)
    return parse_binary_stl(data)


def parse_ascii_stl(text: str) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []
    current: list[tuple[float, float, float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("vertex"):
            parts = stripped.split()
            if len(parts) != 4:
                raise StlParseError(f"linha 'vertex' malformada: {stripped!r}")
            current.append((float(parts[1]), float(parts[2]), float(parts[3])))
            if len(current) == 3:
                triangles.append((current[0], current[1], current[2]))
                current = []
    return triangles


def box_signed_distance_mm(x: float, y: float, z: float, half_x: float, half_y: float, half_z: float) -> float:
    """Reimplementação independente da SDF de caixa alinhada aos eixos, centrada na origem --
    mesma fórmula matemática de GyroidMath.BoxSignedDistanceMm (não uma chamada a ela)."""
    dx, dy, dz = abs(x) - half_x, abs(y) - half_y, abs(z) - half_z
    outside = math.sqrt(max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2 + max(dz, 0.0) ** 2)
    inside = min(max(dx, max(dy, dz)), 0.0)
    return outside + inside


def capped_cylinder_signed_distance_mm(x: float, y: float, z: float, radius: float, height: float) -> float:
    """Reimplementação independente da SDF de cilindro limitado -- mesma convenção EXATA de
    GyroidMath.CappedCylinderSignedDistanceMm: base em z=0, topo em z=height (NÃO simétrica em
    torno de z=0 -- `dz = max(-z, z-height)`, não `abs(z) - height/2`). O chamador
    (`domain_sdf` abaixo) é responsável por deslocar coordenadas de mundo centradas para esta
    convenção de base em zero, exatamente como GyroidScaffoldBuilder/VoronoiTessellation fazem
    (`z_mundo + height/2`)."""
    radial = math.sqrt(x * x + y * y) - radius
    axial = max(-z, z - height)
    outside = math.sqrt(max(radial, 0.0) ** 2 + max(axial, 0.0) ** 2)
    inside = min(max(radial, axial), 0.0)
    return outside + inside


def domain_sdf(point: tuple[float, float, float], domain: dict) -> float:
    shape = domain["shape"]
    dims = domain["dimensions_mm"]
    x, y, z = point
    if shape == "block":
        return box_signed_distance_mm(x, y, z, dims["x_mm"] / 2.0, dims["y_mm"] / 2.0, dims["z_mm"] / 2.0)
    if shape == "cylinder":
        # Mesma convenção de deslocamento usada por VoronoiTessellation.SignedDistanceToDomain
        # (z + height/2 antes de chamar a SDF centrada) -- domínio cilíndrico ocupa z em
        # [0, height], não [-height/2, height/2].
        return capped_cylinder_signed_distance_mm(x, y, z + dims["height_mm"] / 2.0, dims["radius_mm"], dims["height_mm"])
    raise StlParseError(f"forma de domínio não suportada por esta auditoria: {shape!r}")


def _round_key(v: tuple[float, float, float], tolerance: float) -> tuple[int, int, int]:
    inv = 1.0 / tolerance if tolerance > 0 else 1.0
    return (round(v[0] * inv), round(v[1] * inv), round(v[2] * inv))


def audit_stl(stl_path: Path, recipe: dict, dedupe_tolerance_mm: float = 1e-4) -> dict:
    triangles = load_stl_triangles(stl_path)
    domain = recipe["domain"]

    vertex_ids: dict[tuple[int, int, int], int] = {}
    vertices: list[tuple[float, float, float]] = []

    def vid(v: tuple[float, float, float]) -> int:
        key = _round_key(v, dedupe_tolerance_mm)
        if key not in vertex_ids:
            vertex_ids[key] = len(vertices)
            vertices.append(v)
        return vertex_ids[key]

    edge_counts: dict[tuple[int, int], int] = {}
    for tri in triangles:
        ids = [vid(v) for v in tri]
        for a, b in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            edge = (a, b) if a < b else (b, a)
            edge_counts[edge] = edge_counts.get(edge, 0) + 1

    non_manifold_edges = sum(1 for count in edge_counts.values() if count != 2)
    is_watertight_independent = non_manifold_edges == 0 and len(triangles) > 0

    max_violation = 0.0
    for v in vertices:
        sdf = domain_sdf(v, domain)
        max_violation = max(max_violation, sdf)

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    bounding_box = {
        "min": [min(xs), min(ys), min(zs)] if vertices else None,
        "max": [max(xs), max(ys), max(zs)] if vertices else None,
    }

    return {
        "stl_path": str(stl_path),
        "triangle_count_independent": len(triangles),
        "vertex_count_unique_independent": len(vertices),
        "edge_count_independent": len(edge_counts),
        "non_manifold_edge_count_independent": non_manifold_edges,
        "is_watertight_independent": is_watertight_independent,
        "max_domain_containment_violation_mm_independent": max_violation,
        "domain_containment_verified_independent": max_violation <= 1e-3,
        "bounding_box_mm_independent": bounding_box,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stl", required=True, help="Caminho do arquivo STL a auditar.")
    parser.add_argument("--recipe", required=True, help="Caminho do JSON da receita (para domain.shape/dimensions_mm).")
    parser.add_argument("--manifest", default=None, help="Caminho do manifesto JSON (opcional) para comparação cruzada de métricas.")
    parser.add_argument("--output-json", default=None, help="Caminho onde salvar o relatório desta auditoria (opcional).")
    args = parser.parse_args()

    stl_path = Path(args.stl)
    recipe = json.loads(Path(args.recipe).read_text(encoding="utf-8"))

    if not stl_path.exists():
        print(f"ERRO: STL não encontrado: {stl_path}", file=sys.stderr)
        return 1

    result = audit_stl(stl_path, recipe)

    if args.manifest:
        manifest_path = Path(args.manifest)
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            reported_metrics = manifest.get("manifest_json", manifest).get("metrics", {})
            comparison = {
                "triangle_count_reported_by_worker": reported_metrics.get("triangle_count"),
                "triangle_count_independent": result["triangle_count_independent"],
                "triangle_count_matches": reported_metrics.get("triangle_count") == result["triangle_count_independent"],
                "vertex_count_unique_reported_by_worker": reported_metrics.get("vertex_count_unique"),
                "vertex_count_unique_independent": result["vertex_count_unique_independent"],
                "vertex_count_unique_matches": reported_metrics.get("vertex_count_unique") == result["vertex_count_unique_independent"],
                "is_watertight_reported_by_worker": reported_metrics.get("is_watertight"),
                "is_watertight_independent": result["is_watertight_independent"],
                "watertight_matches": reported_metrics.get("is_watertight") == result["is_watertight_independent"],
                "domain_containment_verified_reported_by_worker": reported_metrics.get("domain_containment_verified"),
                "domain_containment_verified_independent": result["domain_containment_verified_independent"],
            }
            result["cross_check_vs_manifest"] = comparison
        else:
            result["cross_check_vs_manifest"] = {"error": f"manifesto não encontrado: {manifest_path}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.output_json:
        Path(args.output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    overall_ok = result["is_watertight_independent"] and result["domain_containment_verified_independent"]
    if "cross_check_vs_manifest" in result and "error" not in result["cross_check_vs_manifest"]:
        overall_ok = overall_ok and all(
            v for k, v in result["cross_check_vs_manifest"].items() if k.endswith("_matches")
        )
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
