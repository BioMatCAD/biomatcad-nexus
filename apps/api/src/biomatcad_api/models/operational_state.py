"""Estado operacional (Prompt Mestre §3.2 e Incremento 1: contrato de chave mestra).

Os quatro estados — pesquisa, laboratório, piloto clínico, produção clínica — são registrados
no backend, nunca apenas no frontend. Teste/Piloto/Produção começam desabilitados por padrão e
só podem ser ativados via endpoint autenticado que exige a chave mestra configurada no ambiente
(nunca embutida no cliente, nunca localStorage).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from biomatcad_api.db import Base


class OperationalStateKind(str, enum.Enum):
    RESEARCH = "research"
    LABORATORY = "laboratory"
    CLINICAL_PILOT = "clinical_pilot"
    CLINICAL_PRODUCTION = "clinical_production"


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperationalState(Base):
    __tablename__ = "operational_states"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    justification: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    @staticmethod
    def default_enabled(kind: OperationalStateKind) -> bool:
        """Somente Pesquisa é habilitada por padrão (Prompt Mestre §3.2)."""
        return kind == OperationalStateKind.RESEARCH
