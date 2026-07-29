"""Testes do JSON Schema BioMatCEM (Incremento 2.1, item 8): valores fora dos limites, campos
desconhecidos, unidades ausentes/erradas, canonicalização e checksum. Não depende de banco de
dados nem de rede -- testa apenas services/recipe_service.py."""
from __future__ import annotations

import copy

import pytest

from biomatcad_api.services.recipe_service import (
    RecipeValidationError,
    canonicalize_recipe,
    compute_checksum,
    schema_version,
    validate_and_canonicalize,
    validate_recipe,
)
from tests.conftest import load_golden_recipe

VALID_RECIPE = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "isovalue": 0.0, "target_porosity_pct": 60},
    "resolution": {"voxel_size_mm": 0.2},
    "mode": "preview",
    "seed": 42,
    "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
    "output_formats": ["stl"],
}


def test_valid_recipe_has_no_errors():
    assert validate_recipe(VALID_RECIPE) == []


def test_unknown_top_level_field_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["arbitrary_code"] = "os.system('rm -rf /')"
    errors = validate_recipe(recipe)
    assert errors, "campo desconhecido na raiz deveria ser rejeitado"


def test_unknown_nested_field_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["topology"]["eval_expression"] = "1+1"
    errors = validate_recipe(recipe)
    assert errors, "campo desconhecido aninhado deveria ser rejeitado"


def test_block_dimension_above_max_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["domain"]["dimensions_mm"]["x_mm"] = 500
    errors = validate_recipe(recipe)
    assert errors


def test_block_dimension_zero_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["domain"]["dimensions_mm"]["x_mm"] = 0
    errors = validate_recipe(recipe)
    assert errors


def test_cylinder_domain_accepted():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["domain"] = {"shape": "cylinder", "dimensions_mm": {"kind": "cylinder", "radius_mm": 5, "height_mm": 12}}
    assert validate_recipe(recipe) == []


def test_cell_size_below_min_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["topology"]["cell_size_mm"] = 0.01
    errors = validate_recipe(recipe)
    assert errors


def test_cell_size_above_max_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["topology"]["cell_size_mm"] = 50
    errors = validate_recipe(recipe)
    assert errors


def test_missing_required_field_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    del recipe["seed"]
    errors = validate_recipe(recipe)
    assert errors


def test_wrong_schema_version_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["schema_version"] = "0.9.0"
    errors = validate_recipe(recipe)
    assert errors


def test_invalid_topology_kind_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["topology"]["kind"] = "schwarz-p"
    errors = validate_recipe(recipe)
    assert errors


def test_invalid_domain_shape_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["domain"]["shape"] = "sphere"
    errors = validate_recipe(recipe)
    assert errors


def test_invalid_output_format_is_rejected():
    recipe = copy.deepcopy(VALID_RECIPE)
    recipe["output_formats"] = ["obj"]
    errors = validate_recipe(recipe)
    assert errors


def test_no_arbitrary_code_execution_structural_guarantee():
    """additionalProperties:false em todos os níveis é o mecanismo que impede o envio de
    código/expressões arbitrárias -- este teste apenas confirma estruturalmente que a raiz e
    os sub-objetos do schema declaram essa restrição."""
    from biomatcad_api.services.recipe_service import _load_schema

    schema = _load_schema()
    assert schema["additionalProperties"] is False
    for key in ("domain", "topology", "resolution", "compute_limits"):
        assert schema["properties"][key]["additionalProperties"] is False


def test_canonicalization_is_order_independent():
    reordered = {
        "output_formats": VALID_RECIPE["output_formats"],
        "compute_limits": VALID_RECIPE["compute_limits"],
        "seed": VALID_RECIPE["seed"],
        "mode": VALID_RECIPE["mode"],
        "resolution": VALID_RECIPE["resolution"],
        "topology": VALID_RECIPE["topology"],
        "domain": VALID_RECIPE["domain"],
        "schema_version": VALID_RECIPE["schema_version"],
    }
    canon_a = canonicalize_recipe(VALID_RECIPE)
    canon_b = canonicalize_recipe(reordered)
    assert canon_a == canon_b
    assert compute_checksum(canon_a) == compute_checksum(canon_b)


def test_validate_and_canonicalize_raises_on_invalid_recipe():
    recipe = copy.deepcopy(VALID_RECIPE)
    del recipe["seed"]
    with pytest.raises(RecipeValidationError) as exc_info:
        validate_and_canonicalize(recipe)
    assert exc_info.value.errors


def test_schema_version_helper_matches_recipe():
    assert schema_version() == "1.0.0"


@pytest.mark.parametrize(
    "golden_name", ["block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1"]
)
def test_golden_recipes_all_validate(golden_name):
    recipe = load_golden_recipe(golden_name)
    assert validate_recipe(recipe) == [], f"{golden_name} deveria ser uma receita válida"
