"""Schemas Pydantic da API administrativa de ingestão científica (Incremento 2.3, Rodada 2,
Fase H). Deliberadamente pequena: submissão exige uma lista EXPLÍCITA de identificadores
externos (nunca uma consulta livre/fuzzy) e um `source_id`/`connector_id` já existentes -- ver
docs/data/connectors/CONNECTOR_CONTRACT.md."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from biomatcad_api.models.scientific_ingestion import IngestionConflictType, IngestionRequestStatus

# Mesmo limite de config.py::pubchem_max_cids_per_request -- repetido aqui apenas como default
# de schema (documentação de API), a validação de fato acontece em
# ScientificDataConnector.validate_request, nunca confiando só no default do schema.
DEFAULT_MAX_CIDS_PER_REQUEST = 10


class IngestionRequestCreate(BaseModel):
    """Lista explícita de identificadores externos -- nunca uma busca por nome/fuzzy. O
    `connector_id` deve ser um conector implementado (ver registry.py); `source_id` deve
    referenciar um `ScientificSource` já existente (ex.: o registro PubChem do seed sintético)."""

    connector_id: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=36)
    external_ids: list[str] = Field(min_length=1, max_length=DEFAULT_MAX_CIDS_PER_REQUEST)
    dry_run: bool = False


class IngestionRequestResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    organization_id: str | None
    requested_by_user_id: str
    connector_id: str
    source_id: str
    external_ids: list[str]
    dry_run: bool
    status: IngestionRequestStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    claimed_by_dispatcher_id: str | None
    heartbeat_at: datetime | None
    attempt_number: int
    cancel_requested_at: datetime | None
    summary: dict | None
    error: dict | None
    ingestion_run_id: str | None


class IngestionConflictResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    ingestion_request_id: str
    external_record_id: str
    conflict_type: IngestionConflictType
    entity_id: str | None
    other_entity_id: str | None
    details: dict | None
    resolved: bool
    created_at: datetime


class ConnectorInfoResponse(BaseModel):
    connector_id: str
    version: str
    status: str
    description: str


class RawSourceRecordResponse(BaseModel):
    """Snapshot bruto versionado de uma fonte externa (Adendo de Interface Científica Mínima,
    Fase L) -- exposto em modo leitura para a aba "Snapshots" do detalhe de entidade científica.
    Nunca editável via API; apenas leitura de um registro já persistido por
    `services/scientific_ingestion_service.py::_persist_raw_source_record`."""

    model_config = {"from_attributes": True}
    id: str
    source_id: str
    connector_id: str
    connector_version: str
    external_record_id: str
    requested_endpoint: str
    http_status: int
    content_type: str | None
    fetched_at: datetime
    payload_sha256: str
    payload_size_bytes: int
    schema_mapping_version: str
    predecessor_record_id: str | None
    parsing_status: str
    retention_policy: str
    created_at: datetime
