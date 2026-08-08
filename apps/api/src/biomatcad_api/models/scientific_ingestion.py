"""Infraestrutura de ingestão científica (Incremento 2.3, Rodada 2 -- Fase C).

Esta rodada implementa o primeiro conector real (PubChem PUG REST, ver
services/connectors/pubchem.py) e a infraestrutura comum necessária para qualquer conector
futuro. Três entidades novas, todas aditivas (nenhuma tabela da Rodada 1 é modificada, exceto
uma única coluna nova e nullable em PropertyObservation -- ver comentário no models/__init__.py
e na migração desta rodada).

Princípio central (reforçado aqui): todo dado externo entra sempre como IMPORTADO e NÃO
REVISADO. Nenhuma linha aqui jamais promove uma ScientificEntity/PropertyObservation para
`reviewed` automaticamente -- isso continua exigindo uma ReviewDecision humana explícita (ver
models/scientific_data.py). A ingestão nunca funde entidades por nome livre, nunca sobrescreve
uma observação já revisada, e nunca apaga evidência anterior -- ver
services/connectors/base.py::ScientificDataConnector.reconcile/persist para onde essas regras
são aplicadas em código.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from biomatcad_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ParsingStatus(str, PyEnum):
    PARSED = "parsed"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestionRequestStatus(str, PyEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionConflictType(str, PyEnum):
    """Tipos de conflito estruturado detectados durante a reconciliação (Fase G). Nunca
    resolvidos automaticamente -- apenas registrados para decisão humana futura (ReviewDecision
    continua sendo o único mecanismo de mudança de estado de curadoria)."""

    INCHIKEY_SHARED_WITH_OTHER_ENTITY = "inchikey_shared_with_other_entity"
    IDENTIFIER_VERIFICATION_DISPUTED = "identifier_verification_disputed"
    OTHER = "other"


class RawSourceRecord(Base):
    """Snapshot imutável de um único registro bruto obtido de uma fonte externa (um CID do
    PubChem, por exemplo). Nunca editado após criado -- uma nova versão (payload alterado) é
    sempre uma NOVA linha, com `predecessor_record_id` apontando para a versão anterior da MESMA
    (source_id, external_record_id). "Supersedes" é a relação inversa (consultável via
    `predecessor_record_id` a partir da versão mais nova), não uma coluna própria.

    O payload é armazenado como JSON canônico (chaves ordenadas, separadores compactos -- mesma
    convenção de `recipe_service.canonicalize_recipe`) diretamente nesta tabela para o piloto
    pequeno desta rodada (limite rígido de tamanho aplicado na camada de aplicação, ver
    services/connectors/base.py::MAX_PAYLOAD_BYTES). Uma abstração de object storage (para
    payloads maiores, em rodada futura) NÃO é implementada agora -- ver
    docs/data/connectors/CONNECTOR_CONTRACT.md."""

    __tablename__ = "raw_source_records"
    __table_args__ = (
        Index("ix_raw_source_records_source_external_id", "source_id", "external_record_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_sources.id"), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    external_record_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # Endpoint normalizado (path + query pública, NUNCA credenciais/cabeçalhos/cookies).
    requested_endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_mapping_version: Mapped[str] = mapped_column(String(50), nullable=False)
    predecessor_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("raw_source_records.id"), nullable=True
    )
    parsing_status: Mapped[ParsingStatus] = mapped_column(Enum(ParsingStatus, native_enum=False), nullable=False)
    parsing_error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Política de retenção declarada explicitamente (nunca implícita) -- ver
    # docs/data/connectors/PUBCHEM_CONNECTOR.md para o valor usado nesta rodada.
    retention_policy: Mapped[str] = mapped_column(String(100), nullable=False, default="pilot_indefinite")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ScientificIngestionRequest(Base):
    """Fila persistente de solicitações de ingestão -- mesmo padrão de claim atômico
    (`SELECT ... FOR UPDATE SKIP LOCKED`) já usado por `GeometryJob`
    (services/geometry_job_service.py::claim_next_queued_job), implementado de forma
    independente aqui (ver services/scientific_ingestion_service.py) porque os dois domínios
    têm estados/transições diferentes o suficiente para não valer a pena uma abstração
    genérica prematura -- mas o PADRÃO de concorrência é deliberadamente idêntico."""

    __tablename__ = "scientific_ingestion_requests"
    __table_args__ = (
        Index("ix_scientific_ingestion_requests_status_created_at", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    requested_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_sources.id"), nullable=False)
    # Lista explícita de identificadores externos (CIDs) -- nunca uma varredura/consulta aberta.
    external_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[IngestionRequestStatus] = mapped_column(
        Enum(IngestionRequestStatus, native_enum=False), nullable=False, default=IngestionRequestStatus.QUEUED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_dispatcher_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False, default=_uuid)
    ingestion_run_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ingestion_runs.id"), nullable=True)


class IngestionConflict(Base):
    """Conflito estruturado detectado durante a reconciliação -- nunca resolvido
    automaticamente. Ver `IngestionConflictType` para os tipos e
    `ScientificDataConnector.reconcile` para onde é gerado."""

    __tablename__ = "ingestion_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ingestion_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scientific_ingestion_requests.id"), nullable=False
    )
    external_record_id: Mapped[str] = mapped_column(String(200), nullable=False)
    conflict_type: Mapped[IngestionConflictType] = mapped_column(
        Enum(IngestionConflictType, native_enum=False), nullable=False
    )
    entity_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scientific_entities.id"), nullable=True)
    other_entity_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scientific_entities.id"), nullable=True
    )
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
