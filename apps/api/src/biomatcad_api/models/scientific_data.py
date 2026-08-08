"""Fundação do banco de dados científico (Incremento 2.3, Rodada 1 -- Fase B).

Esta rodada NÃO faz coleta ampla na internet nem importa bases externas em massa (PubChem,
ChEBI, ChEMBL, Crossref, Europe PMC/PubMed, Crystallography Open Database, RCSB PDB,
fornecedores) -- ver docs/data/SOURCE_REGISTRY_POLICY.md para o registro dessas fontes como
candidatas futuras. O objetivo aqui é exclusivamente a fundação persistente: tornar o sistema
capaz de armazenar dado científico com proveniência completa, sem inventar nenhum valor.

Princípio central (repetido em cada tabela relevante): um valor científico nunca existe
desacompanhado de fonte, data de acesso, método/contexto, unidade, condições experimentais
relevantes, nível de evidência, estado de revisão e licença/termos de reutilização conhecidos.
Nenhuma tabela aqui sobrescreve silenciosamente um valor divergente -- observações de fontes
diferentes sempre coexistem como linhas separadas (ver PropertyObservation).

Compatibilidade: este módulo NÃO modifica `models/material.py` (MaterialRecord/MaterialProperty/
ScientificReference) -- esse modelo legado do Incremento 2.1 continua intocado, com a mesma
tabela `material_records` já referenciada por `GeometryJob.material_id` e por
`design_advisor_rule_based.py`. Este módulo estende por composição: `ScientificEntity` é o novo
registro canônico mais amplo (biomaterial, substância química, fármaco, formulação,
nanomaterial), e `MaterialRecord` ganha um vínculo OPCIONAL (`scientific_entity_id`, nullable,
sem backfill obrigatório) para permitir consolidação futura sem quebrar nenhum contrato
existente. Nenhum endpoint, teste ou comportamento do Incremento 2.1/2.2 é alterado por este
vínculo -- ele começa sempre NULL para os registros já existentes.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
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


# ---------------------------------------------------------------------------
# Enumerações do domínio científico
# ---------------------------------------------------------------------------


class ScientificEntityType(str, PyEnum):
    """Tipo da entidade científica canônica -- nunca confundir com produto de fornecedor
    (ver SupplierProduct) nem com a receita geométrica (GeometryRecipe, domínio distinto)."""

    BIOMATERIAL = "biomaterial"
    CHEMICAL_SUBSTANCE = "chemical_substance"
    DRUG = "drug"
    FORMULATION = "formulation"
    NANOMATERIAL = "nanomaterial"
    OTHER = "other"


class CurationState(str, PyEnum):
    """Estado de revisão/curadoria. Distinto do `ReviewStatus` legado de `models/material.py`
    (que não tem REJECTED) -- este é o vocabulário do domínio científico mais amplo desta
    rodada, deliberadamente separado para não alterar o comportamento/testes já aprovados do
    Incremento 2.1 sobre MaterialRecord/MaterialProperty."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class EvidenceType(str, PyEnum):
    """Distinção obrigatória (princípio 5 da rodada): nunca apresentar um destes tipos como
    outro. Nenhum é, por si só, validação clínica."""

    EXPERIMENTAL = "experimental"
    CALCULATED = "calculated"
    SUPPLIER_DECLARED = "supplier_declared"
    INFERRED = "inferred"
    SYNTHETIC_DEMO = "synthetic_demo"
    UNVERIFIED = "unverified"


class IdentifierVerificationStatus(str, PyEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"


class RedistributionStatus(str, PyEnum):
    """Permissão de redistribuição conhecida/desconhecida de uma fonte -- nunca assumir
    permissão por omissão; o padrão seguro é UNKNOWN, não ALLOWED."""

    ALLOWED = "allowed"
    PROHIBITED = "prohibited"
    UNKNOWN = "unknown"


class SourceType(str, PyEnum):
    DATABASE = "database"
    PUBLISHER = "publisher"
    SUPPLIER = "supplier"
    INSTITUTIONAL = "institutional"
    OTHER = "other"


class IngestionStatus(str, PyEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ReviewDecisionOutcome(str, PyEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


# ---------------------------------------------------------------------------
# Entidade canônica e identificadores
# ---------------------------------------------------------------------------


class ScientificEntity(Base):
    """Entidade científica canônica -- o registro central ao qual identificadores externos,
    observações de propriedades, evidências biológicas, produtos de fornecedor e referências
    cristalográficas se conectam. Nunca é, por si só, um produto comercial (ver SupplierProduct)
    nem uma receita geométrica (ver GeometryRecipe, domínio de fabricação/topologia distinto)."""

    __tablename__ = "scientific_entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    # Nullable: NULL = registro global/público (visível a qualquer usuário autenticado, somente
    # leitura fora do papel curador). Não-nulo = privado a essa organização. Ver
    # docs/data/PROVENANCE_AND_CURATION.md para a política completa de autorização.
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    entity_type: Mapped[ScientificEntityType] = mapped_column(
        Enum(ScientificEntityType, native_enum=False), nullable=False
    )
    preferred_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[CurationState] = mapped_column(
        Enum(CurationState, native_enum=False), nullable=False, default=CurationState.DRAFT
    )
    # Desativação/soft-delete: nunca apaga evidência histórica associada (observações,
    # identificadores, decisões de revisão permanecem intactos e consultáveis).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    identifiers: Mapped[list[ScientificIdentifier]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    property_observations: Mapped[list[PropertyObservation]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    biological_evidence: Mapped[list[BiologicalEvidence]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )
    supplier_products: Mapped[list[SupplierProduct]] = relationship(back_populates="entity")
    crystal_structure_references: Mapped[list[CrystalStructureReference]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )


class ScientificIdentifier(Base):
    """Identificador externo (CID, ChEBI, ChEMBL, CAS, DOI, PMID, COD, PDB, etc.) -- namespace e
    identificador normalizado formam uma restrição única para impedir duplicidade silenciosa."""

    __tablename__ = "scientific_identifiers"
    __table_args__ = (
        UniqueConstraint("namespace", "identifier_normalized", name="uq_identifier_namespace_normalized"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scientific_entities.id"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(50), nullable=False)
    identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    identifier_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    verification_status: Mapped[IdentifierVerificationStatus] = mapped_column(
        Enum(IdentifierVerificationStatus, native_enum=False),
        nullable=False,
        default=IdentifierVerificationStatus.UNVERIFIED,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped[ScientificEntity] = relationship(back_populates="identifiers")


# ---------------------------------------------------------------------------
# Fontes e referências
# ---------------------------------------------------------------------------


class ScientificSource(Base):
    """Registro de uma fonte de dados (banco, editora, fornecedor, institucional) -- nunca
    assume permissão de redistribuição por omissão (ver RedistributionStatus.UNKNOWN)."""

    __tablename__ = "scientific_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(200), nullable=True)
    license: Mapped[str | None] = mapped_column(String(200), nullable=True)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    terms_of_use: Mapped[str | None] = mapped_column(Text, nullable=True)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    redistribution_status: Mapped[RedistributionStatus] = mapped_column(
        Enum(RedistributionStatus, native_enum=False), nullable=False, default=RedistributionStatus.UNKNOWN
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class BibliographicReference(Base):
    """Referência bibliográfica -- nunca inventar uma referência ausente; se a fonte não
    fornecer DOI/PMID, os campos ficam nulos, não fabricados."""

    __tablename__ = "bibliographic_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    pmid: Mapped[str | None] = mapped_column(String(50), nullable=True)
    other_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scientific_sources.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Propriedades: definição canônica + observações com proveniência completa
# ---------------------------------------------------------------------------


class PropertyDefinition(Base):
    """Vocabulário canônico de propriedades (ex.: `young_modulus`, `melting_point`) -- unidade
    canônica declarada aqui uma única vez; cada observação registra sua unidade original e,
    quando a conversão for comprovada, o valor normalizado (ver PropertyObservation)."""

    __tablename__ = "property_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    canonical_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_unit: Mapped[str] = mapped_column(String(50), nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, default="numeric")
    applicable_domain: Mapped[str] = mapped_column(String(50), nullable=False, default="generic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


def compute_observation_fingerprint(
    *,
    entity_id: str,
    property_definition_id: str,
    source_id: str | None,
    value_numeric: float | None,
    value_min: float | None,
    value_max: float | None,
    value_text: str | None,
    unit_original: str,
    method: str | None,
    conditions_key: str | None,
) -> str:
    """Fingerprint determinístico de deduplicação (SHA-256).

    Duas observações são consideradas a MESMA observação (deduplicáveis) apenas se
    entidade+propriedade+fonte+valor+unidade+método+condições forem idênticos. Qualquer
    diferença em qualquer um desses campos produz um fingerprint diferente -- ou seja,
    observações genuinamente divergentes de fontes diferentes (ou da mesma fonte em condições
    diferentes) NUNCA colidem e sempre coexistem como linhas separadas. Isto implementa
    diretamente o princípio 4 da rodada ("não sobrescrever silenciosamente valores
    divergentes").
    """
    raw = "|".join(
        [
            entity_id,
            property_definition_id,
            source_id or "",
            f"{value_numeric:.10g}" if value_numeric is not None else "",
            f"{value_min:.10g}" if value_min is not None else "",
            f"{value_max:.10g}" if value_max is not None else "",
            value_text or "",
            unit_original,
            method or "",
            conditions_key or "",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class PropertyObservation(Base):
    """Um único valor científico observado, sempre com proveniência completa. NUNCA é
    atualizado em memória por cima de um valor divergente anterior -- uma nova observação de
    fonte diferente (ou condições diferentes) é sempre uma NOVA linha (ver
    compute_observation_fingerprint). O único mecanismo de "correção" é uma nova ReviewDecision
    que muda o `review_status`, nunca a reescrita do valor em si."""

    __tablename__ = "property_observations"
    __table_args__ = (
        UniqueConstraint("dedup_fingerprint", name="uq_property_observation_fingerprint"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_entities.id"), nullable=False)
    property_definition_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("property_definitions.id"), nullable=False
    )

    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    unit_original: Mapped[str] = mapped_column(String(50), nullable=False)
    # Só preenchido quando a conversão para a unidade canônica de PropertyDefinition for
    # comprovada (ex.: fator de conversão determinístico) -- nunca uma estimativa silenciosa.
    value_normalized: Mapped[float | None] = mapped_column(Float, nullable=True)

    method: Mapped[str | None] = mapped_column(String(300), nullable=True)

    # Condições experimentais explícitas mais comuns, mais um JSON aberto para qualquer outra
    # condição relevante não coberta pelos campos fixos (ex.: umidade relativa, atmosfera).
    condition_temperature_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_pressure_kpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_ph: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_medium: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conditions_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    uncertainty_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType, native_enum=False), nullable=False)

    reference_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bibliographic_references.id"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scientific_sources.id"), nullable=True)
    source_location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Rastreia uma observação declarada por fornecedor até o produto exato, sem jamais tratar o
    # produto como se fosse a entidade canônica (ver SupplierProduct e o teste dedicado).
    related_supplier_product_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("supplier_products.id"), nullable=True
    )
    # Incremento 2.3, Rodada 2 (Fase C): rastreia uma observação criada por um conector de
    # ingestão até o snapshot EXATO e imutável do payload de onde ela veio (ver
    # models/scientific_ingestion.py::RawSourceRecord). Sempre NULL para observações
    # criadas manualmente/via seed -- coluna aditiva, sem impacto em nenhum comportamento
    # já testado da Rodada 1.
    raw_source_record_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("raw_source_records.id"), nullable=True
    )

    review_status: Mapped[CurationState] = mapped_column(
        Enum(CurationState, native_enum=False), nullable=False, default=CurationState.DRAFT
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dedup_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped[ScientificEntity] = relationship(back_populates="property_observations")


# ---------------------------------------------------------------------------
# Evidência biológica (classificação apenas de pesquisa)
# ---------------------------------------------------------------------------


class BiologicalEvidence(Base):
    """Evidência biológica associada a uma entidade -- classificação SEMPRE apenas de
    pesquisa (`research_classification_only=True`, não configurável para False por nenhum
    caminho de API desta rodada). Nunca é apresentada como validação clínica."""

    __tablename__ = "biological_evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_entities.id"), nullable=False)

    assay_type: Mapped[str] = mapped_column(String(200), nullable=False)
    biological_model: Mapped[str] = mapped_column(String(100), nullable=False)
    species: Mapped[str | None] = mapped_column(String(150), nullable=True)
    cell_line: Mapped[str | None] = mapped_column(String(150), nullable=True)
    organism: Mapped[str | None] = mapped_column(String(150), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    result_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dose_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    duration_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    reference_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bibliographic_references.id"), nullable=True
    )
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("scientific_sources.id"), nullable=True)

    research_classification_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped[ScientificEntity] = relationship(back_populates="biological_evidence")


# ---------------------------------------------------------------------------
# Fornecedor e produto comercial -- NUNCA sinônimo da entidade canônica
# ---------------------------------------------------------------------------


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    products: Mapped[list[SupplierProduct]] = relationship(
        back_populates="supplier", cascade="all, delete-orphan"
    )


class SupplierProduct(Base):
    """Produto comercial de um fornecedor. `entity_id` é opcional e deliberadamente nullable:
    um produto pode existir sem ainda estar vinculado a uma entidade científica canônica
    (pendente de curadoria) -- e mesmo quando vinculado, o produto NUNCA substitui ou é tratado
    como a entidade em si (ver teste dedicado de não-confusão produto/entidade)."""

    __tablename__ = "supplier_products"
    __table_args__ = (
        UniqueConstraint("supplier_id", "catalog_sku", name="uq_supplier_product_sku"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    supplier_id: Mapped[str] = mapped_column(String(36), ForeignKey("suppliers.id"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scientific_entities.id"), nullable=True
    )
    catalog_sku: Mapped[str] = mapped_column(String(100), nullable=False)
    commercial_name: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registry_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registry_valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Propriedades declaradas pelo fornecedor, em bruto -- SEMPRE rotuladas como tal; nunca
    # promovidas a PropertyObservation sem evidence_type=SUPPLIER_DECLARED explícito.
    declared_properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    supplier: Mapped[Supplier] = relationship(back_populates="products")
    entity: Mapped[ScientificEntity | None] = relationship(back_populates="supplier_products")


# ---------------------------------------------------------------------------
# Estrutura cristalográfica (referência apenas -- sem incorporar arquivos nesta rodada)
# ---------------------------------------------------------------------------


class CrystalStructureReference(Base):
    """Referência a uma estrutura cristalográfica externa (ex.: COD, RCSB PDB). Esta rodada
    armazena apenas metadados de referência -- nenhum arquivo cristalográfico (CIF/PDB) é
    baixado, incorporado ou redistribuído."""

    __tablename__ = "crystal_structure_references"
    __table_args__ = (
        UniqueConstraint("database_name", "accession_id", name="uq_crystal_structure_accession"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_entities.id"), nullable=False)
    database_name: Mapped[str] = mapped_column(String(50), nullable=False)
    accession_id: Mapped[str] = mapped_column(String(100), nullable=False)
    formula: Mapped[str | None] = mapped_column(String(200), nullable=True)
    crystal_system: Mapped[str | None] = mapped_column(String(50), nullable=True)
    space_group: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cell_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    entity: Mapped[ScientificEntity] = relationship(back_populates="crystal_structure_references")


# ---------------------------------------------------------------------------
# Ingestão e trilha de revisão
# ---------------------------------------------------------------------------


class IngestionRun(Base):
    """Execução de um conector de ingestão. Nesta rodada nenhum conector real existe -- esta
    tabela documenta o contrato para quando um conector (PubChem, ChEBI etc.) for implementado
    em rodada futura, e é exercitada nos testes via conectores sintéticos de teste."""

    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("scientific_sources.id"), nullable=False)
    connector_name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_version: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, native_enum=False), nullable=False, default=IngestionStatus.RUNNING
    )
    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    raw_payload_checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_event_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("audit_events.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ReviewDecision(Base):
    """Trilha de decisão de revisão -- append-only por convenção da camada de aplicação (nenhum
    endpoint de UPDATE/DELETE é exposto), mesmo padrão já usado por `AuditEvent`. `subject_type`
    + `subject_id` referenciam polimorficamente o objeto revisado (ex.: "ScientificEntity",
    "PropertyObservation") sem exigir uma FK física por tipo, para não acoplar esta tabela a
    todas as tabelas revisáveis."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[ReviewDecisionOutcome] = mapped_column(
        Enum(ReviewDecisionOutcome, native_enum=False), nullable=False
    )
    reviewer_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
