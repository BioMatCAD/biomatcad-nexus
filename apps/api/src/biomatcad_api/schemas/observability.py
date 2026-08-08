"""Contratos de observabilidade real (Incremento 2.2, Seção 7: painel de observabilidade
local). Cada campo é resultado de uma verificação REAL feita no momento da requisição --
nunca um estado inventado ou otimista.

Estados possíveis (mínimo pedido): healthy, degraded, unavailable, stale, stopped, unknown.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ComponentState = Literal["healthy", "degraded", "unavailable", "stale", "stopped", "unknown"]


class ComponentStatus(BaseModel):
    """Bloco padrão de status de um subsistema -- todo componente do painel usa esta forma."""

    state: ComponentState
    detail: str


class ApiStatus(ComponentStatus):
    version: str
    environment: str


class DatabaseStatus(ComponentStatus):
    pass


class DispatcherStatus(ComponentStatus):
    dispatcher_id: str | None = None
    pid: int | None = None
    phase: str | None = None
    last_poll_at: str | None = None
    jobs_processed_total: int | None = None
    current_poll_interval_seconds: float | None = None


class WorkerStatus(ComponentStatus):
    binary_found: bool
    worker_version: str | None = None
    dotnet_version: str | None = None
    picogk_version: str | None = None


class QueueStatus(ComponentStatus):
    queued_count: int
    processing_count: int


class StorageStatus(ComponentStatus):
    path: str
    writable: bool


class ActiveJobSummary(BaseModel):
    job_id: str
    design_run_id: str
    status: str
    progress_pct: int
    started_at: str | None
    heartbeat_at: str | None
    heartbeat_stale: bool


class FailedJobSummary(BaseModel):
    job_id: str
    design_run_id: str
    error_code: str | None
    # Já sanitizado na origem (geometry_job_service._mark_failed nunca grava stdout/stderr
    # bruto do worker aqui) -- ver services/observability_service.py para a referência exata.
    error_message: str | None
    finished_at: str | None


class VersionsInfo(BaseModel):
    api: str
    schema_geometry_recipe: str


class ObservabilityStatusResponse(BaseModel):
    generated_at: str
    api: ApiStatus
    database: DatabaseStatus
    dispatcher: DispatcherStatus
    worker: WorkerStatus
    queue: QueueStatus
    storage: StorageStatus
    versions: VersionsInfo
    # Escopados pela organização do usuário autenticado (Incremento 2.1.1, Seção 5:
    # isolamento entre organizações) -- nunca vazam jobs de outra organização.
    jobs_active: list[ActiveJobSummary]
    jobs_failed_recent: list[FailedJobSummary]
