"""Testes de schema especificos de topology.kind == "voronoi_cell_edges_v1" (Incremento 2.2,
rodada Voronoi, Secao 12 -- "Testes"). Espelha o estilo e a cobertura ja existente para o ramo
gyroid em test_recipe_schema.py, sem duplicar os testes genericos (unknown top-level field,
wrong schema_version, etc. ja cobertos la e reutilizados por qualquer ramo do oneOf de
topology). Aqui: apenas os cenarios REAIS pedidos que dependem de campos exclusivos do ramo
Voronoi (site_count, distribution, strut_radius_mm, node_smoothing, node_radius_factor,
boundary_behavior, seed_site_min_separation_mm)."""
from __future__ import annotations

import copy

import pytest

from biomatcad_api.services.recipe_service import validate_recipe

VALID_VORONOI_RECIPE = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {
        "kind": "voronoi_cell_edges_v1",
        "site_count": 12,
        "distribution": "uniform_random",
        "strut_radius_mm": 0.4,
        "node_smoothing": 0.5,
        "node_radius_factor": 1.3,
        "boundary_behavior": "clip",
        "target_porosity_pct": 65,
    },
    "resolution": {"voxel_size_mm": 0.4},
    "mode": "preview",
    "seed": 11,
    "compute_limits": {"max_duration_seconds": 30, "max_memory_mb": 512, "max_voxel_count": 200000},
    "output_formats": ["stl"],
}


def test_valid_voronoi_recipe_has_no_errors():
    assert validate_recipe(VALID_VORONOI_RECIPE) == []


def test_valid_voronoi_recipe_on_cylinder_domain_has_no_errors():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["domain"] = {"shape": "cylinder", "dimensions_mm": {"kind": "cylinder", "radius_mm": 5, "height_mm": 10}}
    assert validate_recipe(recipe) == []


def test_voronoi_unknown_nested_field_is_rejected():
    """additionalProperties:false tambem se aplica ao ramo voronoi_cell_edges_v1 do oneOf de
    topology -- mesma garantia estrutural do gyroid (ver
    test_no_arbitrary_code_execution_structural_guarantee em test_recipe_schema.py)."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["eval_expression"] = "1+1"
    errors = validate_recipe(recipe)
    assert errors, "campo desconhecido aninhado em topology voronoi deveria ser rejeitado"


def test_voronoi_field_without_mm_suffix_is_rejected_as_unknown():
    """'Unidades nunca implicitas' -- um campo com o mesmo significado mas sem o sufixo _mm
    (ex.: 'strut_radius' em vez de 'strut_radius_mm') nao existe no schema e e rejeitado como
    propriedade desconhecida, nunca aceito silenciosamente como um alias."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["strut_radius"] = recipe["topology"].pop("strut_radius_mm")
    errors = validate_recipe(recipe)
    assert errors


@pytest.mark.parametrize("site_count", [0, 1, 2, 3])
def test_site_count_below_minimum_is_rejected(site_count):
    """Minimo 4 -- necessario para qualquer tetraedralizacao de Delaunay 3D nao-degenerada."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["site_count"] = site_count
    errors = validate_recipe(recipe)
    assert errors, f"site_count={site_count} deveria ser rejeitado (minimo 4)"


def test_site_count_above_maximum_is_rejected():
    """Maximo 500 nesta rodada (receitas pequenas e conservadoras)."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["site_count"] = 501
    errors = validate_recipe(recipe)
    assert errors


@pytest.mark.parametrize("site_count", [4, 500])
def test_site_count_at_boundaries_is_accepted(site_count):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["site_count"] = site_count
    assert validate_recipe(recipe) == []


def test_site_count_missing_is_rejected():
    """site_count e obrigatorio no ramo voronoi_cell_edges_v1."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["site_count"]
    errors = validate_recipe(recipe)
    assert errors


def test_distribution_missing_is_rejected():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["distribution"]
    errors = validate_recipe(recipe)
    assert errors


def test_distribution_invalid_enum_is_rejected():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["distribution"] = "anatomy_guided"
    errors = validate_recipe(recipe)
    assert errors, "'anatomy_guided' e um ponto de extensao reservado, nao aceito nesta versao"


def test_distribution_jittered_grid_is_accepted():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["distribution"] = "jittered_grid"
    assert validate_recipe(recipe) == []


def test_strut_radius_missing_is_rejected():
    """strut_radius_mm e obrigatorio."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["strut_radius_mm"]
    errors = validate_recipe(recipe)
    assert errors


@pytest.mark.parametrize("strut_radius_mm", [0.0, 0.02, -0.1])
def test_strut_radius_at_or_below_minimum_is_rejected(strut_radius_mm):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["strut_radius_mm"] = strut_radius_mm
    errors = validate_recipe(recipe)
    assert errors, f"strut_radius_mm={strut_radius_mm} deveria ser rejeitado (exclusiveMinimum=0.02)"


def test_strut_radius_above_maximum_is_rejected():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["strut_radius_mm"] = 3.5
    errors = validate_recipe(recipe)
    assert errors


def test_strut_radius_just_above_minimum_is_accepted():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["strut_radius_mm"] = 0.021
    assert validate_recipe(recipe) == []


def test_seed_is_required_for_voronoi_recipe_too():
    """seed e um campo canonico de nivel superior da receita (compartilhado por qualquer
    topologia) -- continua obrigatorio para voronoi_cell_edges_v1."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["seed"]
    errors = validate_recipe(recipe)
    assert errors


def test_negative_seed_is_rejected_for_voronoi_recipe():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["seed"] = -1
    errors = validate_recipe(recipe)
    assert errors


@pytest.mark.parametrize("node_smoothing", [-0.1, 1.1])
def test_node_smoothing_out_of_range_is_rejected(node_smoothing):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["node_smoothing"] = node_smoothing
    errors = validate_recipe(recipe)
    assert errors


def test_node_smoothing_is_optional():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["node_smoothing"]
    assert validate_recipe(recipe) == []


@pytest.mark.parametrize("node_radius_factor", [0.5, 3.5])
def test_node_radius_factor_out_of_range_is_rejected(node_radius_factor):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["node_radius_factor"] = node_radius_factor
    errors = validate_recipe(recipe)
    assert errors


def test_node_radius_factor_is_optional():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["node_radius_factor"]
    assert validate_recipe(recipe) == []


def test_boundary_behavior_invalid_enum_is_rejected():
    """'clip' e o unico valor suportado nesta rodada -- mantido como enum (nao booleano/const)
    para extensao futura, mas qualquer outro valor deve ser rejeitado agora."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["boundary_behavior"] = "mirror"
    errors = validate_recipe(recipe)
    assert errors


def test_boundary_behavior_is_optional_and_defaults_conceptually_to_clip():
    """O schema declara default 'clip' quando omitido -- omitir o campo deve continuar valido."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["boundary_behavior"]
    assert validate_recipe(recipe) == []


@pytest.mark.parametrize("seed_site_min_separation_mm", [0.0, -1.0, 51.0])
def test_seed_site_min_separation_out_of_range_is_rejected(seed_site_min_separation_mm):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["seed_site_min_separation_mm"] = seed_site_min_separation_mm
    errors = validate_recipe(recipe)
    assert errors


def test_seed_site_min_separation_is_optional():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    assert "seed_site_min_separation_mm" not in recipe["topology"]
    assert validate_recipe(recipe) == []


@pytest.mark.parametrize("target_porosity_pct", [0, 100, -5])
def test_target_porosity_pct_out_of_range_is_rejected_for_voronoi(target_porosity_pct):
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["target_porosity_pct"] = target_porosity_pct
    errors = validate_recipe(recipe)
    assert errors


def test_target_porosity_pct_is_optional_for_voronoi():
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    del recipe["topology"]["target_porosity_pct"]
    assert validate_recipe(recipe) == []


def test_gyroid_specific_fields_on_voronoi_topology_are_rejected():
    """Confirma que os dois ramos do oneOf sao mutuamente exclusivos -- um campo exclusivo do
    Gyroid (cell_size_mm) dentro de topology.kind == voronoi_cell_edges_v1 e rejeitado como
    propriedade desconhecida (nao existe 'campo compartilhado silencioso' entre os dois ramos)."""
    recipe = copy.deepcopy(VALID_VORONOI_RECIPE)
    recipe["topology"]["cell_size_mm"] = 2.0
    errors = validate_recipe(recipe)
    assert errors


def test_voronoi_kind_with_gyroid_required_fields_missing_is_rejected():
    """Uma receita gyroid a que faltam wall_thickness_mm/cell_size_mm nao deve "vazar" para o
    ramo voronoi_cell_edges_v1 do oneOf so porque teoricamente teria menos campos exigidos --
    o schema deve rejeitar por nao casar com NENHUM ramo (kind errado)."""
    recipe = {
        "schema_version": "1.0.0",
        "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
        "topology": {"kind": "gyroid"},
        "resolution": {"voxel_size_mm": 0.2},
        "mode": "preview",
        "seed": 1,
        "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
        "output_formats": ["stl"],
    }
    errors = validate_recipe(recipe)
    assert errors
