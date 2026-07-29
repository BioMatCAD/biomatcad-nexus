"""Testes de segurança entre organizações para criação de DesignRun (Incremento 2.1.1, item 5).

Cobre exatamente os cinco ataques exigidos pela auditoria: projeto da organização A com receita
da B, projeto A com material B, receita A pertencente a outro projeto, IDs inexistentes, e
receita não validada. Todas as tentativas devem ser recusadas (DesignRunAuthorizationError) e
resultar em um AuditEvent do tipo cross_organization_access_denied -- nunca uma exceção não
tratada nem, pior, a criação silenciosa de um DesignRun inválido.
"""
from __future__ import annotations

import json

import pytest

from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.material import MaterialRecord, MaterialSourceType
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    DesignRunAuthorizationError,
    create_design_run_and_job,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize

from .factories import create_researcher

GOOD_RECIPE_BODY = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "wall_thickness_mm": 0.4, "isovalue": 0.0, "target_porosity_pct": 60},
    "resolution": {"voxel_size_mm": 0.2},
    "mode": "preview",
    "seed": 42,
    "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
    "output_formats": ["stl"],
}


def _make_project(db_session, user, name="Projeto"):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name=name)
    db_session.add(project)
    db_session.flush()
    return project


def _make_recipe(db_session, user, project, *, status=RecipeStatus.VALIDATED, name="Receita"):
    canonical_str, checksum = validate_and_canonicalize(GOOD_RECIPE_BODY)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name=name,
        schema_version=GOOD_RECIPE_BODY["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=status,
    )
    db_session.add(recipe)
    db_session.flush()
    return recipe


def _make_material(db_session, user, name="Material"):
    material = MaterialRecord(
        organization_id=user.organization_id, name=name, category="ceramic", source_type=MaterialSourceType.SYNTHETIC
    )
    db_session.add(material)
    db_session.flush()
    return material


def _count_denied_audit_events(db_session, organization_id) -> int:
    return (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.organization_id == organization_id,
            AuditEvent.event_type == "cross_organization_access_denied",
        )
        .count()
    )


def test_project_org_a_with_recipe_org_b_is_denied(db_session):
    user_a = create_researcher(db_session, email="seca1@biomatcad.example")
    user_b = create_researcher(db_session, email="secb1@biomatcad.example")
    project_a = _make_project(db_session, user_a)
    recipe_b = _make_recipe(db_session, user_b, _make_project(db_session, user_b))

    before = _count_denied_audit_events(db_session, user_a.organization_id)
    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user_a.organization_id,
            project_id=project_a.id,
            recipe_id=recipe_b.id,
            material_id=None,
            created_by_user_id=user_a.id,
            idempotency_key="attack-1",
        )
    assert exc_info.value.reason_code == "RECIPE_ORGANIZATION_MISMATCH"
    assert _count_denied_audit_events(db_session, user_a.organization_id) == before + 1


def test_project_org_a_with_material_org_b_is_denied(db_session):
    user_a = create_researcher(db_session, email="seca2@biomatcad.example")
    user_b = create_researcher(db_session, email="secb2@biomatcad.example")
    project_a = _make_project(db_session, user_a)
    recipe_a = _make_recipe(db_session, user_a, project_a)
    material_b = _make_material(db_session, user_b)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user_a.organization_id,
            project_id=project_a.id,
            recipe_id=recipe_a.id,
            material_id=material_b.id,
            created_by_user_id=user_a.id,
            idempotency_key="attack-2",
        )
    assert exc_info.value.reason_code == "MATERIAL_ORGANIZATION_MISMATCH"


def test_recipe_belonging_to_another_project_same_org_is_denied(db_session):
    user = create_researcher(db_session, email="sec3@biomatcad.example")
    project_1 = _make_project(db_session, user, name="Projeto 1")
    project_2 = _make_project(db_session, user, name="Projeto 2")
    recipe_of_project_2 = _make_recipe(db_session, user, project_2)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project_1.id,
            recipe_id=recipe_of_project_2.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key="attack-3",
        )
    assert exc_info.value.reason_code == "RECIPE_PROJECT_MISMATCH"


def test_nonexistent_project_id_is_denied(db_session):
    user = create_researcher(db_session, email="sec4@biomatcad.example")
    project = _make_project(db_session, user)
    recipe = _make_recipe(db_session, user, project)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id="00000000-0000-0000-0000-000000000000",
            recipe_id=recipe.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key="attack-4a",
        )
    assert exc_info.value.reason_code == "PROJECT_NOT_FOUND"


def test_nonexistent_recipe_id_is_denied(db_session):
    user = create_researcher(db_session, email="sec5@biomatcad.example")
    project = _make_project(db_session, user)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project.id,
            recipe_id="00000000-0000-0000-0000-000000000000",
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key="attack-4b",
        )
    assert exc_info.value.reason_code == "RECIPE_NOT_FOUND"


def test_nonexistent_material_id_is_denied(db_session):
    user = create_researcher(db_session, email="sec6@biomatcad.example")
    project = _make_project(db_session, user)
    recipe = _make_recipe(db_session, user, project)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project.id,
            recipe_id=recipe.id,
            material_id="00000000-0000-0000-0000-000000000000",
            created_by_user_id=user.id,
            idempotency_key="attack-4c",
        )
    assert exc_info.value.reason_code == "MATERIAL_NOT_FOUND"


def test_unvalidated_draft_recipe_is_denied(db_session):
    user = create_researcher(db_session, email="sec7@biomatcad.example")
    project = _make_project(db_session, user)
    draft_recipe = _make_recipe(db_session, user, project, status=RecipeStatus.DRAFT)

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project.id,
            recipe_id=draft_recipe.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key="attack-5",
        )
    assert exc_info.value.reason_code == "RECIPE_NOT_VALIDATED"


def test_valid_combination_is_accepted_for_contrast(db_session):
    """Garante que as checagens acima não estão rejeitando tudo indiscriminadamente."""
    user = create_researcher(db_session, email="sec8@biomatcad.example")
    project = _make_project(db_session, user)
    recipe = _make_recipe(db_session, user, project)
    material = _make_material(db_session, user)

    design_run, _job, created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=material.id,
        created_by_user_id=user.id,
        idempotency_key="attack-control",
    )
    assert created is True
    assert design_run.recipe_id == recipe.id
