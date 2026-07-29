"""DesignRun/GeometryJob — orquestração de execução geométrica (Incremento 2.1, item 4).

DesignRun é a unidade de idempotência (organization_id + idempotency_key únicos):
reenviar a mesma chave para a mesma organização nunca cria um segundo job. GeometryJob é a
unidade de execução/estado (queued/running/succeeded/failed/cancelled) com progresso,
tentativa, timestamps, versões do worker/.NET/PicoGK e métricas — a fila é a própria coluna
`status`, consumida por um processo separado (`scripts/geometry_dispatcher.py`), nunca pela
API.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biomatcad_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, PyEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DesignRun(Base):
    __tablename__ = "design_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_design_run_org_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("biomat_projects.id"), nullable=False)
    recipe_id: Mapped[str] = mapped_column(String(36), ForeignKey("geometry_recipes.id"), nullable=False)
    material_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("material_records.id"), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    jobs: Mapped[list[GeometryJob]] = relationship(back_populates="design_run", cascade="all, delete-orphan")


class GeometryJob(Base):
    __tablename__ = "geometry_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    design_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("design_runs.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False), nullable=False, default=JobStatus.QUEUED
    )
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dotnet_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    picogk_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hardware_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cancelled_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)

    design_run: Mapped[DesignRun] = relationship(back_populates="jobs")
