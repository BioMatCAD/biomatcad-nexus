"""Estado operacional (Prompt Mestre §3.2, corrigido no Incremento 1.1).

Dois grupos distintos, que NÃO podem ser confundidos entre si:

1. Contextos independentes — Pesquisa e Laboratório. Cada um é ativado/desativado
   individualmente (`OperationalStateKind.RESEARCH`, `OperationalStateKind.LABORATORY`).
   Pesquisa vem habilitada por padrão; Laboratório não.
2. Suíte clínica — Teste clínico, Piloto clínico e Produção clínica
   (`CLINICAL_TEST`, `CLINICAL_PILOT`, `CLINICAL_PRODUCTION`). Esses três flags são controlados
   SEMPRE em conjunto, na mesma transação, por uma única chave mestra — nunca individualmente e
   nunca com chaves diferentes por flag. Ver `services/operational_state_service.py` e
   `routers/operational_state.py`.

Nenhum destes estados é alterável apenas pelo frontend: toda ativação passa por endpoint
autenticado, restrito a administrador, e é auditada com estado anterior, estado posterior,
justificativa e identidade de quem ativou (Prompt Mestre §3.2, Incremento 1.1).
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
    CLINICAL_TEST = "clinical_test"
    CLINICAL_PILOT = "clinical_pilot"
    CLINICAL_PRODUCTION = "clinical_production"


# Suíte clínica: os três flags controlados atomicamente pela chave mestra (Incremento 1.1).
# Pesquisa e Laboratório ficam DE FORA deste grupo por serem contextos independentes.
CLINICAL_SUITE_KINDS: tuple[OperationalStateKind, ...] = (
    OperationalStateKind.CLINICAL_TEST,
    OperationalStateKind.CLINICAL_PILOT,
    OperationalStateKind.CLINICAL_PRODUCTION,
)


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
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    @staticmethod
    def default_enabled(kind: OperationalStateKind) -> bool:
        """Somente Pesquisa é habilitada por padrão (Prompt Mestre §3.2)."""
        return kind == OperationalStateKind.RESEARCH

    def is_effectively_enabled(self, *, now: datetime | None = None) -> bool:
        """`enabled` sozinho não basta: um estado expirado deve ser tratado como desabilitado,
        mesmo que a linha no banco ainda diga `enabled=True` (não há job de expiração em
        background nesta fase — a expiração é avaliada em tempo de leitura)."""
        if not self.enabled:
            return False
        if self.expires_at is None:
            return True
        reference = now or _utcnow()
        return self.expires_at > reference
