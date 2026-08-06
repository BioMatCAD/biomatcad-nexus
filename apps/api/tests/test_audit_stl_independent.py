"""Testes de scripts/audit_stl_independent.py (Incremento 2.2, rodada Voronoi, Seção 7): o
parser de STL binário e a reimplementação independente da SDF de domínio, escritos do zero
especificamente para esta auditoria (nunca reaproveitando código do worker C#), precisam ter
sua própria cobertura real -- nunca confiados sem prova só porque "parecem simples"."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_stl_independent import (  # noqa: E402
    StlParseError,
    audit_stl,
    box_signed_distance_mm,
    capped_cylinder_signed_distance_mm,
    load_stl_triangles,
    parse_ascii_stl,
)

BLOCK_RECIPE = {"domain": {"shape": "block", "dimensions_mm": {"x_mm": 10, "y_mm": 10, "z_mm": 10}}}
CYLINDER_RECIPE = {"domain": {"shape": "cylinder", "dimensions_mm": {"radius_mm": 5, "height_mm": 10}}}

# Tetraedro simples, watertight, contido no bloco 10x10x10 centrado na origem.
_TETRA_VERTS = [(0.0, 0.0, 3.0), (-2.0, -2.0, -1.0), (2.0, -2.0, -1.0), (0.0, 2.0, -1.0)]
_TETRA_FACES = [(0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)]


def _binary_stl_bytes(vertices, faces) -> bytes:
    def tri_bytes(v1, v2, v3) -> bytes:
        return (
            struct.pack("<3f", 0.0, 0.0, 0.0)
            + struct.pack("<3f", *v1)
            + struct.pack("<3f", *v2)
            + struct.pack("<3f", *v3)
            + struct.pack("<H", 0)
        )

    data = b"solid" + b" " * 75
    data += struct.pack("<I", len(faces))
    for f in faces:
        data += tri_bytes(vertices[f[0]], vertices[f[1]], vertices[f[2]])
    return data


def _write_stl(tmp_path: Path, name: str, vertices, faces) -> Path:
    path = tmp_path / name
    path.write_bytes(_binary_stl_bytes(vertices, faces))
    return path


def test_watertight_tetrahedron_inside_block_is_fully_verified(tmp_path):
    stl_path = _write_stl(tmp_path, "tetra.stl", _TETRA_VERTS, _TETRA_FACES)
    result = audit_stl(stl_path, BLOCK_RECIPE)
    assert result["triangle_count_independent"] == 4
    assert result["vertex_count_unique_independent"] == 4
    assert result["non_manifold_edge_count_independent"] == 0
    assert result["is_watertight_independent"] is True
    assert result["max_domain_containment_violation_mm_independent"] == 0.0
    assert result["domain_containment_verified_independent"] is True


def test_mesh_missing_one_face_is_detected_as_non_watertight(tmp_path):
    faces_missing_one = _TETRA_FACES[:3]
    stl_path = _write_stl(tmp_path, "broken.stl", _TETRA_VERTS, faces_missing_one)
    result = audit_stl(stl_path, BLOCK_RECIPE)
    assert result["non_manifold_edge_count_independent"] > 0
    assert result["is_watertight_independent"] is False


def test_vertex_outside_domain_is_detected_as_containment_violation(tmp_path):
    verts_outside = [(0.0, 0.0, 30.0), (-2.0, -2.0, -1.0), (2.0, -2.0, -1.0), (0.0, 2.0, -1.0)]
    stl_path = _write_stl(tmp_path, "outside.stl", verts_outside, _TETRA_FACES)
    result = audit_stl(stl_path, BLOCK_RECIPE)
    assert result["max_domain_containment_violation_mm_independent"] > 20.0
    assert result["domain_containment_verified_independent"] is False


def test_tetrahedron_inside_cylinder_domain_is_verified(tmp_path):
    small_tetra = [(0.0, 0.0, 1.0), (-0.5, -0.5, -1.0), (0.5, -0.5, -1.0), (0.0, 0.5, -1.0)]
    stl_path = _write_stl(tmp_path, "tetra_cyl.stl", small_tetra, _TETRA_FACES)
    result = audit_stl(stl_path, CYLINDER_RECIPE)
    assert result["domain_containment_verified_independent"] is True


def test_ascii_stl_parses_identically_to_binary(tmp_path):
    ascii_lines = ["solid test"]
    for f in _TETRA_FACES:
        ascii_lines.append("facet normal 0 0 0")
        ascii_lines.append("outer loop")
        for idx in f:
            v = _TETRA_VERTS[idx]
            ascii_lines.append(f"vertex {v[0]} {v[1]} {v[2]}")
        ascii_lines.append("endloop")
        ascii_lines.append("endfacet")
    ascii_lines.append("endsolid test")
    ascii_path = tmp_path / "tetra_ascii.stl"
    ascii_path.write_text("\n".join(ascii_lines), encoding="utf-8")

    triangles = load_stl_triangles(ascii_path)
    assert len(triangles) == 4


def test_box_signed_distance_zero_at_face_center():
    assert box_signed_distance_mm(5.0, 0.0, 0.0, 5.0, 5.0, 5.0) == pytest.approx(0.0, abs=1e-9)


def test_box_signed_distance_negative_strictly_inside():
    assert box_signed_distance_mm(0.0, 0.0, 0.0, 5.0, 5.0, 5.0) < 0.0


def test_box_signed_distance_positive_outside():
    assert box_signed_distance_mm(10.0, 0.0, 0.0, 5.0, 5.0, 5.0) == pytest.approx(5.0)


def test_capped_cylinder_signed_distance_negative_strictly_inside():
    # Convenção EXATA da função crua (sem o deslocamento de domain_sdf): base em z=0, topo em
    # z=height -- o centro geométrico real está em z=height/2, não z=0.
    assert capped_cylinder_signed_distance_mm(0.0, 0.0, 5.0, 5.0, 10.0) < 0.0


def test_capped_cylinder_signed_distance_zero_at_base_and_top():
    assert capped_cylinder_signed_distance_mm(0.0, 0.0, 0.0, 5.0, 10.0) == pytest.approx(0.0, abs=1e-9)
    assert capped_cylinder_signed_distance_mm(0.0, 0.0, 10.0, 5.0, 10.0) == pytest.approx(0.0, abs=1e-9)


def test_capped_cylinder_signed_distance_positive_beyond_radius():
    assert capped_cylinder_signed_distance_mm(10.0, 0.0, 0.0, 5.0, 10.0) == pytest.approx(5.0)


def test_truncated_binary_stl_raises_structured_error(tmp_path):
    stl_path = tmp_path / "truncated.stl"
    full = _binary_stl_bytes(_TETRA_VERTS, _TETRA_FACES)
    stl_path.write_bytes(full[:-10])
    with pytest.raises(StlParseError):
        load_stl_triangles(stl_path)


def test_ascii_stl_with_malformed_vertex_line_raises_structured_error():
    with pytest.raises(StlParseError):
        parse_ascii_stl("solid x\nfacet normal 0 0 0\nouter loop\nvertex 1 2\nendloop\nendfacet\nendsolid x\n")
