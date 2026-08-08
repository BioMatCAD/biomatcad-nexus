"""Contrato comum de conectores de ingestão científica (Incremento 2.3, Rodada 2 -- Fase B).

`ScientificDataConnector` é a base abstrata que qualquer conector real (PubChem nesta rodada;
ChEBI, ChEMBL, Crystallography Open Database, Crossref, RCSB PDB em rodadas futuras -- ver
docs/data/SOURCE_REGISTRY_POLICY.md) deve estender. Apenas `validate_request`/`fetch`/
`normalize` são abstratos (específicos de cada fonte -- como buscar e como interpretar o
formato de resposta daquela fonte). `reconcile`/`persist`/`summarize` têm uma implementação
CONCRETA e COMPARTILHADA aqui, porque a lógica de "como um registro normalizado vira uma
ScientificEntity/observações/identificadores" não depende da fonte -- é a mesma regra de
domínio (nunca fundir por nome, nunca sobrescrever revisado, sempre marcar conflito) qualquer
que seja o conector. Isso evita que um futuro conector ChEBI precise reimplementar essa lógica.

Princípios obrigatórios desta rodada (repetidos aqui porque `reconcile`/`persist` são onde eles
são de fato aplicados em código):

1. Todo dado externo entra como IMPORTADO e NÃO REVISADO (`CurationState.DRAFT`, nunca
   `REVIEWED`) -- promover para revisado continua exigindo uma `ReviewDecision` humana.
2. A identidade primária de qualquer conector é o par (namespace do identificador externo,
   valor) -- ex.: `("pubchem_cid", "2244")`. Nunca se funde duas entidades por nome livre.
3. Uma observação já com `review_status == REVIEWED` nunca é sobrescrita -- uma nova
   observação (mesmo que divergente) é sempre uma NOVA linha (mesmo princípio de
   `models/scientific_data.py::compute_observation_fingerprint`, reaproveitado sem alteração).
4. Colisão (ex.: o InChIKey do registro que está chegando já pertence a OUTRA entidade que não
   a que o CID/identificador primário resolveu) nunca é resolvida automaticamente -- é sempre
   registrada como `IngestionConflict` estruturado, para decisão humana futura.
5. Nenhuma evidência anterior é apagada -- `persist` só adiciona linhas novas.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.scientific_data import (
    CurationState,
    EvidenceType,
    IdentifierVerificationStatus,
    PropertyDefinition,
    PropertyObservation,
    ScientificEntity,
    ScientificEntityType,
    ScientificIdentifier,
    compute_observation_fingerprint,
)
from biomatcad_api.models.scientific_ingestion import (
    IngestionConflictType,
    ParsingStatus,
    RawSourceRecord,
)

# Limite rígido de tamanho de payload aceito nesta rodada (piloto pequeno, nunca importação em
# massa) -- um payload maior que isto é rejeitado antes de ser persistido, nunca truncado
# silenciosamente (truncar mudaria o conteúdo sem que o checksum refletisse isso claramente).
MAX_PAYLOAD_BYTES = 200_000


def canonical_json_bytes(payload: dict) -> bytes:
    """Mesma convenção de `recipe_service.canonicalize_recipe`: chaves ordenadas, separadores
    compactos -- determinístico para o mesmo conteúdo lógico, base do checksum SHA-256."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_of_payload(payload: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NormalizedProperty:
    """Uma propriedade calculada/declarada extraída do registro normalizado -- sempre rotulada
    com `evidence_type` explícito (nunca apresentada como `experimental` sem evidência)."""

    property_key: str
    value_numeric: float | None
    value_text: str | None
    unit: str
    evidence_type: EvidenceType


@dataclass(frozen=True)
class NormalizedExternalRecord:
    """Resultado de `normalize()` -- nunca inventa um valor ausente; campos não presentes na
    fonte ficam `None` e são listados em `missing_fields`, nunca silenciosamente omitidos."""

    external_identifier: str
    source_name: str
    retrieved_at: datetime
    preferred_name: str | None = None
    iupac_name: str | None = None
    # Sinônimos são preservados para referência, mas NUNCA usados como identidade (princípio 3
    # da Rodada 2: "nenhuma reconciliação automática exclusivamente por nome").
    synonyms: list[str] = field(default_factory=list)
    formula: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    canonical_smiles: str | None = None
    isomeric_smiles: str | None = None
    calculated_properties: list[NormalizedProperty] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    mapping_warnings: list[str] = field(default_factory=list)
    raw_payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    """Resultado de `fetch()` -- sempre inclui o payload bruto, mesmo em caso de erro (quando
    disponível), para que `parsing_error` estruturado possa referenciar o que foi recebido."""

    external_id: str
    requested_endpoint: str
    http_status: int
    content_type: str | None
    fetched_at: datetime
    payload_json: dict | None
    parsing_status: ParsingStatus
    parsing_error: dict | None = None


@dataclass
class ConflictReport:
    conflict_type: IngestionConflictType
    entity_id: str | None
    other_entity_id: str | None
    details: dict


@dataclass
class ReconcileOutcome:
    """Resultado de `reconcile()` -- nunca decide sozinho fundir entidades; apenas indica qual
    entidade usar (existente ou a ser criada) e quais conflitos foram detectados."""

    entity: ScientificEntity
    entity_is_new: bool
    conflicts: list[ConflictReport]


@dataclass
class PersistOutcome:
    """Resultado de `persist()` para UM identificador externo -- usado por `summarize()` para
    montar os contadores do IngestionRun (received/created/updated/skipped/rejected)."""

    external_id: str
    entity_id: str | None
    raw_source_record_id: str | None
    created_entity: bool
    created_observations: int
    unchanged: bool
    conflicts: list[ConflictReport]
    rejected: bool
    rejection_reason: str | None = None


class ScientificDataConnector(ABC):
    """Base abstrata para conectores de ingestão científica. Ver docstring do módulo para os
    princípios obrigatórios aplicados em `reconcile`/`persist`."""

    connector_id: str
    connector_version: str
    # Namespace usado em ScientificIdentifier para o identificador primário deste conector
    # (ex.: "pubchem_cid"). Cada conector declara o seu -- nunca reconciliado por nome.
    primary_identifier_namespace: str
    schema_mapping_version: str

    @abstractmethod
    def validate_request(self, external_ids: list[str]) -> list[str]:
        """Retorna uma lista de erros de validação (vazia = requisição válida). Nunca lança
        exceção para entrada inválida do usuário -- erros estruturados sempre."""

    @abstractmethod
    def fetch(self, external_id: str) -> FetchResult:
        """Busca o registro bruto de UM identificador externo. Implementação específica de
        cada fonte -- ver services/connectors/pubchem.py para a política de rede."""

    @abstractmethod
    def normalize(self, fetch_result: FetchResult) -> NormalizedExternalRecord:
        """Converte o payload bruto em `NormalizedExternalRecord`. Nunca inventa um campo
        ausente -- registra em `missing_fields`."""

    # ------------------------------------------------------------------------------------
    # Reconciliação e persistência -- compartilhadas por todos os conectores (ver docstring
    # do módulo). Não sobrescrever em subclasses a menos que uma fonte futura precise de uma
    # regra de identidade genuinamente diferente (o que deveria ser raro).
    # ------------------------------------------------------------------------------------

    def reconcile(self, db: Session, normalized: NormalizedExternalRecord) -> ReconcileOutcome:
        conflicts: list[ConflictReport] = []

        existing_identifier = (
            db.query(ScientificIdentifier)
            .filter(
                ScientificIdentifier.namespace == self.primary_identifier_namespace,
                ScientificIdentifier.identifier_normalized == normalized.external_identifier.strip().upper(),
            )
            .first()
        )

        entity_is_new = existing_identifier is None
        if existing_identifier is not None:
            entity = db.get(ScientificEntity, existing_identifier.entity_id)
            assert entity is not None
        else:
            # Categorização SEMPRE conservadora -- nunca inferir "fármaco" só por existir na
            # fonte (Fase G, regra explícita). Uma classificação mais específica depende de
            # curadoria humana ou de outra fonte apropriada, em rodada futura.
            entity = ScientificEntity(
                organization_id=None,
                entity_type=ScientificEntityType.CHEMICAL_SUBSTANCE,
                preferred_name=normalized.preferred_name or normalized.external_identifier,
                description=(
                    f"Importado automaticamente de {normalized.source_name} "
                    f"(identificador {self.primary_identifier_namespace}={normalized.external_identifier}). "
                    "Não revisado -- classificação inicial conservadora (chemical_substance)."
                ),
                review_status=CurationState.DRAFT,
            )
            db.add(entity)
            db.flush()
            db.add(
                ScientificIdentifier(
                    entity_id=entity.id,
                    namespace=self.primary_identifier_namespace,
                    identifier=normalized.external_identifier,
                    identifier_normalized=normalized.external_identifier.strip().upper(),
                    verification_status=IdentifierVerificationStatus.VERIFIED,
                )
            )
            # Flush explícito: a sessão de produção usa autoflush=False (ver db.py::SessionLocal),
            # e um lote com vários CIDs pode ser processado na MESMA sessão/transação (Fase D) --
            # sem este flush, o identificador recém-criado ficaria invisível a qualquer
            # db.query(ScientificIdentifier) subsequente até um commit externo, fazendo o mesmo
            # CID ser tratado como "novo" outra vez dentro do mesmo lote (bug real encontrado por
            # test_reconcile_same_cid_twice_reuses_entity_not_duplicated).
            db.flush()

        # InChIKey: identificador químico adicional -- nunca base de fusão automática. Apenas
        # detectamos e registramos quando o MESMO InChIKey já pertence a uma entidade DIFERENTE
        # da que o identificador primário resolveu (colisão real, nunca resolvida aqui).
        if normalized.inchikey:
            inchikey_normalized = normalized.inchikey.strip().upper()
            existing_inchikey = (
                db.query(ScientificIdentifier)
                .filter(
                    ScientificIdentifier.namespace == "inchikey",
                    ScientificIdentifier.identifier_normalized == inchikey_normalized,
                )
                .first()
            )
            if existing_inchikey is not None and existing_inchikey.entity_id != entity.id:
                conflicts.append(
                    ConflictReport(
                        conflict_type=IngestionConflictType.INCHIKEY_SHARED_WITH_OTHER_ENTITY,
                        entity_id=entity.id,
                        other_entity_id=existing_inchikey.entity_id,
                        details={
                            "inchikey": normalized.inchikey,
                            "identifier_namespace": self.primary_identifier_namespace,
                            "identifier_value": normalized.external_identifier,
                            "note": (
                                "InChIKey já registrado em outra entidade -- possível duplicata "
                                "de substância sob identificadores externos diferentes. Não "
                                "fundido automaticamente; requer decisão humana (ReviewDecision)."
                            ),
                        },
                    )
                )
            elif existing_inchikey is None:
                db.add(
                    ScientificIdentifier(
                        entity_id=entity.id,
                        namespace="inchikey",
                        identifier=normalized.inchikey,
                        identifier_normalized=inchikey_normalized,
                        verification_status=IdentifierVerificationStatus.VERIFIED,
                    )
                )
                # Mesmo motivo do flush acima: torna este InChIKey visível a uma checagem de
                # colisão feita para outro CID ainda dentro do mesmo lote/transação.
                db.flush()

        return ReconcileOutcome(entity=entity, entity_is_new=entity_is_new, conflicts=conflicts)

    def persist(
        self,
        db: Session,
        *,
        normalized: NormalizedExternalRecord,
        fetch_result: FetchResult,
        source_id: str,
        raw_source_record: RawSourceRecord | None,
        reconcile_outcome: ReconcileOutcome,
    ) -> PersistOutcome:
        """Persiste as observações de propriedade calculadas do registro normalizado. NUNCA
        sobrescreve uma observação já `REVIEWED` -- uma nova linha é sempre criada quando o
        fingerprint difere; quando o fingerprint é idêntico a uma já existente, a observação é
        tratada como `unchanged` (deduplicação, não sobrescrita)."""
        entity = reconcile_outcome.entity
        created_observations = 0
        any_new = False

        for prop in normalized.calculated_properties:
            prop_def = (
                db.query(PropertyDefinition).filter(PropertyDefinition.canonical_key == prop.property_key).first()
            )
            if prop_def is None:
                prop_def = PropertyDefinition(
                    canonical_key=prop.property_key,
                    name=prop.property_key.replace("_", " ").title(),
                    dimension="chemical",
                    canonical_unit=prop.unit,
                    value_type="numeric" if prop.value_numeric is not None else "text",
                    applicable_domain="chemical_substance",
                )
                db.add(prop_def)
                db.flush()

            fingerprint = compute_observation_fingerprint(
                entity_id=entity.id,
                property_definition_id=prop_def.id,
                source_id=source_id,
                value_numeric=prop.value_numeric,
                value_min=None,
                value_max=None,
                value_text=prop.value_text,
                unit_original=prop.unit,
                method=f"{self.connector_id}:{self.connector_version}",
                conditions_key=None,
            )
            existing_observation = (
                db.query(PropertyObservation).filter(PropertyObservation.dedup_fingerprint == fingerprint).first()
            )
            if existing_observation is not None:
                # Unchanged -- mesma entidade+propriedade+fonte+valor+unidade+método já
                # registrados. Nunca duplicado, nunca sobrescrito.
                continue

            db.add(
                PropertyObservation(
                    organization_id=None,
                    entity_id=entity.id,
                    property_definition_id=prop_def.id,
                    value_numeric=prop.value_numeric,
                    value_text=prop.value_text,
                    unit_original=prop.unit,
                    method=f"{self.connector_id}:{self.connector_version}",
                    evidence_type=prop.evidence_type,
                    source_id=source_id,
                    review_status=CurationState.DRAFT,
                    notes=(
                        f"Importado automaticamente de {normalized.source_name} em "
                        f"{fetch_result.fetched_at.isoformat()}. Não revisado."
                    ),
                    dedup_fingerprint=fingerprint,
                    raw_source_record_id=raw_source_record.id if raw_source_record else None,
                )
            )
            created_observations += 1
            any_new = True

        db.flush()

        db.add(
            AuditEvent(
                event_type="scientific_ingestion_persisted",
                description=(
                    f"Conector {self.connector_id} v{self.connector_version} persistiu "
                    f"{created_observations} observação(ões) nova(s) para a entidade {entity.id} "
                    f"(identificador externo {normalized.external_identifier})."
                ),
            )
        )

        return PersistOutcome(
            external_id=normalized.external_identifier,
            entity_id=entity.id,
            raw_source_record_id=raw_source_record.id if raw_source_record else None,
            created_entity=reconcile_outcome.entity_is_new,
            created_observations=created_observations,
            unchanged=not any_new and not reconcile_outcome.entity_is_new,
            conflicts=reconcile_outcome.conflicts,
            rejected=False,
        )

    def summarize(self, outcomes: list[PersistOutcome]) -> dict:
        """Contadores agregados -- mapeiam diretamente para os campos já existentes de
        `IngestionRun` (Rodada 1, sem nenhuma alteração de schema): `received_count` = total de
        identificadores solicitados; `created_count` = entidades novas; `updated_count` =
        observações novas adicionadas a entidades já existentes; `skipped_count` = identificadores
        sem nenhuma mudança (`unchanged`); `rejected_count` = identificadores que falharam."""
        return {
            "received_count": len(outcomes),
            "created_count": sum(1 for o in outcomes if o.created_entity),
            "updated_count": sum(o.created_observations for o in outcomes if not o.created_entity),
            "skipped_count": sum(1 for o in outcomes if o.unchanged),
            "rejected_count": sum(1 for o in outcomes if o.rejected),
            "conflicts_count": sum(len(o.conflicts) for o in outcomes),
        }
