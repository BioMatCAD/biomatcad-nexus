"""Testes de cancelamento real (Incremento 2.1.1, item 7): idempotência, cancelamento de job
ainda na fila, e a corrida "conclusão vs. cancelamento" -- um job cujo worker termina (com
sucesso) exatamente na janela em que um cancelamento já havia sido solicitado nunca deve
terminar como 'succeeded', nem deve deixar artefatos persistidos."""
from __future__ import annotations

import json
from pathlib import Path

from biomatcad_api.models.geometry_job import GeometryJob, JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    claim_next_queued_job,
    create_design_run_and_job,
    dispatch_job,
    request_cancel,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import WorkerResult

from .factories import create_researcher

REPO_ROOT = Path(__file__).resolve().parents[3]

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


def _setup_project_and_recipe(db_session, user):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Cancelamento")
    db_session.add(project)
    db_session.flush()
    canonical_str, checksum = validate_and_canonicalize(GOOD_RECIPE_BODY)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Cancelamento",
        schema_version=GOOD_RECIPE_BODY["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()
    return project, recipe


class _RacesCancellationWorkerClient:
    """Test double que simula a corrida conclusão-vs-cancelamento: enquanto o worker
    "processa" (aqui, instantaneamente), um cancelamento chega por outra via (ex.: o usuário
    clicou cancelar) e é persistido no banco ANTES do worker retornar -- mas sem que o
    cancel_check do worker tenha tido a chance de observar a tempo (janela de corrida real,
    inevitável em sistemas distribuídos: o resultado e o pedido de cancelamento podem cruzar).
    Deliberadamente NÃO usa cancel_check para decidir nada -- é dispatch_job quem tem que
    protejer contra isto na re-checagem final antes de persistir."""

    def __init__(self, db_session, job_id: str, stl_content: bytes, racer_user_id: str) -> None:
        self.db_session = db_session
        self.job_id = job_id
        self.stl_content = stl_content
        self.racer_user_id = racer_user_id

    def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
        if on_process_started is not None:
            on_process_started(0)
        job_row = self.db_session.get(GeometryJob, self.job_id)
        request_cancel(self.db_session, job=job_row, cancelled_by_user_id=self.racer_user_id)

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
            worker_version="0.1.0-racer-test-double",
            dotnet_version="9.0.0",
            picogk_version="2.2.0",
            duration_seconds=0.05,
            stl_sha256="0" * 64,
            platform="fake-platform-for-tests",
        )


def test_cancel_queued_job_is_immediate(db_session):
    user = create_researcher(db_session, email="cancel1@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session, organization_id=user.organization_id, project_id=project.id, recipe_id=recipe.id,
        material_id=None, created_by_user_id=user.id, idempotency_key="cancel-queued",
    )
    cancelled = request_cancel(db_session, job=job, cancelled_by_user_id=user.id)
    assert cancelled.status == JobStatus.CANCELLED
    assert cancelled.cancel_requested_at is not None
    assert cancelled.finished_at is not None


def test_cancel_is_idempotent(db_session):
    user = create_researcher(db_session, email="cancel2@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session, organization_id=user.organization_id, project_id=project.id, recipe_id=recipe.id,
        material_id=None, created_by_user_id=user.id, idempotency_key="cancel-idem",
    )
    first = request_cancel(db_session, job=job, cancelled_by_user_id=user.id)
    second = request_cancel(db_session, job=first, cancelled_by_user_id=user.id)
    assert first.status == JobStatus.CANCELLED
    assert second.status == JobStatus.CANCELLED
    assert first.cancel_requested_at == second.cancel_requested_at


def test_completion_after_cancel_request_never_becomes_succeeded(db_session, tmp_path):
    """O teste central da Seção 7: o worker "termina" (com um resultado tecnicamente
    bem-sucedido) DEPOIS que um cancelamento já foi solicitado -- dispatch_job deve descartar
    esse resultado, marcar o job como CANCELLED (nunca SUCCEEDED), e não persistir nenhum
    Artifact."""
    user = create_researcher(db_session, email="cancel3@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session, organization_id=user.organization_id, project_id=project.id, recipe_id=recipe.id,
        material_id=None, created_by_user_id=user.id, idempotency_key="cancel-race",
    )

    claimed = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher")
    assert claimed is not None and claimed.id == job.id

    storage = LocalStorageAdapter(tmp_path / "artifacts")
    racer_client = _RacesCancellationWorkerClient(
        db_session, job_id=job.id, stl_content=b"solid demo\nendsolid demo\n", racer_user_id=user.id
    )
    result_job = dispatch_job(
        db_session, job_id=job.id, worker_client=racer_client, storage=storage,
        output_dir=tmp_path / "work", repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.CANCELLED, (
        "Um resultado que chega depois de um cancelamento solicitado nunca pode virar 'succeeded'"
    )
    assert result_job.metrics is None, "Job cancelado não deve ter métricas de um resultado descartado"

    from biomatcad_api.models.artifact import Artifact

    artifacts = db_session.query(Artifact).filter(Artifact.geometry_job_id == job.id).all()
    assert artifacts == [], "Nenhum artefato deveria ter sido persistido para um job cancelado"
