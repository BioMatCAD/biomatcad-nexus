"""Seed científico sintético (Incremento 2.3, Rodada 1, Fase E).

Uso: python -m biomatcad_api.seed_scientific_data

Popula um conjunto pequeno e EXCLUSIVAMENTE SINTÉTICO para exercitar o domínio de
models/scientific_data.py de ponta a ponta: uma entidade de cada tipo obrigatório
(biomaterial, substância química, fármaco, formulação, nanomaterial), um produto de
fornecedor fictício, uma referência bibliográfica fictícia, observações conflitantes de duas
fontes sintéticas distintas sobre a MESMA propriedade da MESMA entidade (nunca sobrescritas --
ambas coexistem, ver compute_observation_fingerprint), uma referência cristalográfica sintética,
e entidades nos três estados de curadoria (draft/reviewed/rejected).

NENHUM identificador real é usado: nenhum DOI/PMID/CAS/CID/accession de banco real aparece em
lugar nenhum deste arquivo -- todos os identificadores têm o prefixo "SYNTHETIC-DEMO-" ou
equivalente, e todo texto humano-legível (nomes, títulos, descrições) é explicitamente marcado
como fictício/sintético/de demonstração. Este seed NÃO faz nenhuma chamada de rede -- é
inserção direta via SQLAlchemy, sem nenhum conector de ingestão real (ver IngestionRun: o
registro criado aqui documenta o CONTRATO, não uma execução real contra PubChem/ChEBI/etc.).

Idempotente: reexecutável sem duplicar linhas, seguindo o mesmo padrão de `_ensure_user` em
seed.py (get_or_create por chave natural)."""
from __future__ import annotations

from datetime import datetime, timezone

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.organization import Organization
from biomatcad_api.models.scientific_data import (
    BibliographicReference,
    BiologicalEvidence,
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
from biomatcad_api.models.user import User
from biomatcad_api.seed import SYNTHETIC_ADMIN_EMAIL, SYNTHETIC_ORG_SLUG

# ---------------------------------------------------------------------------
# Definições de propriedade canônicas usadas pelas observações sintéticas
# ---------------------------------------------------------------------------

PROPERTY_YOUNG_MODULUS = "young_modulus_demo"
PROPERTY_MELTING_POINT = "melting_point_demo"


def _get_or_create_property_definition(
    db, *, canonical_key: str, name: str, dimension: str, canonical_unit: str
) -> PropertyDefinition:
    existing = db.query(PropertyDefinition).filter(PropertyDefinition.canonical_key == canonical_key).first()
    if existing is not None:
        return existing
    prop_def = PropertyDefinition(
        canonical_key=canonical_key,
        name=name,
        dimension=dimension,
        canonical_unit=canonical_unit,
        value_type="numeric",
        applicable_domain="generic",
    )
    db.add(prop_def)
    db.flush()
    return prop_def


def _get_or_create_source(
    db, *, name: str, source_type: SourceType, redistribution_status: RedistributionStatus
) -> ScientificSource:
    existing = db.query(ScientificSource).filter(ScientificSource.name == name).first()
    if existing is not None:
        return existing
    source = ScientificSource(
        name=name,
        source_type=source_type,
        base_url=None,
        publisher="Fonte fictícia de demonstração -- não corresponde a nenhuma editora/banco real.",
        license="Uso interno de demonstração apenas -- não redistribuir.",
        version="demo-1",
        terms_of_use="Dado sintético, sem termos de uso reais associados.",
        accessed_at=datetime.now(timezone.utc),
        redistribution_status=redistribution_status,
    )
    db.add(source)
    db.flush()
    return source


def _get_or_create_reference(db, *, title: str) -> BibliographicReference:
    existing = db.query(BibliographicReference).filter(BibliographicReference.title == title).first()
    if existing is not None:
        return existing
    reference = BibliographicReference(
        doi=None,
        pmid=None,
        other_identifier="SYNTHETIC-DEMO-REF-0001",
        title=title,
        authors="Autores fictícios de demonstração",
        venue="Publicação fictícia de demonstração (não existe)",
        year=2026,
        url=None,
    )
    db.add(reference)
    db.flush()
    return reference


def _get_or_create_entity(
    db, *, preferred_name: str, entity_type: ScientificEntityType, description: str, review_status: CurationState
) -> ScientificEntity:
    existing = db.query(ScientificEntity).filter(ScientificEntity.preferred_name == preferred_name).first()
    if existing is not None:
        return existing
    entity = ScientificEntity(
        organization_id=None,  # registro global de demonstração, visível a qualquer usuário autenticado
        entity_type=entity_type,
        preferred_name=preferred_name,
        description=description,
        review_status=review_status,
    )
    db.add(entity)
    db.flush()
    return entity


def _ensure_identifier(
    db, *, entity: ScientificEntity, namespace: str, identifier: str, verification_status: IdentifierVerificationStatus
) -> None:
    identifier_normalized = identifier.strip().upper()
    existing = (
        db.query(ScientificIdentifier)
        .filter(
            ScientificIdentifier.namespace == namespace,
            ScientificIdentifier.identifier_normalized == identifier_normalized,
        )
        .first()
    )
    if existing is not None:
        return
    db.add(
        ScientificIdentifier(
            entity_id=entity.id,
            namespace=namespace,
            identifier=identifier,
            identifier_normalized=identifier_normalized,
            verification_status=verification_status,
        )
    )


def _ensure_observation(
    db,
    *,
    entity: ScientificEntity,
    property_definition: PropertyDefinition,
    source: ScientificSource | None,
    value_numeric: float,
    unit_original: str,
    method: str | None,
    evidence_type: EvidenceType,
    review_status: CurationState,
    notes: str,
    reference: BibliographicReference | None = None,
) -> PropertyObservation:
    fingerprint = compute_observation_fingerprint(
        entity_id=entity.id,
        property_definition_id=property_definition.id,
        source_id=source.id if source else None,
        value_numeric=value_numeric,
        value_min=None,
        value_max=None,
        value_text=None,
        unit_original=unit_original,
        method=method,
        conditions_key=None,
    )
    existing = (
        db.query(PropertyObservation).filter(PropertyObservation.dedup_fingerprint == fingerprint).first()
    )
    if existing is not None:
        return existing
    observation = PropertyObservation(
        organization_id=None,
        entity_id=entity.id,
        property_definition_id=property_definition.id,
        value_numeric=value_numeric,
        unit_original=unit_original,
        method=method,
        evidence_type=evidence_type,
        reference_id=reference.id if reference else None,
        source_id=source.id if source else None,
        review_status=review_status,
        notes=notes,
        dedup_fingerprint=fingerprint,
    )
    db.add(observation)
    db.flush()
    return observation


def run_seed_scientific_data() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == SYNTHETIC_ORG_SLUG).first()
        if org is None:
            raise RuntimeError(
                "Organização de demonstração ausente -- rode `python -m biomatcad_api.seed` antes deste seed."
            )
        admin = db.query(User).filter(User.email == SYNTHETIC_ADMIN_EMAIL).first()
        if admin is None:
            raise RuntimeError(
                "Usuário admin de demonstração ausente -- rode `python -m biomatcad_api.seed` antes deste seed."
            )

        # --- Definições de propriedade -----------------------------------------------------
        young_modulus = _get_or_create_property_definition(
            db,
            canonical_key=PROPERTY_YOUNG_MODULUS,
            name="Módulo de Young (demonstração)",
            dimension="mechanical",
            canonical_unit="GPa",
        )

        # --- Fontes sintéticas conflitantes -------------------------------------------------
        source_alpha = _get_or_create_source(
            db,
            name="Fonte Sintética Alfa de Demonstração",
            source_type=SourceType.DATABASE,
            redistribution_status=RedistributionStatus.UNKNOWN,
        )
        source_beta = _get_or_create_source(
            db,
            name="Fonte Sintética Beta de Demonstração",
            source_type=SourceType.PUBLISHER,
            redistribution_status=RedistributionStatus.PROHIBITED,
        )

        # --- Referência bibliográfica fictícia (claramente marcada) -------------------------
        fictitious_reference = _get_or_create_reference(
            db, title="Artigo fictício de demonstração sobre biomateriais sintéticos (não existe na realidade)"
        )

        # --- As 5 entidades canônicas obrigatórias ------------------------------------------
        biomaterial = _get_or_create_entity(
            db,
            preferred_name="Hidroxiapatita Sintética de Demonstração (fictícia)",
            entity_type=ScientificEntityType.BIOMATERIAL,
            description="Biomaterial fictício usado apenas para demonstrar o domínio científico. Sem dado real.",
            review_status=CurationState.REVIEWED,
        )
        chemical_substance = _get_or_create_entity(
            db,
            preferred_name="Ácido Poliláctico Fictício de Demonstração",
            entity_type=ScientificEntityType.CHEMICAL_SUBSTANCE,
            description="Substância química fictícia de demonstração. Sem dado real.",
            review_status=CurationState.DRAFT,
        )
        drug = _get_or_create_entity(
            db,
            preferred_name="Fármaco Fictício de Demonstração X-100",
            entity_type=ScientificEntityType.DRUG,
            description="Fármaco inteiramente fictício, criado apenas para teste do domínio. Não existe na realidade.",
            review_status=CurationState.REJECTED,
        )
        formulation = _get_or_create_entity(
            db,
            preferred_name="Formulação Fictícia de Demonstração F-1",
            entity_type=ScientificEntityType.FORMULATION,
            description="Formulação fictícia combinando materiais/fármacos sintéticos de demonstração.",
            review_status=CurationState.DRAFT,
        )
        nanomaterial = _get_or_create_entity(
            db,
            preferred_name="Nanopartícula Fictícia de Demonstração NP-1",
            entity_type=ScientificEntityType.NANOMATERIAL,
            description="Nanomaterial fictício de demonstração. Sem dado real.",
            review_status=CurationState.DRAFT,
        )

        # --- Identificador externo fictício (nunca um CID/ChEBI/CAS real) ------------------
        _ensure_identifier(
            db,
            entity=biomaterial,
            namespace="SYNTHETIC_DEMO_ID",
            identifier="SYNTH-BIOMAT-0001",
            verification_status=IdentifierVerificationStatus.UNVERIFIED,
        )

        # --- Observações conflitantes: mesma entidade+propriedade, duas fontes distintas,
        # valores DIFERENTES -- ambas devem coexistir (fingerprints diferentes). -------------
        _ensure_observation(
            db,
            entity=biomaterial,
            property_definition=young_modulus,
            source=source_alpha,
            value_numeric=12.3,
            unit_original="GPa",
            method="Ensaio de compressão fictício (fonte Alfa)",
            evidence_type=EvidenceType.EXPERIMENTAL,
            review_status=CurationState.REVIEWED,
            notes="Observação sintética de demonstração -- fonte Alfa.",
            reference=fictitious_reference,
        )
        _ensure_observation(
            db,
            entity=biomaterial,
            property_definition=young_modulus,
            source=source_beta,
            value_numeric=15.7,
            unit_original="GPa",
            method="Ensaio de compressão fictício (fonte Beta)",
            evidence_type=EvidenceType.EXPERIMENTAL,
            review_status=CurationState.DRAFT,
            notes=(
                "Observação sintética de demonstração -- fonte Beta. Valor DIVERGENTE da "
                "observação da fonte Alfa, mantido como linha separada por design (nunca "
                "sobrescrita silenciosa)."
            ),
        )
        # Uma terceira observação, agora declarada por FORNECEDOR (rotulada explicitamente) --
        # nunca confundida com valor experimental/calculado.
        supplier_declared_obs = _ensure_observation(
            db,
            entity=biomaterial,
            property_definition=young_modulus,
            source=None,
            value_numeric=13.9,
            unit_original="GPa",
            method="Valor declarado em ficha técnica fictícia de fornecedor",
            evidence_type=EvidenceType.SUPPLIER_DECLARED,
            review_status=CurationState.DRAFT,
            notes="Observação sintética declarada por fornecedor fictício -- não é medição independente.",
        )

        # --- Evidência biológica (classificação apenas de pesquisa) -------------------------
        existing_evidence = (
            db.query(BiologicalEvidence)
            .filter(BiologicalEvidence.entity_id == drug.id, BiologicalEvidence.assay_type == "ensaio_fictício_demo")
            .first()
        )
        if existing_evidence is None:
            db.add(
                BiologicalEvidence(
                    organization_id=None,
                    entity_id=drug.id,
                    assay_type="ensaio_fictício_demo",
                    biological_model="in_vitro_fictício",
                    species=None,
                    cell_line="Linhagem celular fictícia de demonstração",
                    organism=None,
                    endpoint="viabilidade_celular_fictícia",
                    result_value=72.5,
                    result_text="Resultado fictício de demonstração -- classificação apenas de pesquisa.",
                    dose_value=10.0,
                    dose_unit="ug_mL_fictício",
                    duration_value=24.0,
                    duration_unit="h",
                    conditions={"nota": "Dado inteiramente sintético, não é validação clínica."},
                    reference_id=fictitious_reference.id,
                    research_classification_only=True,
                )
            )

        # --- Fornecedor e produto comercial fictícios (nunca sinônimo da entidade canônica) -
        existing_supplier = (
            db.query(Supplier).filter(Supplier.name == "Fornecedor Fictício de Demonstração Ltda").first()
        )
        if existing_supplier is None:
            supplier = Supplier(
                name="Fornecedor Fictício de Demonstração Ltda",
                website_url=None,
                region="Região fictícia de demonstração",
            )
            db.add(supplier)
            db.flush()
        else:
            supplier = existing_supplier

        existing_product = (
            db.query(SupplierProduct)
            .filter(SupplierProduct.supplier_id == supplier.id, SupplierProduct.catalog_sku == "SYNTH-SKU-0001")
            .first()
        )
        if existing_product is None:
            db.add(
                SupplierProduct(
                    supplier_id=supplier.id,
                    entity_id=biomaterial.id,
                    catalog_sku="SYNTH-SKU-0001",
                    commercial_name="Hidroxiapatita Fictícia Grau-Demo",
                    url=None,
                    region="Região fictícia de demonstração",
                    lot_number="LOTE-FICTICIO-0001",
                    declared_properties={
                        "young_modulus_gpa_declarado_pelo_fornecedor": 13.9,
                        "observacao_relacionada_id": supplier_declared_obs.id,
                    },
                )
            )

        # --- Estrutura cristalográfica sintética (referência apenas, sem arquivo real) ------
        existing_crystal = (
            db.query(CrystalStructureReference)
            .filter(
                CrystalStructureReference.database_name == "SYNTHETIC_DEMO_CRYSTAL_DB",
                CrystalStructureReference.accession_id == "SYNTH-0001",
            )
            .first()
        )
        if existing_crystal is None:
            db.add(
                CrystalStructureReference(
                    entity_id=biomaterial.id,
                    database_name="SYNTHETIC_DEMO_CRYSTAL_DB",
                    accession_id="SYNTH-0001",
                    formula="Ca10(PO4)6(OH)2-fictício",
                    crystal_system="hexagonal_fictício",
                    space_group="P63/m-fictício",
                    cell_params={"a": 9.42, "b": 9.42, "c": 6.88, "nota": "Parâmetros fictícios de demonstração"},
                    url=None,
                    license="Uso interno de demonstração apenas.",
                )
            )

        # --- IngestionRun sintética (documenta o contrato, nenhum conector real existe) -----
        existing_run = (
            db.query(IngestionRun)
            .filter(IngestionRun.connector_name == "synthetic_demo_connector")
            .first()
        )
        if existing_run is None:
            now = datetime.now(timezone.utc)
            db.add(
                IngestionRun(
                    organization_id=None,
                    source_id=source_alpha.id,
                    connector_name="synthetic_demo_connector",
                    connector_version="0.0.0-demo",
                    started_at=now,
                    finished_at=now,
                    parameters={"nota": "Execução fictícia -- nenhum conector real implementado nesta rodada."},
                    received_count=1,
                    created_count=1,
                    updated_count=0,
                    skipped_count=0,
                    rejected_count=0,
                    status=IngestionStatus.SUCCEEDED,
                    errors=None,
                )
            )

        # --- Trilha de revisão (draft/reviewed/rejected já refletidos nas entidades acima;
        # aqui registramos as DECISÕES que levaram a esses estados, append-only) ------------
        def _ensure_review_decision(entity: ScientificEntity, decision: ReviewDecisionOutcome, justification: str) -> None:
            existing_decision = (
                db.query(ReviewDecision)
                .filter(ReviewDecision.subject_type == "ScientificEntity", ReviewDecision.subject_id == entity.id)
                .first()
            )
            if existing_decision is not None:
                return
            db.add(
                ReviewDecision(
                    organization_id=None,
                    subject_type="ScientificEntity",
                    subject_id=entity.id,
                    decision=decision,
                    reviewer_user_id=admin.id,
                    justification=justification,
                    previous_state=CurationState.DRAFT.value,
                    new_state=(
                        CurationState.REVIEWED.value
                        if decision == ReviewDecisionOutcome.APPROVED
                        else CurationState.REJECTED.value
                    ),
                )
            )

        _ensure_review_decision(
            biomaterial, ReviewDecisionOutcome.APPROVED, "Revisão sintética de demonstração: aprovada."
        )
        _ensure_review_decision(
            drug,
            ReviewDecisionOutcome.REJECTED,
            "Revisão sintética de demonstração: rejeitada (entidade inteiramente fictícia, propositalmente "
            "marcada como rejeitada para exercitar o estado no domínio).",
        )
        # chemical_substance, formulation e nanomaterial ficam propositalmente em DRAFT, sem
        # nenhuma ReviewDecision ainda -- exercitam o caso "aguardando revisão".
        del chemical_substance, formulation, nanomaterial

        db.commit()
        print(
            "Seed científico sintético aplicado: 5 entidades canônicas (biomaterial/substância/"
            "fármaco/formulação/nanomaterial), 3 observações conflitantes/rotuladas, 1 evidência "
            "biológica, 1 fornecedor+produto fictício, 1 referência cristalográfica sintética, "
            "1 execução de ingestão fictícia, estados draft/reviewed/rejected representados."
        )
    finally:
        db.close()


if __name__ == "__main__":
    run_seed_scientific_data()
