"""API mínima de pesquisa do banco de dados científico (Incremento 2.3, Rodada 1, Fase D).

Deliberadamente minimal: expõe apenas o necessário para provar o domínio (leitura de
entidades/identificadores/observações/proveniência/produtos de fornecedor/estruturas
cristalográficas/histórico de revisão, mais criação de entidade e de decisão de revisão).
Criação de PropertyObservation/ScientificIdentifier/ScientificSource/BibliographicReference/
Supplier/SupplierProduct/CrystalStructureReference NÃO é exposta via API nesta rodada -- esses
registros são povoados apenas pelo seed sintético (Fase E), mantendo a superfície de API
deliberadamente pequena ("não construir ainda uma interface administrativa extensa").

Autorização: leitura exige apenas usuário autenticado, com escopo por organização -- um
registro é visível se `organization_id is None` (global/público) OU se
`organization_id == current_user.organization_id` (privado da própria organização); qualquer
outro caso resulta em 404 (nunca 403, para não vazar a existência do registro de outra
organização). Escrita e revisão exigem `require_admin` (papel curador/administrador).
Dados ainda não revisados (`review_status != REVIEWED`) continuam visíveis mas devem ser
tratados como não revisados pelo consumidor -- os schemas sempre incluem `review_status`
para que isso nunca fique implícito.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.scientific_data import (
    BibliographicReference,
    BiologicalEvidence,
    CrystalStructureReference,
    CurationState,
    PropertyDefinition,
    PropertyObservation,
    ReviewDecision,
    ScientificEntity,
    ScientificIdentifier,
    ScientificSource,
    SupplierProduct,
)
from biomatcad_api.models.scientific_ingestion import IngestionConflict, RawSourceRecord
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user, require_admin
from biomatcad_api.schemas.scientific_data import (
    BibliographicReferenceResponse,
    BiologicalEvidenceResponse,
    CrystalStructureReferenceResponse,
    PropertyDefinitionResponse,
    PropertyObservationResponse,
    ProvenanceEntry,
    ReviewDecisionCreateRequest,
    ReviewDecisionResponse,
    ScientificEntityCreateRequest,
    ScientificEntityDetail,
    ScientificEntitySummary,
    ScientificIdentifierResponse,
    ScientificSourceResponse,
    SupplierProductResponse,
)
from biomatcad_api.schemas.scientific_ingestion import (
    IngestionConflictResponse,
    RawSourceRecordResponse,
)

router = APIRouter(prefix="/api/v1/scientific-entities", tags=["scientific-data"])


def _visibility_filter(current_user: User):
    """Registro visível se global (organization_id NULL) OU da própria organização do usuário."""
    return or_(
        ScientificEntity.organization_id.is_(None),
        ScientificEntity.organization_id == current_user.organization_id,
    )


def _get_visible_entity(entity_id: str, db: Session, current_user: User) -> ScientificEntity:
    entity = (
        db.query(ScientificEntity)
        .filter(ScientificEntity.id == entity_id, _visibility_filter(current_user))
        .first()
    )
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entidade científica não encontrada.")
    return entity


@router.post("", response_model=ScientificEntityDetail, status_code=201)
def create_scientific_entity(
    payload: ScientificEntityCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ScientificEntity:
    """Cria uma entidade científica privada da organização do curador. Criação de registro
    global (organization_id NULL) deliberadamente não exposta nesta rodada."""
    entity = ScientificEntity(
        organization_id=current_user.organization_id,
        entity_type=payload.entity_type,
        preferred_name=payload.preferred_name,
        description=payload.description,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


@router.get("", response_model=list[ScientificEntitySummary])
def list_scientific_entities(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ScientificEntity]:
    return (
        db.query(ScientificEntity)
        .filter(_visibility_filter(current_user))
        .order_by(ScientificEntity.created_at.desc())
        .all()
    )


@router.get("/property-definitions", response_model=list[PropertyDefinitionResponse])
def list_property_definitions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[PropertyDefinition]:
    """Vocabulário canônico de propriedades (Adendo de Interface Científica Mínima, Fase L) --
    vocabulário global, não escopado por organização (ver PropertyDefinition, sem
    organization_id). Permite ao frontend traduzir `property_definition_id` em nome/unidade
    legíveis sem precisar de N chamadas por observação. Declarado ANTES de `/{entity_id}` para
    que "property-definitions" nunca seja capturado como um valor de entity_id."""
    return db.query(PropertyDefinition).order_by(PropertyDefinition.name.asc()).all()


@router.get("/sources", response_model=list[ScientificSourceResponse])
def list_scientific_sources(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ScientificSource]:
    """Lista de `ScientificSource` (Adendo de Interface Científica Mínima, Fase L/O) -- permite
    ao painel administrativo de ingestão escolher um `source_id` real sem precisar conhecer o
    UUID de antemão (ex.: o registro "PubChem" criado por `ensure_pubchem_source.py`, ou os
    registros fictícios do seed de demonstração). Vocabulário global, não escopado por
    organização. Declarado ANTES de `/{entity_id}` pela mesma razão de `/property-definitions`."""
    return db.query(ScientificSource).order_by(ScientificSource.name.asc()).all()


@router.get("/{entity_id}", response_model=ScientificEntityDetail)
def get_scientific_entity(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ScientificEntity:
    entity = (
        db.query(ScientificEntity)
        .options(joinedload(ScientificEntity.identifiers))
        .filter(ScientificEntity.id == entity_id, _visibility_filter(current_user))
        .first()
    )
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entidade científica não encontrada.")
    return entity


@router.get("/{entity_id}/identifiers", response_model=list[ScientificIdentifierResponse])
def list_entity_identifiers(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ScientificIdentifier]:
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(ScientificIdentifier)
        .filter(ScientificIdentifier.entity_id == entity_id)
        .order_by(ScientificIdentifier.created_at.asc())
        .all()
    )


@router.get("/{entity_id}/property-observations", response_model=list[PropertyObservationResponse])
def list_entity_property_observations(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[PropertyObservation]:
    """Retorna TODAS as observações da entidade, inclusive divergentes entre si -- nunca só a
    "mais recente" ou a "mais confiável": deduplicação apenas impede duplicatas verdadeiras
    (mesmo fingerprint), nunca oculta valores genuinamente diferentes."""
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(PropertyObservation)
        .filter(PropertyObservation.entity_id == entity_id)
        .order_by(PropertyObservation.created_at.asc())
        .all()
    )


@router.get("/{entity_id}/provenance", response_model=list[ProvenanceEntry])
def list_entity_provenance(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ProvenanceEntry]:
    """Consolida, por observação, a referência bibliográfica e a fonte associadas -- a visão de
    'de onde veio este dado' referenciada na Fase D."""
    _get_visible_entity(entity_id, db, current_user)
    observations = (
        db.query(PropertyObservation).filter(PropertyObservation.entity_id == entity_id).all()
    )
    entries: list[ProvenanceEntry] = []
    for obs in observations:
        reference = (
            db.query(BibliographicReference).filter(BibliographicReference.id == obs.reference_id).first()
            if obs.reference_id
            else None
        )
        source = (
            db.query(ScientificSource).filter(ScientificSource.id == obs.source_id).first()
            if obs.source_id
            else None
        )
        entries.append(
            ProvenanceEntry(
                observation_id=obs.id,
                reference=BibliographicReferenceResponse.model_validate(reference) if reference else None,
                source=ScientificSourceResponse.model_validate(source) if source else None,
            )
        )
    return entries


@router.get("/{entity_id}/supplier-products", response_model=list[SupplierProductResponse])
def list_entity_supplier_products(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[SupplierProduct]:
    """Produtos de fornecedor vinculados à entidade -- nunca substituem nem se confundem com a
    entidade canônica em si; ver docstring de SupplierProduct."""
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(SupplierProduct)
        .filter(SupplierProduct.entity_id == entity_id)
        .order_by(SupplierProduct.created_at.asc())
        .all()
    )


@router.get("/{entity_id}/crystal-structures", response_model=list[CrystalStructureReferenceResponse])
def list_entity_crystal_structures(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[CrystalStructureReference]:
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(CrystalStructureReference)
        .filter(CrystalStructureReference.entity_id == entity_id)
        .order_by(CrystalStructureReference.created_at.asc())
        .all()
    )


@router.get("/{entity_id}/review-history", response_model=list[ReviewDecisionResponse])
def list_entity_review_history(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[ReviewDecision]:
    """Trilha completa e append-only de decisões de revisão da entidade."""
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(ReviewDecision)
        .filter(ReviewDecision.subject_type == "ScientificEntity", ReviewDecision.subject_id == entity_id)
        .order_by(ReviewDecision.created_at.asc())
        .all()
    )


@router.post("/{entity_id}/review-decisions", response_model=ReviewDecisionResponse, status_code=201)
def create_entity_review_decision(
    entity_id: str,
    payload: ReviewDecisionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ReviewDecision:
    """Registra uma decisão de revisão e atualiza o `review_status` da própria entidade (não é
    sobrescrita de valor científico -- é o campo de status da própria entidade, análogo ao que
    já ocorre em outros fluxos de curadoria do repositório). A trilha de decisões (ReviewDecision)
    em si nunca é editada ou apagada -- apenas novas linhas são adicionadas."""
    entity = _get_visible_entity(entity_id, db, current_user)

    previous_state = entity.review_status.value
    if payload.decision.value == "approved":
        new_state = "reviewed"
    elif payload.decision.value == "rejected":
        new_state = "rejected"
    else:
        new_state = previous_state

    decision = ReviewDecision(
        organization_id=entity.organization_id,
        subject_type="ScientificEntity",
        subject_id=entity_id,
        decision=payload.decision,
        reviewer_user_id=current_user.id,
        justification=payload.justification,
        previous_state=previous_state,
        new_state=new_state,
    )
    db.add(decision)

    if new_state != previous_state:
        entity.review_status = CurationState(new_state)

    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="scientific_entity_review_decision",
            description=(
                f"{current_user.email} registrou decisão '{payload.decision.value}' para "
                f"ScientificEntity {entity_id}."
            ),
        )
    )

    db.commit()
    db.refresh(decision)
    return decision


@router.get("/{entity_id}/biological-evidence", response_model=list[BiologicalEvidenceResponse])
def list_entity_biological_evidence(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[BiologicalEvidence]:
    """Evidência biológica da entidade (Adendo de Interface Científica Mínima, Fase L) --
    `research_classification_only` é sempre True nesta rodada; a interface nunca deve
    apresentar isto como validação clínica (ver docstring de BiologicalEvidence)."""
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(BiologicalEvidence)
        .filter(BiologicalEvidence.entity_id == entity_id)
        .order_by(BiologicalEvidence.created_at.asc())
        .all()
    )


@router.get("/{entity_id}/raw-source-records", response_model=list[RawSourceRecordResponse])
def list_entity_raw_source_records(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[RawSourceRecord]:
    """Snapshots brutos versionados (Adendo de Interface Científica Mínima, Fase L) -- a aba
    "Snapshots" do detalhe de entidade. Reconstituído via `PropertyObservation.raw_source_record_id`
    (coluna aditiva da Rodada 2) -- nunca por casamento de identificador externo direto, que
    seria frágil a mudanças no conector. Apenas leitura; não expõe `payload_json` bruto aqui
    (ver RawSourceRecordResponse) para manter a resposta compacta -- o payload completo
    permanece disponível via `scripts/pubchem_pilot_report.py` para inspeção administrativa."""
    _get_visible_entity(entity_id, db, current_user)
    record_ids = {
        obs.raw_source_record_id
        for obs in db.query(PropertyObservation.raw_source_record_id)
        .filter(
            PropertyObservation.entity_id == entity_id,
            PropertyObservation.raw_source_record_id.is_not(None),
        )
        .all()
    }
    if not record_ids:
        return []
    return (
        db.query(RawSourceRecord)
        .filter(RawSourceRecord.id.in_(record_ids))
        .order_by(RawSourceRecord.fetched_at.desc())
        .all()
    )


@router.get("/{entity_id}/conflicts", response_model=list[IngestionConflictResponse])
def list_entity_conflicts(
    entity_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[IngestionConflict]:
    """Conflitos de ingestão que referenciam esta entidade, como entidade principal OU como a
    "outra entidade" colidente (Adendo de Interface Científica Mínima, Fase L) -- nunca
    resolvidos automaticamente por esta rota, apenas expostos para decisão humana futura (ver
    services/connectors/base.py::reconcile)."""
    _get_visible_entity(entity_id, db, current_user)
    return (
        db.query(IngestionConflict)
        .filter(
            or_(
                IngestionConflict.entity_id == entity_id,
                IngestionConflict.other_entity_id == entity_id,
            )
        )
        .order_by(IngestionConflict.created_at.desc())
        .all()
    )
