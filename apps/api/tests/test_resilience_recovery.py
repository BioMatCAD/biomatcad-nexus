"""Testes de resiliencia adicionais (Incremento 2.2, Fase D -- fechamento).

Cobre 3 lacunas reais encontradas na auditoria desta rodada, sem alterar geometria/golden
recipes/TopologyProviders/PicoGK/worker C#:

1. `recover_orphaned_jobs()` existia e ja era chamada por `process_queued_jobs()`
   (scripts/geometry_dispatcher.py), mas NUNCA tinha um teste direto provando que ela de fato
   recoloca um job `running` com heartbeat expirado de volta na fila -- só havia testes
   indiretos de OBSERVABILIDADE (que checam o relatorio de status, nao a acao de recuperacao
   em si).
2/3. `dispatch_job()` confiava cegamente no `stl_sha256` autorreportado pelo worker (só
   recalculava se ausente) e nunca verificava se o arquivo STL escrito era vazio -- corrigido
   em `geometry_job_service.py` nesta mesma rodada (ver commit da Fase D): agora SEMPRE
   recalcula o hash a partir dos bytes armazenados e trata tanto um arquivo vazio
   (`WORKER_PARTIAL_OUTPUT`) quanto uma divergencia de hash (`WORKER_CHECKSUM_MISMATCH`) como
   falha real do job, nunca persistindo um artefato nao confiavel como "succeeded".
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biomatcad_api.models.artifact import Artifact
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    ORPHAN_HEARTBEAT_TIMEOUT_SECONDS,
    claim_next_queued_job,
    create_design_run_and_job,
    dispatch_job,
    recover_orphaned_jobs,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter, sha256_of_bytes
from biomatcad_api.services.worker_client import WorkerResult

from .conftest import load_golden_recipe
from .factories import create_researcher

REPO_ROOT = Path(__file__).resolve().parents[3]


def _setup_project_and_recipe(db_session, user):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Resiliencia")
    db_session.add(project)
    db_session.flush()

    recipe_body = load_golden_recipe("block-gyroid-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Resiliencia",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()
    return project, recipe


def _create_queued_job(db_session, user, project, recipe, *, idempotency_key: str):
    _run, job, _created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key=idempotency_key,
    )
    return job


class _FixedContentWorkerClient:
    """Test double explicito -- NAO executa PicoGK real. Escreve exatamente `stl_content` e
    reporta `reported_sha256` (que pode ser deliberadamente ERRADO, para testar a deteccao de
    divergencia)."""

    def __init__(self, stl_content: bytes, reported_sha256: str | None) -> None:
        self.stl_content = stl_content
        self.reported_sha256 = reported_sha256

    def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
        if on_process_started is not None:
            on_process_started(0)
        output_dir.mkdir(parents=True, exist_ok=True)
        stl_path = output_dir / "fake.stl"
        stl_path.write_bytes(self.stl_content)
        return WorkerResult(
            stl_path=stl_path,
            thumbnail_path=None,
            metrics={
                "bounding_box_mm": [[0, 0, 0], [10, 10, 10]],
                "volume_mm3": 400.0,
                "porosity_pct_measured": 60.0,
                "surface_area_mm2": 950.5,
                "vertex_count_unique": 168,
                "triangle_count": 100,
                "is_watertight": True,
                "stl_reload_validation_passed": True,
            },
            worker_version="0.1.0-fake-test-double",
            dotnet_version="9.0.0",
            picogk_version="2.2.0",
            duration_seconds=0.1,
            effective_parameters=None,
            stl_sha256=self.reported_sha256,
            platform="fake-platform-for-tests",
        )


# ---------------------------------------------------------------------------
# 1) Recuperacao de job orfao (heartbeat expirado)
# ---------------------------------------------------------------------------


def test_recover_orphaned_jobs_recoloca_job_com_heartbeat_expirado_na_fila(db_session):
    user = create_researcher(db_session, email="resil-orphan1@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    job = _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-orphan-1")

    claimed = claim_next_queued_job(db_session, dispatcher_id="dispatcher-que-morreu")
    assert claimed is not None and claimed.id == job.id
    assert claimed.status == JobStatus.RUNNING
    original_attempt_number = claimed.attempt_number

    # Simula um dispatcher que travou/morreu no meio da execucao: o heartbeat parou de
    # avancar ha mais tempo que o limite configurado.
    claimed.heartbeat_at = datetime.now(timezone.utc) - timedelta(
        seconds=ORPHAN_HEARTBEAT_TIMEOUT_SECONDS + 30
    )
    db_session.commit()

    recovered_ids = recover_orphaned_jobs(db_session)

    assert recovered_ids == [job.id]
    db_session.refresh(claimed)
    assert claimed.status == JobStatus.QUEUED
    assert claimed.claimed_by_dispatcher_id is None
    assert claimed.claimed_at is None
    assert claimed.heartbeat_at is None
    assert claimed.started_at is None
    # Prova de "nova tentativa", nao uma reexecucao silenciosa do mesmo attempt.
    assert claimed.attempt_number == original_attempt_number + 1

    audit = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.event_type == "geometry_job_orphan_recovered")
        .all()
    )
    assert any(job.id in (a.description or "") for a in audit)

    # O job recuperado pode ser reivindicado de novo por QUALQUER dispatcher (inclusive um
    # diferente do que "morreu") -- prova de que a recuperacao realmente devolve o job à fila
    # utilizavel, nao apenas muda um campo isolado.
    reclaimed = claim_next_queued_job(db_session, dispatcher_id="dispatcher-novo")
    assert reclaimed is not None and reclaimed.id == job.id


def test_recover_orphaned_jobs_ignora_job_com_heartbeat_recente(db_session):
    user = create_researcher(db_session, email="resil-orphan2@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-orphan-2")

    claimed = claim_next_queued_job(db_session, dispatcher_id="dispatcher-vivo")
    assert claimed is not None
    # heartbeat_at já foi setado por claim_next_queued_job a um valor recente -- um dispatcher
    # genuinamente ativo NUNCA deve ser confundido com órfão.

    recovered_ids = recover_orphaned_jobs(db_session)

    assert recovered_ids == []
    db_session.refresh(claimed)
    assert claimed.status == JobStatus.RUNNING


def test_recover_orphaned_jobs_ignora_jobs_queued_e_succeeded(db_session):
    # Regra: só jobs em RUNNING com heartbeat parado são candidatos -- um job já succeeded ou
    # ainda queued nunca deve ser "recuperado" (não há nada de errado com eles).
    user = create_researcher(db_session, email="resil-orphan3@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    queued_job = _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-orphan-3")

    recovered_ids = recover_orphaned_jobs(db_session)
    assert recovered_ids == []
    db_session.refresh(queued_job)
    assert queued_job.status == JobStatus.QUEUED


# ---------------------------------------------------------------------------
# 2) Arquivo parcial (STL vazio) -- nunca persistido como "succeeded"
# ---------------------------------------------------------------------------


def test_dispatch_job_stl_vazio_e_tratado_como_falha_parcial_nunca_como_sucesso(db_session, tmp_path):
    user = create_researcher(db_session, email="resil-partial1@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-partial-1")
    claimed = claim_next_queued_job(db_session, dispatcher_id="d1")
    assert claimed is not None

    storage = LocalStorageAdapter(base_dir=tmp_path / "artifacts")
    result_job = dispatch_job(
        db_session,
        job_id=claimed.id,
        worker_client=_FixedContentWorkerClient(stl_content=b"", reported_sha256=None),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.FAILED
    assert result_job.error_code == "WORKER_PARTIAL_OUTPUT"
    assert "vazio" in (result_job.error_message or "")
    # Nenhum artefato foi persistido para um resultado geometrico incompleto.
    artifacts = db_session.query(Artifact).filter(Artifact.geometry_job_id == result_job.id).all()
    assert artifacts == []


# ---------------------------------------------------------------------------
# 3) Checksum divergente -- nunca persistido silenciosamente
# ---------------------------------------------------------------------------


def test_dispatch_job_checksum_divergente_do_worker_e_tratado_como_falha(db_session, tmp_path):
    user = create_researcher(db_session, email="resil-checksum1@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-checksum-1")
    claimed = claim_next_queued_job(db_session, dispatcher_id="d1")
    assert claimed is not None

    real_content = b"solid conteudo real\nendsolid conteudo real\n"
    wrong_hash = "f" * 64  # deliberadamente errado -- nunca coincide com sha256(real_content)
    assert sha256_of_bytes(real_content) != wrong_hash

    storage = LocalStorageAdapter(base_dir=tmp_path / "artifacts")
    result_job = dispatch_job(
        db_session,
        job_id=claimed.id,
        worker_client=_FixedContentWorkerClient(stl_content=real_content, reported_sha256=wrong_hash),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.FAILED
    assert result_job.error_code == "WORKER_CHECKSUM_MISMATCH"
    assert wrong_hash in (result_job.error_message or "")
    assert sha256_of_bytes(real_content) in (result_job.error_message or "")
    artifacts = db_session.query(Artifact).filter(Artifact.geometry_job_id == result_job.id).all()
    assert artifacts == []


def test_dispatch_job_usa_sempre_o_hash_recalculado_mesmo_quando_worker_acerta(db_session, tmp_path):
    # Quando o hash autorreportado BATE com o real, o job tem sucesso normalmente -- e o
    # Artifact persistido usa o hash RECALCULADO (nao apenas o valor confiado do worker, ainda
    # que sejam iguais neste caso -- defesa em profundidade: o valor de origem confiavel é
    # sempre o que foi de fato calculado sobre os bytes armazenados).
    user = create_researcher(db_session, email="resil-checksum2@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _create_queued_job(db_session, user, project, recipe, idempotency_key="idem-checksum-2")
    claimed = claim_next_queued_job(db_session, dispatcher_id="d1")
    assert claimed is not None

    real_content = b"solid conteudo correto\nendsolid conteudo correto\n"
    correct_hash = sha256_of_bytes(real_content)

    storage = LocalStorageAdapter(base_dir=tmp_path / "artifacts")
    result_job = dispatch_job(
        db_session,
        job_id=claimed.id,
        worker_client=_FixedContentWorkerClient(stl_content=real_content, reported_sha256=correct_hash),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.SUCCEEDED
    artifacts = db_session.query(Artifact).filter(Artifact.geometry_job_id == result_job.id).all()
    stl_artifacts = [a for a in artifacts if a.kind.value == "stl"]
    assert len(stl_artifacts) == 1
    assert stl_artifacts[0].sha256 == correct_hash
