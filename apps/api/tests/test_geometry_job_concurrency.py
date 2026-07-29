"""Teste de concorrência real da fila (Incremento 2.1.1, item 6): dois "dispatchers" (duas
conexões de banco de dados INDEPENDENTES, cada uma em sua própria thread) competem pela mesma
fila de GeometryJob simultaneamente. claim_next_queued_job() usa SELECT ... FOR UPDATE SKIP
LOCKED -- a propriedade que este teste verifica é que NENHUM job é reivindicado por mais de um
"dispatcher", e que TODOS os jobs acabam reivindicados exatamente uma vez.

Este teste usa conexões reais e independentes (SessionLocal() diretamente, não a fixture
db_session que compartilha uma única conexão/transação com o restante do teste) -- é
justamente a visibilidade entre conexões diferentes de um Postgres real que prova que o
mecanismo de bloqueio funciona (SQLite não suporta FOR UPDATE SKIP LOCKED da mesma forma e não
seria uma prova válida deste requisito)."""
from __future__ import annotations

import json
import threading

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import claim_next_queued_job
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

N_JOBS = 24


def test_two_concurrent_dispatchers_never_claim_the_same_job(engine):
    # `engine` (fixture de sessão do conftest.py) garante que Base.metadata.create_all já rodou
    # antes deste teste -- este teste não usa a fixture db_session (precisa de conexões
    # verdadeiramente independentes), então precisa desta dependência explícita para as tabelas existirem.
    setup_session = SessionLocal()
    created_job_ids: list[str] = []
    created_design_run_ids: list[str] = []
    created_recipe_id = None
    created_project_id = None
    try:
        user = create_researcher(setup_session, email="concurrency1@biomatcad.example")
        project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Concorrência")
        setup_session.add(project)
        setup_session.flush()
        created_project_id = project.id

        canonical_str, checksum = validate_and_canonicalize(GOOD_RECIPE_BODY)
        recipe = GeometryRecipe(
            organization_id=user.organization_id,
            project_id=project.id,
            created_by_user_id=user.id,
            name="Receita Concorrência",
            schema_version=GOOD_RECIPE_BODY["schema_version"],
            canonical_json=json.loads(canonical_str),
            checksum_sha256=checksum,
            version=1,
            status=RecipeStatus.VALIDATED,
        )
        setup_session.add(recipe)
        setup_session.flush()
        created_recipe_id = recipe.id

        for i in range(N_JOBS):
            design_run = DesignRun(
                organization_id=user.organization_id,
                project_id=project.id,
                recipe_id=recipe.id,
                material_id=None,
                created_by_user_id=user.id,
                idempotency_key=f"concurrency-job-{i}",
            )
            setup_session.add(design_run)
            setup_session.flush()
            job = GeometryJob(design_run_id=design_run.id, attempt_number=1, status=JobStatus.QUEUED)
            setup_session.add(job)
            setup_session.flush()
            created_job_ids.append(job.id)
            created_design_run_ids.append(design_run.id)

        # COMMIT real (não apenas flush) -- essencial para que as OUTRAS conexões (threads
        # abaixo) enxerguem estas linhas. Esta é justamente a diferença que torna este teste
        # uma prova de concorrência real entre conexões, e não apenas de lógica sequencial.
        setup_session.commit()

        claimed_by: dict[str, list[str]] = {"dispatcher-a": [], "dispatcher-b": []}
        errors: list[Exception] = []

        def run_dispatcher(name: str) -> None:
            session = SessionLocal()
            try:
                while True:
                    job = claim_next_queued_job(session, dispatcher_id=name)
                    if job is None:
                        break
                    claimed_by[name].append(job.id)
            except Exception as exc:  # noqa: BLE001 -- captura ampla proposital, reportada no teste principal
                errors.append(exc)
            finally:
                session.close()

        t_a = threading.Thread(target=run_dispatcher, args=("dispatcher-a",))
        t_b = threading.Thread(target=run_dispatcher, args=("dispatcher-b",))
        t_a.start()
        t_b.start()
        t_a.join(timeout=30)
        t_b.join(timeout=30)

        assert not errors, f"Dispatcher(s) levantaram exceção: {errors}"

        all_claimed = claimed_by["dispatcher-a"] + claimed_by["dispatcher-b"]
        assert len(all_claimed) == N_JOBS, (
            f"Esperado {N_JOBS} jobs reivindicados ao todo, obtido {len(all_claimed)} "
            f"(a={len(claimed_by['dispatcher-a'])}, b={len(claimed_by['dispatcher-b'])})"
        )
        assert len(set(all_claimed)) == N_JOBS, "Pelo menos um job foi reivindicado por AMBOS os dispatchers -- falha de exclusão mútua"
        assert set(all_claimed) == set(created_job_ids)

        # Confirma que todos os jobs de fato ficaram running e com claimed_by_dispatcher_id
        # coerente com quem os reivindicou nesta contabilidade em memória.
        verify_session = SessionLocal()
        try:
            for name, ids in claimed_by.items():
                for job_id in ids:
                    job_row = verify_session.get(GeometryJob, job_id)
                    assert job_row is not None
                    assert job_row.status == JobStatus.RUNNING
                    assert job_row.claimed_by_dispatcher_id == name
        finally:
            verify_session.close()
    finally:
        # Limpeza -- este teste faz commits reais fora do padrão de rollback usado pela fixture
        # db_session, então desfaz manualmente o que criou.
        cleanup_session = SessionLocal()
        try:
            if created_job_ids:
                cleanup_session.query(GeometryJob).filter(GeometryJob.id.in_(created_job_ids)).delete(synchronize_session=False)
            if created_design_run_ids:
                cleanup_session.query(DesignRun).filter(DesignRun.id.in_(created_design_run_ids)).delete(synchronize_session=False)
            if created_recipe_id:
                cleanup_session.query(GeometryRecipe).filter(GeometryRecipe.id == created_recipe_id).delete(synchronize_session=False)
            if created_project_id:
                cleanup_session.query(BioMatProject).filter(BioMatProject.id == created_project_id).delete(synchronize_session=False)
            cleanup_session.commit()
        finally:
            cleanup_session.close()
        setup_session.close()
