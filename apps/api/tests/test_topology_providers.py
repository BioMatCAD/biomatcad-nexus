"""Testes do contrato TopologyProvider (Incremento 2.2, Seção 4; estendido na Seção 12 da
rodada Voronoi para cobrir o segundo provider real, voronoi_cell_edges_v1).

Cobre: registro real (gyroid e voronoi_cell_edges_v1 implementados; "voronoi" -- o placeholder
genérico reservado, sem sufixo de versão -- permanece apenas planejado e por isso rejeitado,
nunca confundido com voronoi_cell_edges_v1), rejeição de provider desconhecido na criação do
design run (defesa em profundidade, mesmo que o JSON Schema já bloqueie topology.kind fora do
oneOf antes disso), e presença do provider efetivamente usado no manifesto de reprodutibilidade
-- nunca assumido implicitamente, para QUALQUER um dos dois providers implementados.
"""
from __future__ import annotations

import json

import pytest

from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    DesignRunAuthorizationError,
    create_design_run_and_job,
)
from biomatcad_api.services.manifest_service import build_and_store_manifest
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.topology_providers import (
    UnknownTopologyProviderError,
    get_topology_provider,
    list_topology_providers,
)

from .conftest import load_golden_recipe
from .factories import create_researcher


def test_gyroid_e_implementado_e_reconhecido():
    info = get_topology_provider("gyroid")
    assert info.status == "implemented"
    assert info.provider_class == "GyroidTopologyProvider"
    assert info.version


def test_voronoi_cell_edges_v1_e_implementado_e_reconhecido():
    # Regressão direta pedida no escopo desta rodada: voronoi_cell_edges_v1 (a implementação
    # REAL, ver VoronoiTopologyProvider.cs/VoronoiScaffoldBuilder.cs) precisa estar registrada
    # como "implemented" nos dois lados -- nunca confundida com o placeholder genérico "voronoi".
    info = get_topology_provider("voronoi_cell_edges_v1")
    assert info.status == "implemented"
    assert info.provider_class == "VoronoiTopologyProvider"
    assert info.version


def test_voronoi_e_apenas_planejado_e_rejeitado():
    # Regressão direta pedida no escopo: "não implemente Voronoi completo ainda" -- o registro
    # PRECISA recusar voronoi mesmo que ele já apareça listado (status='planned').
    with pytest.raises(UnknownTopologyProviderError):
        get_topology_provider("voronoi")


def test_kind_totalmente_desconhecido_e_rejeitado():
    with pytest.raises(UnknownTopologyProviderError):
        get_topology_provider("hexagonal-honeycomb-inexistente")


def test_list_topology_providers_inclui_gyroid_implementado_e_voronoi_planejado():
    providers = {p.kind: p for p in list_topology_providers()}
    assert providers["gyroid"].status == "implemented"
    assert providers["voronoi"].status == "planned"
    # Incremento 2.2 (rodada Voronoi): o segundo provider real também precisa aparecer listado
    # e implementado, distinto do placeholder genérico "voronoi" acima.
    assert providers["voronoi_cell_edges_v1"].status == "implemented"


def _make_project(db_session, user):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto TopologyProvider")
    db_session.add(project)
    db_session.flush()
    return project


def test_design_run_rejeita_receita_com_topology_kind_desconhecido(db_session):
    # Uma receita real nunca deveria ter topology.kind != "gyroid" (o JSON Schema já impede),
    # mas este teste constrói uma diretamente no banco (contornando a validação de schema de
    # propósito) para provar que a camada de defesa em profundidade em
    # create_design_run_and_job realmente rejeita -- nunca cria um job para um provider
    # inexistente/não implementado, mesmo que uma receita inválida chegue ao banco por outro
    # caminho (ex.: migração de dados, bug futuro na validação de entrada).
    user = create_researcher(db_session, email="topology-unknown@biomatcad.example")
    project = _make_project(db_session, user)

    fake_body = load_golden_recipe("block-gyroid-v1")
    fake_body["topology"] = {**fake_body["topology"], "kind": "voronoi"}

    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita com kind desconhecido (construída direto no banco)",
        schema_version=fake_body["schema_version"],
        canonical_json=fake_body,
        checksum_sha256="0" * 64,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()

    with pytest.raises(DesignRunAuthorizationError) as exc_info:
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project.id,
            recipe_id=recipe.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key="idem-topology-unknown",
        )
    assert exc_info.value.reason_code == "TOPOLOGY_PROVIDER_UNKNOWN"


def test_design_run_aceita_receita_gyroid_normalmente(db_session):
    # Guarda de não-regressão: a checagem nova não pode quebrar o caminho real (gyroid).
    user = create_researcher(db_session, email="topology-gyroid-ok@biomatcad.example")
    project = _make_project(db_session, user)

    recipe_body = load_golden_recipe("block-gyroid-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Gyroid válida",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()

    _design_run, job, created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-topology-gyroid-ok",
    )
    assert created is True
    assert job.status == JobStatus.QUEUED


def test_design_run_aceita_receita_voronoi_normalmente(db_session):
    # Espelha test_design_run_aceita_receita_gyroid_normalmente acima, mas para o segundo
    # provider real (voronoi_cell_edges_v1) -- confirma que o caminho de criação de design
    # run/job não é hardcoded para gyroid em nenhum lugar remanescente.
    user = create_researcher(db_session, email="topology-voronoi-ok@biomatcad.example")
    project = _make_project(db_session, user)

    recipe_body = load_golden_recipe("block-voronoi-preview-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Voronoi válida",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()

    _design_run, job, created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-topology-voronoi-ok",
    )
    assert created is True
    assert job.status == JobStatus.QUEUED


def test_manifesto_registra_o_provider_de_topologia_efetivamente_usado(db_session, tmp_path):
    user = create_researcher(db_session, email="topology-manifest@biomatcad.example")
    project = _make_project(db_session, user)

    recipe_body = load_golden_recipe("block-gyroid-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Gyroid para manifesto",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()

    design_run, job, _created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-topology-manifest",
    )

    storage = LocalStorageAdapter(base_dir=tmp_path / "artifacts")
    manifest = build_and_store_manifest(
        db_session,
        job=job,
        design_run=design_run,
        recipe=recipe,
        versions={"worker_version": "0.2.0-test", "dotnet_version": "9.0.0", "picogk_version": "2.2.0"},
        duration_seconds=1.23,
        storage=storage,
        repo_root=tmp_path,
        effective_parameters=None,
        platform_info="test-platform",
        stl_sha256="a" * 64,
    )

    assert manifest.manifest_json["topology_provider"] == {
        "kind": "gyroid",
        "provider_class": "GyroidTopologyProvider",
        "version": "1.0.0",
    }


def test_manifesto_registra_provider_voronoi_quando_e_o_efetivamente_usado(db_session, tmp_path):
    # Espelha test_manifesto_registra_o_provider_de_topologia_efetivamente_usado acima, agora
    # para uma receita Voronoi -- o manifesto nunca deve assumir gyroid implicitamente.
    user = create_researcher(db_session, email="topology-manifest-voronoi@biomatcad.example")
    project = _make_project(db_session, user)

    recipe_body = load_golden_recipe("block-voronoi-preview-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Voronoi para manifesto",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()

    design_run, job, _created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-topology-manifest-voronoi",
    )

    storage = LocalStorageAdapter(base_dir=tmp_path / "artifacts")
    manifest = build_and_store_manifest(
        db_session,
        job=job,
        design_run=design_run,
        recipe=recipe,
        versions={"worker_version": "0.2.0-test", "dotnet_version": "9.0.0", "picogk_version": "2.2.0"},
        duration_seconds=1.23,
        storage=storage,
        repo_root=tmp_path,
        effective_parameters=None,
        platform_info="test-platform",
        stl_sha256="a" * 64,
    )

    assert manifest.manifest_json["topology_provider"] == {
        "kind": "voronoi_cell_edges_v1",
        "provider_class": "VoronoiTopologyProvider",
        "version": "0.1.0",
    }
