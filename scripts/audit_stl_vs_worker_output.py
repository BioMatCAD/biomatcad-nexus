#!/usr/bin/env python3
"""Auditoria INDEPENDENTE de STL vs. saída do worker (Incremento 2.1.1, item 11).

Este script é deliberadamente uma implementação Python totalmente separada do código C# do
worker (apps/geometry-worker/GeometryMetricsCalculator.cs / StlExporter.cs) -- não importa nem
reusa nenhum código daquele projeto. O objetivo é justamente ter uma SEGUNDA implementação
independente que recalcula as métricas geométricas diretamente do arquivo STL gravado em disco,
para comparar contra o que o worker reportou no JSON de saída (stdout) e no manifesto -- exatamente
o tipo de checagem cruzada que a auditoria do Incremento 2.1 pediu (STL com 336 triângulos/224
vértices únicos enquanto o manifesto dizia 168 vértices e outra área/volume).

Uso:
    python3 scripts/audit_stl_vs_worker_output.py <caminho.stl> [--worker-json <caminho.json>] [--manifest-json <caminho.json>]

Sem argumentos além do STL, apenas imprime as métricas recalculadas. Com --worker-json e/ou
--manifest-json, compara campo a campo e retorna exit code 1 se houver qualquer divergência
acima de uma tolerância numérica pequena (ponto flutuante).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

TOLERANCE_REL = 1e-3  # 0.1% -- tolerância para diferenças de arredondamento float32 vs float64


def read_binary_stl(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Lê um STL binário e retorna (vértices_crus, triângulos) -- SEM deduplicar (fiel ao que o
    arquivo realmente contém: 3 vértices "soltos" por triângulo, limitação do próprio formato)."""
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError("Arquivo STL binário inválido (menor que o cabeçalho mínimo de 84 bytes).")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    expected_size = 84 + triangle_count * 50
    if len(data) != expected_size:
        raise ValueError(
            f"Tamanho de arquivo inconsistente com STL binário: esperado {expected_size} bytes "
            f"para {triangle_count} triângulos, obtido {len(data)} bytes. "
            "(Pode ser um STL ASCII, não suportado por este auditor -- o worker sempre grava binário.)"
        )
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    offset = 84
    for i in range(triangle_count):
        # 12 floats: normal(3) + v0(3) + v1(3) + v2(3), depois 1 uint16 de atributo.
        floats = struct.unpack_from("<12f", data, offset)
        v0 = floats[3:6]
        v1 = floats[6:9]
        v2 = floats[9:12]
        ia = len(vertices); vertices.append(v0)
        ib = len(vertices); vertices.append(v1)
        ic = len(vertices); vertices.append(v2)
        triangles.append((ia, ib, ic))
        offset += 50
    return vertices, triangles


def weld_vertices(vertices: list[tuple[float, float, float]], triangles: list[tuple[int, int, int]], epsilon: float = 1e-5):
    key_to_index: dict[tuple[int, int, int], int] = {}
    welded_vertices: list[tuple[float, float, float]] = []
    remap: list[int] = []
    inv = 1.0 / epsilon
    for v in vertices:
        key = (round(v[0] * inv), round(v[1] * inv), round(v[2] * inv))
        if key in key_to_index:
            remap.append(key_to_index[key])
        else:
            idx = len(welded_vertices)
            welded_vertices.append(v)
            key_to_index[key] = idx
            remap.append(idx)
    welded_triangles = [(remap[a], remap[b], remap[c]) for a, b, c in triangles]
    return welded_vertices, welded_triangles


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def length(a):
    return dot(a, a) ** 0.5


def compute_metrics(vertices, triangles):
    xs = [v[0] for v in vertices]; ys = [v[1] for v in vertices]; zs = [v[2] for v in vertices]
    bbox = [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]] if vertices else [[0, 0, 0], [0, 0, 0]]

    volume = 0.0
    area = 0.0
    for ia, ib, ic in triangles:
        a, b, c = vertices[ia], vertices[ib], vertices[ic]
        volume += dot(a, cross(b, c)) / 6.0
        area += 0.5 * length(cross(sub(b, a), sub(c, a)))
    volume = abs(volume)

    edge_counts: dict[tuple[int, int], int] = {}
    for ia, ib, ic in triangles:
        for u, v in ((ia, ib), (ib, ic), (ic, ia)):
            key = (u, v) if u < v else (v, u)
            edge_counts[key] = edge_counts.get(key, 0) + 1
    is_watertight = len(edge_counts) > 0 and all(c == 2 for c in edge_counts.values())

    return {
        "bounding_box_mm": bbox,
        "volume_mm3": volume,
        "surface_area_mm2": area,
        "vertex_count_unique": len(vertices),
        "triangle_count": len(triangles),
        "is_watertight": is_watertight,
    }


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_diff(a: float, b: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return abs(a - b) / max(abs(a), abs(b), 1e-12)


def compare_field(name: str, expected, actual, mismatches: list[str]) -> None:
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if relative_diff(float(expected), float(actual)) > TOLERANCE_REL:
            mismatches.append(f"{name}: esperado {expected}, obtido {actual} (diferença relativa > {TOLERANCE_REL:.1%})")
    elif expected != actual:
        mismatches.append(f"{name}: esperado {expected!r}, obtido {actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stl_path", type=Path)
    parser.add_argument("--worker-json", type=Path, default=None, help="Saída JSON (stdout) do worker para esta execução.")
    parser.add_argument("--manifest-json", type=Path, default=None, help="manifest.json correspondente, para comparação cruzada.")
    args = parser.parse_args()

    raw_vertices, raw_triangles = read_binary_stl(args.stl_path)
    welded_vertices, welded_triangles = weld_vertices(raw_vertices, raw_triangles)
    metrics = compute_metrics(welded_vertices, welded_triangles)
    stl_sha256 = sha256_of_file(args.stl_path)

    print("=== Métricas recalculadas de forma INDEPENDENTE a partir do STL ===")
    print(json.dumps({**metrics, "stl_sha256": stl_sha256, "raw_vertex_count_before_weld": len(raw_vertices)}, indent=2))

    exit_code = 0
    mismatches: list[str] = []

    if args.worker_json is not None:
        worker_output = json.loads(args.worker_json.read_text(encoding="utf-8"))
        worker_metrics = worker_output.get("metrics", {})
        print("\n=== Comparando contra metrics do worker (stdout JSON) ===")
        compare_field("volume_mm3", worker_metrics.get("volume_mm3"), metrics["volume_mm3"], mismatches)
        compare_field("surface_area_mm2", worker_metrics.get("surface_area_mm2"), metrics["surface_area_mm2"], mismatches)
        compare_field("triangle_count", worker_metrics.get("triangle_count"), metrics["triangle_count"], mismatches)
        compare_field("vertex_count_unique", worker_metrics.get("vertex_count_unique"), metrics["vertex_count_unique"], mismatches)
        compare_field("is_watertight", worker_metrics.get("is_watertight"), metrics["is_watertight"], mismatches)
        compare_field("stl_sha256", worker_output.get("stl_sha256"), stl_sha256, mismatches)

    if args.manifest_json is not None:
        manifest = json.loads(args.manifest_json.read_text(encoding="utf-8"))
        manifest_metrics = manifest.get("metrics", {})
        print("\n=== Comparando contra metrics do manifest.json ===")
        compare_field("volume_mm3 (manifest)", manifest_metrics.get("volume_mm3"), metrics["volume_mm3"], mismatches)
        compare_field("triangle_count (manifest)", manifest_metrics.get("triangle_count"), metrics["triangle_count"], mismatches)
        compare_field("vertex_count_unique (manifest)", manifest_metrics.get("vertex_count_unique"), metrics["vertex_count_unique"], mismatches)
        compare_field("stl_sha256 (manifest)", manifest.get("stl_sha256"), stl_sha256, mismatches)

    if mismatches:
        print("\n=== DIVERGÊNCIAS ENCONTRADAS ===")
        for m in mismatches:
            print(f"  - {m}")
        exit_code = 1
    elif args.worker_json is not None or args.manifest_json is not None:
        print("\nNenhuma divergência encontrada -- STL e saída(s) comparada(s) são consistentes.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
