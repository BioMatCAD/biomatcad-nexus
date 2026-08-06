"""Testes de orquestração de DesignRun/GeometryJob (Incremento 2.1, item 8): idempotência,
transições de status, cancelamento, retry, e o caminho de falha controlada do worker.

IMPORTANTE (transparência): FakeWorkerClient e AlwaysFailsWorkerClient são test doubles que
NÃO alegam executar o PicoGK real -- servem apenas para validar a lógica de orquestração
(persistência de artefato/checksum/manifesto/métricas). O teste
`test_dispatch_job_real_worker_reflects_environment_honestly`, ao final deste arquivo, usa o
DotnetPicoGkWorkerClient REAL contra o binário REAL compilado -- NÃO assume mais que o
resultado é sempre uma falha.

Correção real (rodada Voronoi, auditoria da execução Windows 20260806-112714):
o teste anterior (`test_dispatch_job_real_worker_fails_in_blocked_environment`) hardcoded
`assert result_job.status == JobStatus.FAILED`, uma premissa válida SÓ no sandbox Linux deste
projeto (onde o runtime nativo do PicoGK é bloqueado, ADR-0007). Rodado de verdade no Windows
do usuário (onde PicoGK funciona), o mesmo teste falhava -- não por um bug no produto, mas
porque o job REALMENTE tinha sucesso ali, contradizendo a asserção fixa do teste. O teste
corrigido abaixo aceita os dois desfechos REAIS possíveis, dependendo do ambiente onde roda, e
prova algo forte em cada um: se FALHOU, o error_code precisa ser um dos códigos documentados do
bloqueio (nunca um erro genérico/inesperado); se TEVE SUCESSO, prova que a execução foi
genuína (STL não-vazio realmente gravado em disco, métricas e versões reais presentes) -- ou
seja, o teste fica mais valioso em Windows (finalmente prova execução real) em vez de
simplesmente pular a cobertura lá.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    JobTransitionError,
    cancel_job,
    claim_next_queued_job,
    create_design_run_and_job,
    dispatch_job,
    retry_job,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import (
    DotnetPicoGkWorkerClient,
    WorkerExecutionError,
    WorkerResult,
)

from .conftest import load_golden_recipe
from .factories import create_researcher

REPO_ROOT = Path(__file__).resolve().parents[3]


def _setup_project_and_recipe(db_session, user):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Teste")
    db_session.add(project)
    db_session.flush()

    recipe_body = load_golden_recipe("block-gyroid-v1")
    import json

    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Teste",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()
    return project, recipe


def test_create_design_run_and_job_is_idempotent(db_session):
    user = create_researcher(db_session, email="orch1@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)

    run1, job1, created1 = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-1",
    )
    run2, job2, created2 = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-1",
    )

    assert created1 is True
    assert created2 is False
    assert run1.id == run2.id
    assert job1.id == job2.id
    assert job1.status == JobStatus.QUEUED


def test_cancel_job_then_cancel_again_is_idempotent_not_an_error(db_session):
    """Incremento 2.1.1 (item 7): cancelamento deve permanecer idempotente -- cancelar um job já
    cancelado é um no-op bem-sucedido, não um erro (corrigido em relação ao Incremento 2.1, que
    levantava JobTransitionError na segunda chamada)."""
    user = create_researcher(db_session, email="orch2@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-cancel",
    )

    cancelled = cancel_job(db_session, job=job, cancelled_by_user_id=user.id)
    assert cancelled.status == JobStatus.CANCELLED

    cancelled_again = cancel_job(db_session, job=cancelled, cancelled_by_user_id=user.id)
    assert cancelled_again.status == JobStatus.CANCELLED
    assert cancelled_again.id == cancelled.id


def test_cancel_already_succeeded_job_raises(db_session, tmp_path):
    """Cancelar um job que já SUCCEEDED (por outra razão que não cancelamento) continua sendo
    um erro -- só o estado CANCELLED em si é idempotente, não qualquer estado terminal."""
    from biomatcad_api.services.geometry_job_service import claim_next_queued_job
    from biomatcad_api.services.storage import LocalStorageAdapter

    user = create_researcher(db_session, email="orch2b@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-cancel-succeeded",
    )
    claim_next_queued_job(db_session, dispatcher_id="test-dispatcher")
    storage = LocalStorageAdapter(tmp_path / "artifacts")
    succeeded_job = dispatch_job(
        db_session, job_id=job.id, worker_client=FakeWorkerClient(), storage=storage,
        output_dir=tmp_path / "work", repo_root=REPO_ROOT,
    )
    assert succeeded_job.status == JobStatus.SUCCEEDED

    with pytest.raises(JobTransitionError):
        cancel_job(db_session, job=succeeded_job, cancelled_by_user_id=user.id)


def test_retry_rejected_while_queued_allowed_after_cancel(db_session):
    user = create_researcher(db_session, email="orch3@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    design_run, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-retry",
    )

    with pytest.raises(JobTransitionError):
        retry_job(db_session, design_run=design_run, requested_by_user_id=user.id)

    cancel_job(db_session, job=job, cancelled_by_user_id=user.id)
    db_session.refresh(design_run)
    new_job = retry_job(db_session, design_run=design_run, requested_by_user_id=user.id)
    assert new_job.attempt_number == 2
    assert new_job.status == JobStatus.QUEUED


class FakeWorkerClient:
    """Test double explícito -- NÃO executa PicoGK real. Ver docstring do módulo. Aceita
    (e ignora, exceto quando testado explicitamente) os parâmetros cancel_check/
    on_process_started introduzidos no Incremento 2.1.1 para manter compatibilidade com a
    assinatura real de GeometryWorkerClient.execute."""

    def __init__(self, stl_content: bytes = b"solid fake\nendsolid fake\n") -> None:
        self.stl_content = stl_content

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
            effective_parameters={"wall_thickness_requested_mm": 0.6, "wall_thickness_effective_mm": 0.6},
            stl_sha256="0" * 64,
            platform="fake-platform-for-tests",
        )


class AlwaysFailsWorkerClient:
    """Test double que sempre falha -- valida o caminho de erro sem depender do bloqueio real."""

    def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
        raise WorkerExecutionError("WORKER_SIMULATED_FAILURE", "Falha simulada para teste.")


def test_dispatch_job_success_path_persists_artifacts_checksum_manifest_metrics(db_session, tmp_path):
    user = create_researcher(db_session, email="orch4@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-success",
    )

    storage = LocalStorageAdapter(tmp_path / "artifacts")
    claimed = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher")
    assert claimed is not None and claimed.id == job.id
    result_job = dispatch_job(
        db_session,
        job_id=job.id,
        worker_client=FakeWorkerClient(),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.SUCCEEDED
    assert result_job.metrics["volume_mm3"] == 400.0
    assert result_job.worker_version == "0.1.0-fake-test-double"

    from biomatcad_api.models.artifact import Artifact, ArtifactManifest

    artifacts = db_session.query(Artifact).filter(Artifact.geometry_job_id == job.id).all()
    kinds = {a.kind.value for a in artifacts}
    assert "stl" in kinds and "manifest" in kinds
    for artifact in artifacts:
        assert len(artifact.sha256) == 64

    manifest = db_session.query(ArtifactManifest).filter(ArtifactManifest.geometry_job_id == job.id).first()
    assert manifest is not None
    assert manifest.manifest_json["recipe_canonical"]["seed"] == recipe.canonical_json["seed"]
    assert len(manifest.manifest_sha256) == 64


def test_dispatch_job_failure_path_marks_job_failed_not_fabricated_success(db_session, tmp_path):
    user = create_researcher(db_session, email="orch5@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-fail",
    )

    storage = LocalStorageAdapter(tmp_path / "artifacts")
    claimed = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher")
    assert claimed is not None and claimed.id == job.id
    result_job = dispatch_job(
        db_session,
        job_id=job.id,
        worker_client=AlwaysFailsWorkerClient(),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.FAILED
    assert result_job.error_code == "WORKER_SIMULATED_FAILURE"
    assert result_job.metrics is None


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="Requer .NET SDK instalado (dotnet no PATH).")
def test_dispatch_job_real_worker_reflects_environment_honestly(db_session, tmp_path):
    """Invoca o DotnetPicoGkWorkerClient de verdade contra o binário REAL compilado de
    apps/geometry-worker -- não um test double. Multiplataforma por construção (ver docstring
    do módulo): não assume de antemão se o PicoGK está bloqueado (Linux, ADR-0007) ou
    disponível (Windows real) -- prova a consequência correta para QUALQUER um dos dois
    desfechos, em vez de hardcodar um deles."""
    user = create_researcher(db_session, email="orch6@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-real-worker",
    )

    storage = LocalStorageAdapter(tmp_path / "artifacts")
    worker_client = DotnetPicoGkWorkerClient(repo_root=REPO_ROOT)
    claimed = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher")
    assert claimed is not None and claimed.id == job.id
    result_job = dispatch_job(
        db_session,
        job_id=job.id,
        worker_client=worker_client,
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status in (JobStatus.FAILED, JobStatus.SUCCEEDED), (
        f"desfecho inesperado: {result_job.status!r} (esperado FAILED com um error_code "
        "documentado do bloqueio do PicoGK, OU SUCCEEDED com evidência real de execução)"
    )

    if result_job.status == JobStatus.FAILED:
        # Ambiente onde o PicoGK está genuinamente bloqueado (ex.: este sandbox Linux,
        # ADR-0007) -- o error_code precisa ser um dos códigos DOCUMENTADOS do bloqueio, nunca
        # um erro genérico/inesperado (isso continuaria a pegar uma regressão real).
        assert result_job.error_code in (
            "WORKER_RUNTIME_UNAVAILABLE",
            "WORKER_BINARY_NOT_BUILT",
            "DOTNET_RUNTIME_NOT_FOUND",
        )
    else:
        # Ambiente onde o PicoGK real funciona (ex.: Windows do usuário) -- prova que o
        # sucesso é GENUÍNO, não apenas um status bem-sucedido não verificado: STL real e
        # não-trivial gravado no storage, métricas e versões reais presentes.
        from biomatcad_api.models.artifact import Artifact, ArtifactKind

        stl_artifact = (
            db_session.query(Artifact)
            .filter(Artifact.geometry_job_id == result_job.id, Artifact.kind == ArtifactKind.STL)
            .first()
        )
        assert stl_artifact is not None, "job SUCCEEDED mas nenhum Artifact STL foi persistido"
        assert stl_artifact.size_bytes > 0
        stl_bytes = storage.get(stl_artifact.storage_key)
        assert len(stl_bytes) == stl_artifact.size_bytes
        assert result_job.metrics is not None
        assert result_job.worker_version is not None
        assert result_job.dotnet_version is not None
        assert result_job.picogk_version is not None
