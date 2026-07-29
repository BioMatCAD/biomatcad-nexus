"""Orquestração de DesignRun/GeometryJob (Incremento 2.1, item 4; Incremento 2.1.1, itens 5, 6, 7).

A fila é a própria coluna GeometryJob.status -- não há fila em memória. Este módulo é o único
autorizado a fazer transições de estado (queued -> running -> succeeded|failed, ou -> cancelled).
O processo que consome a fila (scripts/geometry_dispatcher.py) é separado do processo da API,
conforme exigido explicitamente pelo Prompt Mestre para este incremento.

Incremento 2.1.1 acrescenta: (5) validação estrita de que projeto/receita/material pertencem à
MESMA organização (e a receita ao MESMO projeto) antes de criar qualquer DesignRun -- nunca
apenas confiando na checagem já feita no router; (6) claim atômico da fila via
SELECT ... FOR UPDATE SKIP LOCKED, com heartbeat e recuperação de job órfão; (7) cancelamento
real: interrompe o processo do worker em execução (não apenas marca o status) e protege contra
a corrida "job termina exatamente quando é cancelado" via re-checagem antes de persistir
qualquer artefato de sucesso.
"""
from __future__ import annotations

import platform
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NoReturn

from sqlalchemy.orm import Session

from biomatcad_api.models.artifact import Artifact, ArtifactKind
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.material import MaterialRecord
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.manifest_service import build_and_store_manifest
from biomatcad_api.services.storage import StorageAdapter, sha256_of_file
from biomatcad_api.services.worker_client import GeometryWorkerClient, WorkerExecutionError

HEARTBEAT_MIN_INTERVAL_SECONDS = 2.0
ORPHAN_HEARTBEAT_TIMEOUT_SECONDS = 120


class JobTransitionError(RuntimeError):
    """Levantado quando uma transição de estado de job é inválida (ex.: cancelar um job já
    finalizado, retentar um job ainda em execução)."""


class DesignRunAuthorizationError(RuntimeError):
    """Levantado quando projeto/receita/material não pertencem à mesma organização, a receita
    não pertence ao projeto informado, ou a receita não está validada (Incremento 2.1.1,
    item 5). Carrega um `reason_code` estruturado para o router traduzir em HTTP 403/422/404."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cleanup_output_dir(output_dir: Path) -> None:
    """Remove artefatos parciais de um job cancelado/falho/timeout (itens 3 e 7) -- melhor
    esforço, nunca mascara o erro original se a limpeza falhar."""
    try:
        if output_dir.exists():
            shutil.rmtree(output_dir, ignore_errors=True)
    except OSError:
        pass


def _authorize_design_run_inputs(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    recipe_id: str,
    material_id: str | None,
    actor_user_id: str,
) -> tuple[BioMatProject, GeometryRecipe]:
    """Camada 5 (Incremento 2.1.1): TODA criação de DesignRun passa por aqui, não apenas pelo
    router -- garante que a checagem não pode ser contornada chamando o serviço diretamente."""

    def _deny(reason_code: str, message: str) -> NoReturn:
        db.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                organization_id=organization_id,
                event_type="cross_organization_access_denied",
                description=f"{reason_code}: {message}",
            )
        )
        db.commit()
        raise DesignRunAuthorizationError(reason_code, message)

    project = db.get(BioMatProject, project_id)
    if project is None:
        _deny("PROJECT_NOT_FOUND", f"Projeto {project_id} não encontrado.")
        raise AssertionError("unreachable")  # _deny sempre levanta -- ajuda o mypy a estreitar o tipo
    if project.organization_id != organization_id:
        _deny("PROJECT_ORGANIZATION_MISMATCH", f"Projeto {project_id} não pertence à organização {organization_id}.")

    recipe = db.get(GeometryRecipe, recipe_id)
    if recipe is None:
        _deny("RECIPE_NOT_FOUND", f"Receita {recipe_id} não encontrada.")
        raise AssertionError("unreachable")
    if recipe.organization_id != organization_id:
        _deny("RECIPE_ORGANIZATION_MISMATCH", f"Receita {recipe_id} não pertence à organização {organization_id}.")
    if recipe.project_id != project_id:
        _deny("RECIPE_PROJECT_MISMATCH", f"Receita {recipe_id} não pertence ao projeto {project_id}.")
    if recipe.status != RecipeStatus.VALIDATED:
        _deny("RECIPE_NOT_VALIDATED", f"Receita {recipe_id} não está validada (status={recipe.status.value}).")

    if material_id is not None:
        material = db.get(MaterialRecord, material_id)
        if material is None:
            _deny("MATERIAL_NOT_FOUND", f"Material {material_id} não encontrado.")
            raise AssertionError("unreachable")
        if material.organization_id != organization_id:
            _deny("MATERIAL_ORGANIZATION_MISMATCH", f"Material {material_id} não pertence à organização {organization_id}.")

    return project, recipe


def create_design_run_and_job(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    recipe_id: str,
    material_id: str | None,
    created_by_user_id: str,
    idempotency_key: str,
) -> tuple[DesignRun, GeometryJob, bool]:
    """Idempotente: reenviar a mesma (organization_id, idempotency_key) nunca cria um segundo
    DesignRun/GeometryJob -- retorna o já existente com created=False. Levanta
    DesignRunAuthorizationError se projeto/receita/material não passarem na camada 5."""
    existing = (
        db.query(DesignRun)
        .filter(DesignRun.organization_id == organization_id, DesignRun.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        assert existing.jobs, "Invariante violada: DesignRun sempre deve ter ao menos um GeometryJob"
        latest = max(existing.jobs, key=lambda j: j.attempt_number)
        return existing, latest, False

    _authorize_design_run_inputs(
        db,
        organization_id=organization_id,
        project_id=project_id,
        recipe_id=recipe_id,
        material_id=material_id,
        actor_user_id=created_by_user_id,
    )

    design_run = DesignRun(
        organization_id=organization_id,
        project_id=project_id,
        recipe_id=recipe_id,
        material_id=material_id,
        created_by_user_id=created_by_user_id,
        idempotency_key=idempotency_key,
    )
    db.add(design_run)
    db.flush()

    job = GeometryJob(design_run_id=design_run.id, attempt_number=1, status=JobStatus.QUEUED)
    db.add(job)
    db.flush()

    db.add(
        AuditEvent(
            actor_user_id=created_by_user_id,
            organization_id=organization_id,
            event_type="geometry_job_created",
            description=f"Job geométrico {job.id} criado para design_run {design_run.id}.",
        )
    )
    db.commit()
    db.refresh(design_run)
    db.refresh(job)
    return design_run, job, True


def request_cancel(db: Session, *, job: GeometryJob, cancelled_by_user_id: str) -> GeometryJob:
    """Incremento 2.1.1 (item 7): marca a INTENÇÃO de cancelamento. Se o job ainda está na fila
    (queued, nenhum processo rodando), cancela imediatamente. Se está em execução (running), só
    sinaliza -- o dispatcher que está de fato rodando o worker é quem observa o sinal (via
    cancel_check em worker_client.execute) e mata o processo; a transição final para CANCELLED
    acontece então em _finalize_cancelled. Idempotente: chamar duas vezes não é erro."""
    if job.status == JobStatus.CANCELLED:
        # Já cancelado (seja porque já estava queued e foi cancelado direto, seja porque o
        # dispatcher já finalizou o cancelamento de um job que estava running) -- idempotente,
        # nunca um erro: cancelar algo que já está cancelado é sempre um no-op bem-sucedido.
        return job
    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        raise JobTransitionError(f"Job {job.id} não pode ser cancelado no estado {job.status.value}.")

    if job.cancel_requested_at is not None:
        # cancel_requested_at já setado mas o job ainda está running (o dispatcher ainda não
        # finalizou) -- idempotente, não duplica AuditEvent nem re-decide estado.
        return job

    now = _utcnow()
    job.cancel_requested_at = now
    job.cancelled_by_user_id = cancelled_by_user_id
    if job.status == JobStatus.QUEUED:
        # Nada em execução para matar -- cancela diretamente.
        job.status = JobStatus.CANCELLED
        job.finished_at = now
    design_run = db.get(DesignRun, job.design_run_id)
    db.add(
        AuditEvent(
            actor_user_id=cancelled_by_user_id,
            organization_id=design_run.organization_id if design_run else None,
            event_type="geometry_job_cancel_requested",
            description=f"Cancelamento solicitado para job geométrico {job.id} (estado no momento: {job.status.value}).",
        )
    )
    db.commit()
    db.refresh(job)
    return job


# Mantido por compatibilidade com chamadores existentes (rota HTTP) -- delega para
# request_cancel, que é o nome mais preciso desde que o cancelamento deixou de ser instantâneo.
def cancel_job(db: Session, *, job: GeometryJob, cancelled_by_user_id: str) -> GeometryJob:
    return request_cancel(db, job=job, cancelled_by_user_id=cancelled_by_user_id)


def retry_job(db: Session, *, design_run: DesignRun, requested_by_user_id: str) -> GeometryJob:
    latest = max(design_run.jobs, key=lambda j: j.attempt_number)
    if latest.status not in (JobStatus.FAILED, JobStatus.CANCELLED):
        raise JobTransitionError(
            f"Só é possível retentar um job falho/cancelado (estado atual: {latest.status.value})."
        )
    new_job = GeometryJob(
        design_run_id=design_run.id, attempt_number=latest.attempt_number + 1, status=JobStatus.QUEUED
    )
    db.add(new_job)
    db.add(
        AuditEvent(
            actor_user_id=requested_by_user_id,
            organization_id=design_run.organization_id,
            event_type="geometry_job_retried",
            description=f"Nova tentativa ({new_job.attempt_number}) criada para design_run {design_run.id}.",
        )
    )
    db.commit()
    db.refresh(new_job)
    return new_job


def claim_next_queued_job(db: Session, *, dispatcher_id: str) -> GeometryJob | None:
    """Incremento 2.1.1 (item 6): reivindica atomicamente o job mais antigo na fila usando
    `SELECT ... FOR UPDATE SKIP LOCKED` -- se dois dispatchers chamarem isto concorrentemente,
    o Postgres garante que cada um pega uma linha diferente (ou None se não houver mais), nunca
    o mesmo job duas vezes. Já transiciona queued -> running como parte da mesma reivindicação
    (não há uma janela entre "ver que está queued" e "marcar como running" em que outro
    dispatcher poderia intervir)."""
    job = (
        db.query(GeometryJob)
        .filter(GeometryJob.status == JobStatus.QUEUED)
        .order_by(GeometryJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    now = _utcnow()
    job.status = JobStatus.RUNNING
    job.started_at = now
    job.claimed_by_dispatcher_id = dispatcher_id
    job.claimed_at = now
    job.heartbeat_at = now
    job.progress_pct = 5
    db.commit()
    db.refresh(job)
    return job


def recover_orphaned_jobs(
    db: Session, *, heartbeat_timeout_seconds: int = ORPHAN_HEARTBEAT_TIMEOUT_SECONDS
) -> list[str]:
    """Incremento 2.1.1 (item 6): jobs em `running` cujo heartbeat parou de avançar (dispatcher
    morreu/travou sem finalizar) são recolocados na fila (queued) para uma nova tentativa por
    QUALQUER dispatcher disponível -- nunca ficam presos em running para sempre. Retorna os IDs
    recuperados (para log/observabilidade do chamador)."""
    threshold = _utcnow() - timedelta(seconds=heartbeat_timeout_seconds)
    stuck = (
        db.query(GeometryJob)
        .filter(
            GeometryJob.status == JobStatus.RUNNING,
            (GeometryJob.heartbeat_at.is_(None)) | (GeometryJob.heartbeat_at < threshold),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    recovered_ids = []
    for job in stuck:
        job.status = JobStatus.QUEUED
        job.claimed_by_dispatcher_id = None
        job.claimed_at = None
        job.heartbeat_at = None
        job.started_at = None
        job.attempt_number += 1
        design_run = db.get(DesignRun, job.design_run_id)
        db.add(
            AuditEvent(
                organization_id=design_run.organization_id if design_run else None,
                event_type="geometry_job_orphan_recovered",
                description=f"Job {job.id} recuperado de estado órfão (heartbeat expirado) e recolocado na fila.",
            )
        )
        recovered_ids.append(job.id)
    if recovered_ids:
        db.commit()
    return recovered_ids


def _mark_failed(db: Session, job: GeometryJob, *, error_code: str, error_message: str) -> None:
    job.status = JobStatus.FAILED
    job.finished_at = _utcnow()
    job.error_code = error_code
    # Erro sanitizado: nunca propaga stdout/stderr bruto do worker para o campo público de
    # error_message (isso vai em AuditEvent/hardware_info se necessário depurar internamente).
    job.error_message = error_message[:1000]
    design_run = db.get(DesignRun, job.design_run_id)
    assert design_run is not None
    db.add(
        AuditEvent(
            organization_id=design_run.organization_id,
            event_type="geometry_job_failed",
            description=f"Job {job.id} falhou: {error_code}.",
        )
    )
    db.commit()
    db.refresh(job)


def _finalize_cancelled(db: Session, job: GeometryJob, output_dir: Path) -> None:
    """Incremento 2.1.1 (item 7): transição final para CANCELLED -- usada tanto quando o worker
    foi de fato interrompido (WORKER_CANCELLED) quanto quando ele terminou (com sucesso ou
    falha) mas um cancelamento já havia sido solicitado antes da persistência dos artefatos
    (corrida conclusão-vs-cancelamento). Remove qualquer artefato parcial em disco -- nunca
    persiste um Artifact para um job cancelado."""
    _cleanup_output_dir(output_dir)
    if job.status != JobStatus.CANCELLED:
        job.status = JobStatus.CANCELLED
    if job.finished_at is None:
        job.finished_at = _utcnow()
    design_run = db.get(DesignRun, job.design_run_id)
    db.add(
        AuditEvent(
            organization_id=design_run.organization_id if design_run else None,
            event_type="geometry_job_cancelled",
            description=f"Job geométrico {job.id} cancelado (processo do worker encerrado ou resultado descartado por corrida com cancelamento).",
        )
    )
    db.commit()
    db.refresh(job)


def _mark_succeeded(db: Session, job: GeometryJob, *, metrics: dict, versions: dict, duration_seconds: float) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = _utcnow()
    job.progress_pct = 100
    job.metrics = metrics
    job.worker_version = versions.get("worker_version")
    job.dotnet_version = versions.get("dotnet_version")
    job.picogk_version = versions.get("picogk_version")
    job.duration_seconds = duration_seconds
    job.hardware_info = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }
    design_run = db.get(DesignRun, job.design_run_id)
    assert design_run is not None
    db.add(
        AuditEvent(
            organization_id=design_run.organization_id,
            event_type="geometry_job_succeeded",
            description=f"Job {job.id} concluído com sucesso.",
        )
    )
    db.commit()
    db.refresh(job)


def dispatch_job(
    db: Session,
    *,
    job_id: str,
    worker_client: GeometryWorkerClient,
    storage: StorageAdapter,
    output_dir: Path,
    repo_root: Path,
) -> GeometryJob:
    """Executa um job JÁ REIVINDICADO (running) por claim_next_queued_job: chama o worker, e na
    volta persiste artefatos/métricas/manifesto (sucesso) ou erro estruturado sanitizado
    (falha) -- nunca fabrica um resultado quando o worker real falha. Incremento 2.1.1: também
    conecta o mecanismo real de cancelamento (cancel_check) e protege contra a corrida
    conclusão-vs-cancelamento antes de persistir qualquer artefato."""
    job_raw = db.get(GeometryJob, job_id)
    assert job_raw is not None, f"GeometryJob {job_id} não encontrado"
    job: GeometryJob = job_raw
    if job.status != JobStatus.RUNNING:
        raise JobTransitionError(
            f"Job {job_id} não está running (estado atual: {job.status.value}) -- "
            "dispatch_job espera um job já reivindicado por claim_next_queued_job."
        )

    design_run = db.get(DesignRun, job.design_run_id)
    assert design_run is not None
    recipe = db.get(GeometryRecipe, design_run.recipe_id)
    assert recipe is not None

    last_heartbeat_write = {"at": job.heartbeat_at or _utcnow()}

    def cancel_check() -> bool:
        now = _utcnow()
        if (now - last_heartbeat_write["at"]).total_seconds() >= HEARTBEAT_MIN_INTERVAL_SECONDS:
            job.heartbeat_at = now
            db.commit()
            last_heartbeat_write["at"] = now
        db.expire(job)
        fresh = db.get(GeometryJob, job_id)
        return fresh is not None and fresh.cancel_requested_at is not None

    def on_process_started(pid: int) -> None:
        job.worker_pid = pid
        db.commit()

    try:
        result = worker_client.execute(
            recipe_canonical=recipe.canonical_json,
            job_id=job.id,
            output_dir=output_dir,
            cancel_check=cancel_check,
            on_process_started=on_process_started,
        )
    except WorkerExecutionError as exc:
        db.expire(job)
        job_after_error = db.get(GeometryJob, job_id)
        assert job_after_error is not None, f"GeometryJob {job_id} desapareceu durante a execução"
        if exc.error_code == "WORKER_CANCELLED" or job_after_error.cancel_requested_at is not None:
            _finalize_cancelled(db, job_after_error, output_dir)
            return job_after_error
        _mark_failed(db, job_after_error, error_code=exc.error_code, error_message=exc.message)
        _cleanup_output_dir(output_dir)
        return job_after_error

    # Checagem final da corrida conclusão-vs-cancelamento (item 7): re-lê o estado mais recente
    # ANTES de persistir qualquer artefato de sucesso. Se um cancelamento foi solicitado entre a
    # última verificação de cancel_check e o retorno do worker, o resultado é descartado.
    db.expire(job)
    job_after_success = db.get(GeometryJob, job_id)
    assert job_after_success is not None, f"GeometryJob {job_id} desapareceu durante a execução"
    if job_after_success.cancel_requested_at is not None:
        _finalize_cancelled(db, job_after_success, output_dir)
        return job_after_success
    job = job_after_success

    stl_bytes = result.stl_path.read_bytes()
    stl_key = f"jobs/{job.id}/scaffold.stl"
    storage.put(stl_key, stl_bytes)
    db.add(
        Artifact(
            geometry_job_id=job.id,
            kind=ArtifactKind.STL,
            storage_key=stl_key,
            sha256=result.stl_sha256 or sha256_of_file(result.stl_path),
            size_bytes=len(stl_bytes),
        )
    )

    if result.thumbnail_path is not None and result.thumbnail_path.exists():
        thumb_bytes = result.thumbnail_path.read_bytes()
        thumb_key = f"jobs/{job.id}/thumbnail.png"
        storage.put(thumb_key, thumb_bytes)
        db.add(
            Artifact(
                geometry_job_id=job.id,
                kind=ArtifactKind.THUMBNAIL,
                storage_key=thumb_key,
                sha256=sha256_of_file(result.thumbnail_path),
                size_bytes=len(thumb_bytes),
            )
        )

    versions = {
        "worker_version": result.worker_version,
        "dotnet_version": result.dotnet_version,
        "picogk_version": result.picogk_version,
    }
    _mark_succeeded(db, job, metrics=result.metrics, versions=versions, duration_seconds=result.duration_seconds)

    build_and_store_manifest(
        db,
        job=job,
        design_run=design_run,
        recipe=recipe,
        versions=versions,
        duration_seconds=result.duration_seconds,
        storage=storage,
        repo_root=repo_root,
        effective_parameters=result.effective_parameters,
        platform_info=result.platform,
        stl_sha256=result.stl_sha256,
    )
    return job
