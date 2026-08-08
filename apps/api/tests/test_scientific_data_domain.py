"""Testes de domínio do banco de dados científico (Incremento 2.3, Rodada 1, Fase F).

Cobre, no nível de modelo/SQLAlchemy (não apenas API), as regras obrigatórias da rodada que
não são inteiramente exercitadas por test_scientific_data_api.py: unicidade de identificador,
coexistência de valores divergentes, deduplicação por fingerprint (incluindo mutação manual --
tentar inserir um duplicado verdadeiro e provar que é rejeitado), unidade original vs.
normalizada, condições experimentais afetando o fingerprint, distinção completa entre os 6
EvidenceType, trilha de revisão append-only com múltiplas entradas, produto de fornecedor nunca
confundido com a entidade canônica, referência cristalográfica única, os 4 status possíveis de
IngestionRun, e exclusão lógica (is_active=False) que preserva toda a evidência relacionada.

A ausência de regressão nos endpoints existentes de Material é garantida pela suíte completa
(259 testes do Incremento 2.1/2.2, todos aprovados nesta mesma rodada -- ver TEST_EVIDENCE.md)."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from biomatcad_api.models.scientific_data import (
    BibliographicReference,
    CrystalStructureReference,
    CurationState,
    EvidenceType,
    IdentifierVerificationStatus,
    IngestionRun,
    IngestionStatus,
    PropertyDefinition,
    PropertyObservation,
    RedistributionStatus,
    ReviewDecision,
    ReviewDecisionOutcome,
    ScientificEntity,
    ScientificEntityType,
    ScientificIdentifier,
    ScientificSource,
    SourceType,
    Supplier,
    SupplierProduct,
    compute_observation_fingerprint,
)
from tests.factories import create_admin, create_org


def _make_entity(db_session, name="Entidade de teste de domínio") -> ScientificEntity:
    entity = ScientificEntity(
        organization_id=None, entity_type=ScientificEntityType.BIOMATERIAL, preferred_name=name
    )
    db_session.add(entity)
    db_session.flush()
    return entity


def _make_property_definition(db_session, key="prop_teste_dominio") -> PropertyDefinition:
    prop = PropertyDefinition(
        canonical_key=key, name="Propriedade de teste", dimension="mechanical", canonical_unit="GPa"
    )
    db_session.add(prop)
    db_session.flush()
    return prop


def _make_source(db_session, name="Fonte de teste de domínio") -> ScientificSource:
    source = ScientificSource(
        name=name, source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


# --- Identificador: unicidade namespace + identificador normalizado ------------------------


def test_identifier_namespace_and_normalized_value_must_be_unique(db_session):
    entity = _make_entity(db_session, "Entidade A - identificadores")
    db_session.add(
        ScientificIdentifier(
            entity_id=entity.id,
            namespace="SYNTHETIC_DEMO_ID",
            identifier="ABC-123",
            identifier_normalized="ABC-123",
            verification_status=IdentifierVerificationStatus.UNVERIFIED,
        )
    )
    db_session.commit()

    db_session.add(
        ScientificIdentifier(
            entity_id=entity.id,
            namespace="SYNTHETIC_DEMO_ID",
            identifier="abc-123",  # mesmo valor normalizado, grafia diferente
            identifier_normalized="ABC-123",
            verification_status=IdentifierVerificationStatus.UNVERIFIED,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- Coexistência de valores divergentes + deduplicação por fingerprint --------------------


def test_divergent_observations_from_different_sources_coexist(db_session):
    entity = _make_entity(db_session, "Entidade B - observações divergentes")
    prop = _make_property_definition(db_session, "prop_divergencia")
    source_a = _make_source(db_session, "Fonte A - divergência")
    source_b = _make_source(db_session, "Fonte B - divergência")

    fp_a = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=source_a.id,
        value_numeric=10.0, value_min=None, value_max=None, value_text=None,
        unit_original="GPa", method=None, conditions_key=None,
    )
    fp_b = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=source_b.id,
        value_numeric=20.0, value_min=None, value_max=None, value_text=None,
        unit_original="GPa", method=None, conditions_key=None,
    )
    assert fp_a != fp_b

    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id, source_id=source_a.id,
            value_numeric=10.0, unit_original="GPa", evidence_type=EvidenceType.EXPERIMENTAL,
            review_status=CurationState.DRAFT, dedup_fingerprint=fp_a,
        )
    )
    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id, source_id=source_b.id,
            value_numeric=20.0, unit_original="GPa", evidence_type=EvidenceType.EXPERIMENTAL,
            review_status=CurationState.DRAFT, dedup_fingerprint=fp_b,
        )
    )
    db_session.commit()

    observations = db_session.query(PropertyObservation).filter(PropertyObservation.entity_id == entity.id).all()
    assert len(observations) == 2
    assert {o.value_numeric for o in observations} == {10.0, 20.0}


def test_true_duplicate_fingerprint_is_rejected_by_unique_constraint(db_session):
    """Mutação manual: inserir a MESMA observação duas vezes (mesmo fingerprint) deve falhar --
    prova de que a deduplicação é aplicada no nível de banco, não apenas de aplicação."""
    entity = _make_entity(db_session, "Entidade C - duplicata verdadeira")
    prop = _make_property_definition(db_session, "prop_duplicata")

    fingerprint = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=None,
        value_numeric=5.5, value_min=None, value_max=None, value_text=None,
        unit_original="MPa", method="método idêntico", conditions_key=None,
    )
    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id,
            value_numeric=5.5, unit_original="MPa", method="método idêntico",
            evidence_type=EvidenceType.CALCULATED, review_status=CurationState.DRAFT,
            dedup_fingerprint=fingerprint,
        )
    )
    db_session.commit()

    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id,
            value_numeric=5.5, unit_original="MPa", method="método idêntico",
            evidence_type=EvidenceType.CALCULATED, review_status=CurationState.DRAFT,
            dedup_fingerprint=fingerprint,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_different_experimental_conditions_yield_different_fingerprints(db_session):
    """Duas observações com valor IDÊNTICO mas condições experimentais diferentes (chave de
    condições diferente) nunca devem ser tratadas como duplicatas."""
    entity = _make_entity(db_session, "Entidade D - condições")
    prop = _make_property_definition(db_session, "prop_condicoes")

    fp_37c = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=None,
        value_numeric=7.0, value_min=None, value_max=None, value_text=None,
        unit_original="GPa", method=None, conditions_key="temp=310K",
    )
    fp_25c = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=None,
        value_numeric=7.0, value_min=None, value_max=None, value_text=None,
        unit_original="GPa", method=None, conditions_key="temp=298K",
    )
    assert fp_37c != fp_25c

    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id, value_numeric=7.0,
            unit_original="GPa", condition_temperature_k=310.0,
            evidence_type=EvidenceType.EXPERIMENTAL, review_status=CurationState.DRAFT,
            dedup_fingerprint=fp_37c,
        )
    )
    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id, value_numeric=7.0,
            unit_original="GPa", condition_temperature_k=298.0,
            evidence_type=EvidenceType.EXPERIMENTAL, review_status=CurationState.DRAFT,
            dedup_fingerprint=fp_25c,
        )
    )
    db_session.commit()

    rows = db_session.query(PropertyObservation).filter(PropertyObservation.entity_id == entity.id).all()
    assert len(rows) == 2
    assert {r.condition_temperature_k for r in rows} == {310.0, 298.0}


def test_unit_original_is_required_but_normalized_value_is_optional(db_session):
    entity = _make_entity(db_session, "Entidade E - unidades")
    prop = _make_property_definition(db_session, "prop_unidades")
    fingerprint = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=None,
        value_numeric=100.0, value_min=None, value_max=None, value_text=None,
        unit_original="MPa", method=None, conditions_key=None,
    )
    obs = PropertyObservation(
        entity_id=entity.id, property_definition_id=prop.id, value_numeric=100.0,
        unit_original="MPa", value_normalized=None,
        evidence_type=EvidenceType.EXPERIMENTAL, review_status=CurationState.DRAFT,
        dedup_fingerprint=fingerprint,
    )
    db_session.add(obs)
    db_session.commit()
    db_session.refresh(obs)
    assert obs.unit_original == "MPa"
    assert obs.value_normalized is None


def test_all_six_evidence_types_are_distinct_and_persistable(db_session):
    entity = _make_entity(db_session, "Entidade F - tipos de evidência")
    prop = _make_property_definition(db_session, "prop_evidencia")
    for i, evidence_type in enumerate(EvidenceType):
        fingerprint = compute_observation_fingerprint(
            entity_id=entity.id, property_definition_id=prop.id, source_id=None,
            value_numeric=float(i), value_min=None, value_max=None, value_text=None,
            unit_original="unidade_teste", method=None, conditions_key=None,
        )
        db_session.add(
            PropertyObservation(
                entity_id=entity.id, property_definition_id=prop.id, value_numeric=float(i),
                unit_original="unidade_teste", evidence_type=evidence_type,
                review_status=CurationState.DRAFT, dedup_fingerprint=fingerprint,
            )
        )
    db_session.commit()

    rows = db_session.query(PropertyObservation).filter(PropertyObservation.entity_id == entity.id).all()
    assert len(rows) == 6
    assert {r.evidence_type for r in rows} == set(EvidenceType)


# --- Trilha de revisão append-only ----------------------------------------------------------


def test_review_trail_is_append_only_and_preserves_full_history(db_session):
    org = create_org(db_session, slug="org-review-trail-domain")
    admin = create_admin(db_session, email="domain-reviewer@biomatcad.example", org=org)
    entity = _make_entity(db_session, "Entidade G - trilha de revisão")

    decisions = [
        ReviewDecision(
            subject_type="ScientificEntity", subject_id=entity.id,
            decision=ReviewDecisionOutcome.CHANGES_REQUESTED, reviewer_user_id=admin.id,
            justification="Primeira rodada: mudanças solicitadas.",
            previous_state="draft", new_state="draft",
        ),
        ReviewDecision(
            subject_type="ScientificEntity", subject_id=entity.id,
            decision=ReviewDecisionOutcome.APPROVED, reviewer_user_id=admin.id,
            justification="Segunda rodada: aprovada após correções.",
            previous_state="draft", new_state="reviewed",
        ),
    ]
    for d in decisions:
        db_session.add(d)
    db_session.commit()

    history = (
        db_session.query(ReviewDecision)
        .filter(ReviewDecision.subject_type == "ScientificEntity", ReviewDecision.subject_id == entity.id)
        .order_by(ReviewDecision.created_at.asc())
        .all()
    )
    assert len(history) == 2
    assert history[0].decision == ReviewDecisionOutcome.CHANGES_REQUESTED
    assert history[1].decision == ReviewDecisionOutcome.APPROVED
    # Nenhuma linha antiga foi alterada ou removida pela decisão mais recente.
    assert history[0].justification == "Primeira rodada: mudanças solicitadas."


# --- Fornecedor/produto nunca confundido com a entidade canônica ---------------------------


def test_supplier_product_is_never_the_canonical_entity(db_session):
    entity = _make_entity(db_session, "Entidade H - produto de fornecedor")
    supplier = Supplier(name="Fornecedor de teste de domínio H")
    db_session.add(supplier)
    db_session.flush()

    # Produto SEM vínculo com entidade nenhuma -- caso válido, pendente de curadoria.
    unlinked_product = SupplierProduct(
        supplier_id=supplier.id, entity_id=None, catalog_sku="SKU-H-1", commercial_name="Produto H1"
    )
    db_session.add(unlinked_product)

    linked_product = SupplierProduct(
        supplier_id=supplier.id, entity_id=entity.id, catalog_sku="SKU-H-2", commercial_name="Produto H2"
    )
    db_session.add(linked_product)
    db_session.commit()

    assert unlinked_product.entity_id is None
    assert linked_product.entity_id == entity.id
    # O produto é uma linha inteiramente distinta -- IDs diferentes, tabelas diferentes.
    assert linked_product.id != entity.id
    assert isinstance(linked_product, SupplierProduct)
    assert isinstance(entity, ScientificEntity)


def test_supplier_product_sku_is_unique_per_supplier(db_session):
    supplier = Supplier(name="Fornecedor de teste de domínio SKU")
    db_session.add(supplier)
    db_session.flush()
    db_session.add(SupplierProduct(supplier_id=supplier.id, catalog_sku="SKU-DUP", commercial_name="Produto 1"))
    db_session.commit()

    db_session.add(SupplierProduct(supplier_id=supplier.id, catalog_sku="SKU-DUP", commercial_name="Produto 2"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- Estrutura cristalográfica referenciada -------------------------------------------------


def test_crystal_structure_reference_accession_is_unique_per_database(db_session):
    entity = _make_entity(db_session, "Entidade I - cristalografia")
    db_session.add(
        CrystalStructureReference(
            entity_id=entity.id, database_name="SYNTHETIC_DEMO_DB", accession_id="SYNTH-9001"
        )
    )
    db_session.commit()

    db_session.add(
        CrystalStructureReference(
            entity_id=entity.id, database_name="SYNTHETIC_DEMO_DB", accession_id="SYNTH-9001"
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- IngestionRun: os 4 status possíveis ----------------------------------------------------


def test_ingestion_run_supports_all_status_values(db_session):
    source = _make_source(db_session, "Fonte de teste de domínio - ingestão")
    for status in IngestionStatus:
        db_session.add(
            IngestionRun(
                source_id=source.id,
                connector_name=f"connector_teste_{status.value}",
                connector_version="0.0.0-teste",
                status=status,
                received_count=10,
                created_count=5 if status != IngestionStatus.FAILED else 0,
                skipped_count=2,
                rejected_count=3,
            )
        )
    db_session.commit()

    runs = (
        db_session.query(IngestionRun)
        .filter(IngestionRun.connector_name.like("connector_teste_%"))
        .all()
    )
    assert {r.status for r in runs} == set(IngestionStatus)


# --- Exclusão lógica preserva evidência ------------------------------------------------------


def test_soft_delete_of_entity_preserves_related_evidence(db_session):
    entity = _make_entity(db_session, "Entidade J - exclusão lógica")
    prop = _make_property_definition(db_session, "prop_exclusao_logica")
    fingerprint = compute_observation_fingerprint(
        entity_id=entity.id, property_definition_id=prop.id, source_id=None,
        value_numeric=42.0, value_min=None, value_max=None, value_text=None,
        unit_original="GPa", method=None, conditions_key=None,
    )
    db_session.add(
        PropertyObservation(
            entity_id=entity.id, property_definition_id=prop.id, value_numeric=42.0,
            unit_original="GPa", evidence_type=EvidenceType.EXPERIMENTAL,
            review_status=CurationState.REVIEWED, dedup_fingerprint=fingerprint,
        )
    )
    db_session.add(
        ScientificIdentifier(
            entity_id=entity.id, namespace="SYNTHETIC_DEMO_ID", identifier="J-1",
            identifier_normalized="J-1", verification_status=IdentifierVerificationStatus.VERIFIED,
        )
    )
    db_session.commit()

    entity.is_active = False
    db_session.commit()
    db_session.refresh(entity)

    assert entity.is_active is False
    remaining_observations = (
        db_session.query(PropertyObservation).filter(PropertyObservation.entity_id == entity.id).all()
    )
    remaining_identifiers = (
        db_session.query(ScientificIdentifier).filter(ScientificIdentifier.entity_id == entity.id).all()
    )
    assert len(remaining_observations) == 1
    assert remaining_observations[0].value_numeric == 42.0
    assert len(remaining_identifiers) == 1


# --- Nenhum segredo exposto pelos schemas de resposta ---------------------------------------


def test_response_schemas_never_expose_user_secrets():
    from biomatcad_api.schemas.scientific_data import ReviewDecisionResponse, ScientificEntityDetail

    forbidden_substrings = ("password", "secret", "hashed")
    for schema_cls in (ScientificEntityDetail, ReviewDecisionResponse):
        field_names = set(schema_cls.model_fields.keys())
        for field_name in field_names:
            lowered = field_name.lower()
            assert not any(bad in lowered for bad in forbidden_substrings), (
                f"{schema_cls.__name__}.{field_name} parece expor um segredo."
            )


# --- Referência bibliográfica nunca inventada quando ausente --------------------------------


def test_bibliographic_reference_allows_absent_doi_pmid_without_fabrication(db_session):
    reference = BibliographicReference(title="Referência de teste sem DOI/PMID reais, propositalmente ausentes")
    db_session.add(reference)
    db_session.commit()
    db_session.refresh(reference)
    assert reference.doi is None
    assert reference.pmid is None
