"""Verificações reais de observabilidade (Incremento 2.2, Seção 7).

Regra de ouro deste módulo: NENHUMA função aqui pode retornar "healthy" sem ter, de fato,
checado algo (conexão real ao banco, arquivo real no disco, contagem real na tabela, PID real
do sistema operacional). Nunca inventa um estado -- na dúvida ou erro de checagem, retorna
"unknown" ou "unavailable" com o motivo em `detail`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from biomatcad_api import __version__
from biomatcad_api.config import Settings
from biomatcad_api.models.geometry_job import GeometryJob, JobStatus
from biomatcad_api.schemas.observability import (
    ActiveJobSummary,
    ApiStatus,
    DatabaseStatus,
    DispatcherStatus,
    FailedJobSummary,
    ObservabilityStatusResponse,
    QueueStatus,
    StorageStatus,
    VersionsInfo,
    WorkerStatus,
)
from biomatcad_api.services.recipe_service import schema_version
from biomatcad_api.services.worker_client import _find_worker_dll

# Mesmo limite usado por recover_orphaned_jobs() (services/geometry_job_service.py) para
# decidir se um job "running" está órfão -- reaproveitado aqui para reportar
# heartbeat_stale=True em jobs ativos, e para decidir o estado do worker/dispatcher.
_HEARTBEAT_STALE_SECONDS = 120

# Limite de "quantos jobs falhos recentes" o painel mostra -- evita respostas gigantes; o
# histórico completo continua disponível via GET /api/v1/design-runs/{id}/jobs (Incremento 2.1).
_MAX_FAILED_JOBS_SHOWN = 10

# Considera o dispatcher "stale" se seu último poll registrado no status file for mais antigo
# que este limite -- mesma semântica de "heartbeat parado" aplicada ao PRÓPRIO dispatcher (não
# só aos jobs que ele processa).
_DISPATCHER_STALE_SECONDS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def check_database(db: Session) -> DatabaseStatus:
    """Conexão real: executa 'SELECT 1' de verdade -- nunca assume 'healthy' só porque a
    sessão foi injetada com sucesso pelo FastAPI (isso só prova que o objeto Session existe,
    não que o banco responde)."""
    try:
        db.execute(select(func.count()).select_from(GeometryJob))
        return DatabaseStatus(state="healthy", detail="Conexão e consulta real bem-sucedidas.")
    except SQLAlchemyError as exc:
        return DatabaseStatus(state="unavailable", detail=f"Falha real na consulta: {exc}")


def _dispatcher_status_file_path(settings: Settings) -> Path:
    # Mesmo cálculo de scripts/geometry_dispatcher.py::_status_file_path -- mantido em duas
    # cópias de propósito (API e script são processos/pacotes independentes), mas
    # DELIBERADAMENTE idêntico; um teste de regressão (test_observability.py) trava os dois
    # contra o mesmo valor esperado para nunca divergirem silenciosamente.
    return Path(settings.artifact_storage_dir) / "_dispatcher" / "status.json"


def check_dispatcher(settings: Settings) -> DispatcherStatus:
    status_file = _dispatcher_status_file_path(settings)
    if not status_file.exists():
        return DispatcherStatus(
            state="unavailable",
            detail=f"Arquivo de status não encontrado em {status_file} -- dispatcher nunca rodou ou não está em modo contínuo.",
        )
    try:
        raw = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return DispatcherStatus(state="unknown", detail=f"Arquivo de status ilegível: {exc}")

    dispatcher_id = raw.get("dispatcher_id")
    pid = raw.get("pid")
    phase = raw.get("phase")
    last_poll_at_raw = raw.get("last_poll_at")
    jobs_processed_total = raw.get("jobs_processed_total")
    poll_interval = raw.get("current_poll_interval_seconds")
    state_field = raw.get("state")

    if state_field == "stopped":
        return DispatcherStatus(
            state="stopped",
            detail="Dispatcher encerrado graciosamente (último estado registrado: 'stopped').",
            dispatcher_id=dispatcher_id,
            pid=pid,
            phase=phase,
            last_poll_at=last_poll_at_raw,
            jobs_processed_total=jobs_processed_total,
            current_poll_interval_seconds=poll_interval,
        )

    if not last_poll_at_raw:
        return DispatcherStatus(
            state="unknown",
            detail="Status file sem 'last_poll_at' -- formato inesperado.",
            dispatcher_id=dispatcher_id,
            pid=pid,
        )

    try:
        last_poll_at = datetime.fromisoformat(last_poll_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return DispatcherStatus(state="unknown", detail=f"'last_poll_at' ilegível: {last_poll_at_raw}", dispatcher_id=dispatcher_id, pid=pid)

    age_seconds = (_utcnow() - last_poll_at).total_seconds()
    if age_seconds > _DISPATCHER_STALE_SECONDS:
        state: str = "stale"
        detail = f"Último poll há {age_seconds:.0f}s (limite {_DISPATCHER_STALE_SECONDS}s) -- dispatcher pode estar travado ou morto sem atualizar o status file."
    else:
        state = "healthy"
        detail = f"Último poll há {age_seconds:.0f}s, fase '{phase}'."

    return DispatcherStatus(
        state=state,  # type: ignore[arg-type]
        detail=detail,
        dispatcher_id=dispatcher_id,
        pid=pid,
        phase=phase,
        last_poll_at=last_poll_at_raw,
        jobs_processed_total=jobs_processed_total,
        current_poll_interval_seconds=poll_interval,
    )


def check_worker(db: Session, repo_root: Path) -> WorkerStatus:
    """Não existe um processo de worker persistente para "pingar" -- o worker é invocado sob
    demanda pelo dispatcher, por job. A verificação real possível aqui é dupla: (1) o binário
    compilado existe no disco (senão, TODO job vai falhar com WORKER_BINARY_NOT_BUILT); (2) não
    há nenhum job 'running' com heartbeat parado além do limite (sinal de um worker travado).
    As versões reportadas vêm do ÚLTIMO job que efetivamente rodou o worker (campo real
    persistido em GeometryJob, nunca inventado)."""
    dll_path = _find_worker_dll(repo_root)
    binary_found = dll_path is not None

    stale_running = (
        db.execute(
            select(func.count())
            .select_from(GeometryJob)
            .where(GeometryJob.status == JobStatus.RUNNING)
            .where(
                (GeometryJob.heartbeat_at.is_(None))
                | (GeometryJob.heartbeat_at < _utcnow() - timedelta(seconds=_HEARTBEAT_STALE_SECONDS))
            )
        ).scalar_one()
    )

    last_versions_row = db.execute(
        select(GeometryJob.worker_version, GeometryJob.dotnet_version, GeometryJob.picogk_version)
        .where(GeometryJob.worker_version.is_not(None))
        .order_by(GeometryJob.finished_at.desc())
        .limit(1)
    ).first()
    worker_version, dotnet_version, picogk_version = last_versions_row if last_versions_row else (None, None, None)

    if not binary_found:
        return WorkerStatus(
            state="unavailable",
            detail="Binário do worker (BioMatCadGeometryWorker.dll) não encontrado em apps/geometry-worker/bin -- compile antes de submeter jobs.",
            binary_found=False,
            worker_version=worker_version,
            dotnet_version=dotnet_version,
            picogk_version=picogk_version,
        )
    if stale_running > 0:
        return WorkerStatus(
            state="degraded",
            detail=f"{stale_running} job(s) em 'running' com heartbeat parado há mais de {_HEARTBEAT_STALE_SECONDS}s -- possível worker travado (serão recuperados pelo dispatcher).",
            binary_found=True,
            worker_version=worker_version,
            dotnet_version=dotnet_version,
            picogk_version=picogk_version,
        )
    return WorkerStatus(
        state="healthy",
        detail="Binário do worker presente; nenhum job em execução com heartbeat travado.",
        binary_found=True,
        worker_version=worker_version,
        dotnet_version=dotnet_version,
        picogk_version=picogk_version,
    )


def check_queue(db: Session) -> QueueStatus:
    queued_count = db.execute(
        select(func.count()).select_from(GeometryJob).where(GeometryJob.status == JobStatus.QUEUED)
    ).scalar_one()
    processing_count = db.execute(
        select(func.count()).select_from(GeometryJob).where(GeometryJob.status == JobStatus.RUNNING)
    ).scalar_one()
    return QueueStatus(
        state="healthy",
        detail=f"{queued_count} na fila, {processing_count} em execução.",
        queued_count=queued_count,
        processing_count=processing_count,
    )


def check_storage(settings: Settings) -> StorageStatus:
    path = Path(settings.artifact_storage_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_file = path / ".observability_write_probe"
        probe_file.write_text(str(os.getpid()), encoding="utf-8")
        probe_file.unlink()
        return StorageStatus(state="healthy", detail="Diretório existe e é gravável (probe real de escrita).", path=str(path), writable=True)
    except OSError as exc:
        return StorageStatus(state="unavailable", detail=f"Falha real ao gravar em {path}: {exc}", path=str(path), writable=False)


def _active_jobs(db: Session, organization_id: str) -> list[ActiveJobSummary]:
    rows = db.execute(
        select(GeometryJob)
        .join(GeometryJob.design_run)
        .where(GeometryJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
        .where(GeometryJob.design_run.has(organization_id=organization_id))
        .order_by(GeometryJob.created_at.asc())
    ).scalars().all()

    now = _utcnow()
    result = []
    for job in rows:
        heartbeat_stale = bool(
            job.status == JobStatus.RUNNING
            and (job.heartbeat_at is None or (now - job.heartbeat_at) > timedelta(seconds=_HEARTBEAT_STALE_SECONDS))
        )
        result.append(
            ActiveJobSummary(
                job_id=job.id,
                design_run_id=job.design_run_id,
                status=job.status.value,
                progress_pct=job.progress_pct,
                started_at=job.started_at.isoformat() if job.started_at else None,
                heartbeat_at=job.heartbeat_at.isoformat() if job.heartbeat_at else None,
                heartbeat_stale=heartbeat_stale,
            )
        )
    return result


def _failed_jobs(db: Session, organization_id: str) -> list[FailedJobSummary]:
    rows = db.execute(
        select(GeometryJob)
        .join(GeometryJob.design_run)
        .where(GeometryJob.status == JobStatus.FAILED)
        .where(GeometryJob.design_run.has(organization_id=organization_id))
        .order_by(GeometryJob.finished_at.desc())
        .limit(_MAX_FAILED_JOBS_SHOWN)
    ).scalars().all()
    return [
        FailedJobSummary(
            job_id=job.id,
            design_run_id=job.design_run_id,
            error_code=job.error_code,
            error_message=job.error_message,
            finished_at=job.finished_at.isoformat() if job.finished_at else None,
        )
        for job in rows
    ]


def build_observability_status(
    db: Session, settings: Settings, repo_root: Path, organization_id: str
) -> ObservabilityStatusResponse:
    database = check_database(db)
    dispatcher = check_dispatcher(settings)
    worker = check_worker(db, repo_root)
    queue = check_queue(db)
    storage = check_storage(settings)

    return ObservabilityStatusResponse(
        generated_at=_utcnow().isoformat(),
        api=ApiStatus(state="healthy", detail="Processo respondendo (esta própria requisição é a prova).", version=__version__, environment=settings.environment.value),
        database=database,
        dispatcher=dispatcher,
        worker=worker,
        queue=queue,
        storage=storage,
        versions=VersionsInfo(api=__version__, schema_geometry_recipe=schema_version()),
        jobs_active=_active_jobs(db, organization_id),
        jobs_failed_recent=_failed_jobs(db, organization_id),
    )
