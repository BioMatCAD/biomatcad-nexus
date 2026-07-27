"""Evento de auditoria (Prompt Mestre §22 e §23.3 — trilha append-only)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from biomatcad_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    """Append-only por convenção da camada de aplicação: nenhum endpoint de UPDATE/DELETE é
    exposto para esta entidade. Isso não é imutabilidade garantida por infraestrutura — ver
    Prompt Mestre §23.3 (não alegar imutabilidade absoluta sem garantia de infraestrutura)."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
