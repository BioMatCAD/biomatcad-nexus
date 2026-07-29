"""Orquestração de DesignRun/GeometryJob (Incremento 2.1, item 4).

A fila é a própria coluna GeometryJob.status -- não há fila em memória. Este módulo é o único
autorizado a fazer transições de estado (queued -> running -> succeeded|failed, ou -> cancelled).
O processo que consome a fila (scripts/geometry_dispatcher.py) é separado do processo da API,
conforme exigido explicitamente pelo Prompt Mestre para este incremento.
"""
from __future__ import annotations

import platform
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from biomatcad_api.models.artifact import Artifact, ArtifactKind
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe
from biomatcad_api.services.manifest_service import build_and_store_manifest
from biomatcad_api.services.storage import StorageAdapter, sha256_of_file
from biomatcad_api.services.worker_client import GeometryWorkerClient, WorkerExecutionError


class JobTransitionError(RuntimeError):
    """Levantado quando uma transição de estado de job é inválida (ex.: cancelar um job já
    finalizado, retentar um job ainda em execução)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    DesignRun/GeometryJob -- retorna o já existente com created=False."""
    existing = (
        db.query(DesignRun)
        .filter(DesignRun.organization_id == organization_id, DesignRun.idempotency_key == idempotency_key)
        .first()
    )
    if existing is not None:
        assert existing.jobs, "Invariante violada: DesignRun sempre deve ter ao menos um GeometryJob"
        latest = max(existing.jobs, key=lambda j: j.attempt_number)
        return existing, latest, False

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


def cancel_job(db: Session, *, job: GeometryJob, cancelled_by_user_id: str) -> GeometryJob:
    if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise JobTransitionError(f"Job {job.id} não pode ser cancelado no estado {job.status.value}.")
    job.status = JobStatus.CANCELLED
    job.finished_at = _utcnow()
    job.cancelled_by_user_id = cancelled_by_user_id
    db.add(
        AuditEvent(
            actor_user_id=cancelled_by_user_id,
            organization_id=None,
            event_type="geometry_job_cancelled",
            description=f"Job geométrico {job.id} cancelado.",
        )
    )
    db.commit()
    db.refresh(job)
    return job


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


def _mark_running(db: Session, job: GeometryJob) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = _utcnow()
    job.progress_pct = 5
    db.commit()
    db.refresh(job)


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
    """Orquestra uma execução completa: marca running, chama o worker, e na volta persiste
    artefatos/métricas/manifesto (sucesso) ou erro estruturado sanitizado (falha) -- nunca
    fabrica um resultado quando o worker real falha."""
    job = db.get(GeometryJob, job_id)
    assert job is not None, f"GeometryJob {job_id} não encontrado"
    if job.status != JobStatus.QUEUED:
        raise JobTransitionError(f"Job {job_id} não está queued (estado atual: {job.status.value}).")

    design_run = db.get(DesignRun, job.design_run_id)
    assert design_run is not None
    recipe = db.get(GeometryRecipe, design_run.recipe_id)
    assert recipe is not None

    _mark_running(db, job)

    try:
        result = worker_client.execute(
            recipe_canonical=recipe.canonical_json, job_id=job.id, output_dir=output_dir
        )
    except WorkerExecutionError as exc:
        _mark_failed(db, job, error_code=exc.error_code, error_message=exc.message)
        return job

    stl_bytes = result.stl_path.read_bytes()
    stl_key = f"jobs/{job.id}/scaffold.stl"
    storage.put(stl_key, stl_bytes)
    db.add(
        Artifact(
            geometry_job_id=job.id,
            kind=ArtifactKind.STL,
            storage_key=stl_key,
            sha256=sha256_of_file(result.stl_path),
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
    )
    return job
