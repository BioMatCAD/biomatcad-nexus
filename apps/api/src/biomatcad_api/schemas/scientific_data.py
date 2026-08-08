"""Schemas Pydantic da API mínima de pesquisa do banco de dados científico (Incremento 2.3,
Rodada 1, Fase D). Intencionalmente minimal -- ver models/scientific_data.py para o contrato
completo de domínio e docs/data/SCIENTIFIC_DATA_MODEL.md para a documentação de referência."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from biomatcad_api.models.scientific_data import (
    CurationState,
    EvidenceType,
    IdentifierVerificationStatus,
    ReviewDecisionOutcome,
    ScientificEntityType,
)


class ScientificEntityCreateRequest(BaseModel):
    entity_type: ScientificEntityType
    preferred_name: str = Field(min_length=1, max_length=300)
    description: str | None = None


class ScientificEntitySummary(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    organization_id: str | None
    entity_type: ScientificEntityType
    preferred_name: str
    review_status: CurationState
    is_active: bool
    created_at: datetime


class ScientificIdentifierResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    namespace: str
    identifier: str
    identifier_normalized: str
    verification_status: IdentifierVerificationStatus
    created_at: datetime


class ScientificEntityDetail(ScientificEntitySummary):
    description: str | None
    updated_at: datetime
    identifiers: list[ScientificIdentifierResponse]


class PropertyObservationResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    property_definition_id: str
    value_numeric: float | None
    value_min: float | None
    value_max: float | None
    value_text: str | None
    unit_original: str
    value_normalized: float | None
    method: str | None
    condition_temperature_k: float | None
    condition_pressure_kpa: float | None
    condition_ph: float | None
    condition_medium: str | None
    conditions_extra: dict | None
    uncertainty_low: float | None
    uncertainty_high: float | None
    evidence_type: EvidenceType
    reference_id: str | None
    source_id: str | None
    source_location: str | None
    related_supplier_product_id: str | None
    review_status: CurationState
    notes: str | None
    created_at: datetime


class BibliographicReferenceResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    doi: str | None
    pmid: str | None
    other_identifier: str | None
    title: str
    authors: str | None
    venue: str | None
    year: int | None
    url: str | None


class ScientificSourceResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    name: str
    source_type: str
    base_url: str | None
    publisher: str | None
    license: str | None
    version: str | None
    accessed_at: datetime | None
    redistribution_status: str


class ProvenanceEntry(BaseModel):
    """Um par (referência bibliográfica, fonte) associado a uma observação da entidade --
    combinação usada para responder 'de onde veio este dado' de forma consolidada."""

    observation_id: str
    reference: BibliographicReferenceResponse | None
    source: ScientificSourceResponse | None


class SupplierProductResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    supplier_id: str
    entity_id: str | None
    catalog_sku: str
    commercial_name: str
    url: str | None
    region: str | None
    lot_number: str | None
    registry_valid_from: datetime | None
    registry_valid_to: datetime | None
    declared_properties: dict | None


class CrystalStructureReferenceResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    entity_id: str
    database_name: str
    accession_id: str
    formula: str | None
    crystal_system: str | None
    space_group: str | None
    cell_params: dict | None
    url: str | None
    license: str | None
    file_checksum_sha256: str | None


class ReviewDecisionCreateRequest(BaseModel):
    decision: ReviewDecisionOutcome
    justification: str = Field(min_length=1)


class ReviewDecisionResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    subject_type: str
    subject_id: str
    decision: ReviewDecisionOutcome
    reviewer_user_id: str
    justification: str
    previous_state: str | None
    new_state: str | None
    created_at: datetime


class PropertyDefinitionResponse(BaseModel):
    """Vocabulário canônico de propriedades (Adendo de Interface Científica Mínima, Incremento
    2.3, Rodada 2, Fase L) -- permite ao frontend traduzir `property_definition_id` (um UUID
    opaco em PropertyObservationResponse) em nome legível/unidade canônica, sem duplicar essa
    informação em cada observação."""

    model_config = {"from_attributes": True}
    id: str
    canonical_key: str
    name: str
    dimension: str
    canonical_unit: str
    value_type: str
    applicable_domain: str


class BiologicalEvidenceResponse(BaseModel):
    """Evidência biológica (Adendo de Interface Científica Mínima) -- `research_classification_only`
    é sempre True nesta rodada (ver models/scientific_data.py::BiologicalEvidence); nunca
    representa validação clínica."""

    model_config = {"from_attributes": True}
    id: str
    entity_id: str
    assay_type: str
    biological_model: str
    species: str | None
    cell_line: str | None
    organism: str | None
    endpoint: str
    result_value: float | None
    result_text: str | None
    dose_value: float | None
    dose_unit: str | None
    duration_value: float | None
    duration_unit: str | None
    conditions: dict | None
    reference_id: str | None
    source_id: str | None
    research_classification_only: bool
    created_at: datetime
