"""Testes do conector PubChem PUG REST (Incremento 2.3, Rodada 2 -- Fases E, F, G, J).

Nenhum destes testes toca a rede -- `PubChemConnector.fetch()` é exercitado com um
`AllowlistedHttpsClient` fake (monkeypatch em `get`) que devolve payloads `synthetic_contract_fixture`
(ver REGRAS ADICIONAIS regra 2): imitam o FORMATO documentado do PubChem PUG REST, mas nunca
foram capturados de uma resposta real (a rede pubchem.ncbi.nlm.nih.gov está bloqueada neste
sandbox -- ver docs/data/connectors/PUBCHEM_CONNECTOR.md). A única fonte de verdade sobre
comportamento real de rede é o roteiro scripts/Run-PubChemPilotWindows.ps1, rodando no Windows
do usuário, fora deste sandbox.
"""
from __future__ import annotations

import json

import pytest

from biomatcad_api.models.scientific_data import (
    CurationState,
    EvidenceType,
    ScientificEntity,
    ScientificIdentifier,
)
from biomatcad_api.models.scientific_ingestion import ParsingStatus
from biomatcad_api.services.connectors.http_client import HttpFetchResult
from biomatcad_api.services.connectors.pubchem import REQUESTED_PROPERTY_FIELDS, PubChemConnector
from biomatcad_api.services.connectors.registry import get_connector, list_connectors


def _aspirin_payload() -> dict:
    # synthetic_contract_fixture: NUNCA capturado de uma resposta real do PubChem nesta sessão
    # (a rede pubchem.ncbi.nlm.nih.gov está bloqueada neste sandbox -- ver REGRAS ADICIONAIS
    # regra 1/2 e docs/data/connectors/PUBCHEM_CONNECTOR.md). Esta é uma fixture SINTÉTICA que
    # imita o FORMATO documentado da resposta PUG REST (chaves/estrutura do PropertyTable);
    # os valores numéricos/estruturais (peso molecular, SMILES, InChI/InChIKey da aspirina) são
    # fatos químicos publicamente conhecidos e verificáveis, usados apenas como conteúdo
    # plausível de teste -- NUNCA atribuir este payload ao PubChem como se fosse uma resposta
    # oficial real capturada; apenas o roteiro Windows (Run-PubChemPilotWindows.ps1), rodando
    # fora deste sandbox, pode produzir/preservar uma resposta oficial real verificável.
    return {
        "PropertyTable": {
            "Properties": [
                {
                    "CID": 2244,
                    "Title": "Aspirin",
                    "IUPACName": "2-acetyloxybenzoic acid",
                    "MolecularFormula": "C9H8O4",
                    "MolecularWeight": "180.16",
                    # ConnectivitySMILES/SMILES sao os nomes ATUAIS do PUG REST (substituem os
                    # depreciados CanonicalSMILES/IsomericSMILES -- ver correcao da Run 3 do
                    # piloto Windows, 2026-08-10, docs/data/connectors/PUBCHEM_CONNECTOR.md).
                    "ConnectivitySMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "SMILES": "CC(=O)OC1=CC=CC=C1C(=O)O",
                    "InChI": "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)",
                    "InChIKey": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
                    "XLogP": "1.2",
                    "TPSA": "63.6",
                    "HBondDonorCount": 1,
                    "HBondAcceptorCount": 4,
                    "RotatableBondCount": 2,
                    "Charge": 0,
                    "Complexity": "212",
                }
            ]
        }
    }


class _FakeClient:
    """Substitui `AllowlistedHttpsClient` nos testes -- devolve respostas fixas sem rede."""

    def __init__(self, status_code: int, body: bytes, content_type: str = "application/json"):
        self.status_code = status_code
        self.body = body
        self.content_type = content_type
        self.calls: list[str] = []

    def get(self, path: str) -> HttpFetchResult:
        self.calls.append(path)
        return HttpFetchResult(
            status_code=self.status_code,
            content_type=self.content_type,
            body_bytes=self.body,
            attempt_count=1,
            final_url_path=path,
        )


# --- validate_request ------------------------------------------------------------------------


def test_validate_request_rejects_empty_list():
    connector = PubChemConnector(client=_FakeClient(200, b"{}"))
    errors = connector.validate_request([])
    assert errors and "vazia" in errors[0]


def test_validate_request_rejects_too_many_cids(monkeypatch):
    connector = PubChemConnector(client=_FakeClient(200, b"{}"))
    errors = connector.validate_request([str(i) for i in range(1, 40)])
    assert any("acima do limite" in e for e in errors)


def test_validate_request_rejects_non_numeric_cid():
    connector = PubChemConnector(client=_FakeClient(200, b"{}"))
    errors = connector.validate_request(["aspirin", "-5", "2244"])
    assert any("aspirin" in e for e in errors)
    assert any("-5" in e for e in errors)


def test_validate_request_accepts_valid_cids():
    connector = PubChemConnector(client=_FakeClient(200, b"{}"))
    assert connector.validate_request(["2244", "702"]) == []


# --- fetch / normalize: caminho feliz -----------------------------------------------------


def test_fetch_and_normalize_valid_response():
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)

    fetch_result = connector.fetch("2244")
    assert fetch_result.parsing_status == ParsingStatus.PARSED
    assert fetch_result.http_status == 200
    expected_path = f"/rest/pug/compound/cid/2244/property/{','.join(REQUESTED_PROPERTY_FIELDS)}/JSON"
    assert client.calls == [expected_path]

    normalized = connector.normalize(fetch_result)
    assert normalized.external_identifier == "2244"
    assert normalized.preferred_name == "Aspirin"
    assert normalized.iupac_name == "2-acetyloxybenzoic acid"
    assert normalized.formula == "C9H8O4"
    assert normalized.inchikey == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert normalized.canonical_smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
    assert normalized.missing_fields == []
    assert normalized.mapping_warnings == []
    property_keys = {p.property_key for p in normalized.calculated_properties}
    assert property_keys == {
        "molecular_weight", "xlogp", "tpsa", "hbond_donor_count", "hbond_acceptor_count",
        "rotatable_bond_count", "formal_charge", "complexity",
    }
    assert all(p.evidence_type == EvidenceType.CALCULATED for p in normalized.calculated_properties)
    mw = next(p for p in normalized.calculated_properties if p.property_key == "molecular_weight")
    assert mw.value_numeric == pytest.approx(180.16)
    assert mw.unit == "g/mol"


def test_requested_property_fields_use_current_not_deprecated_smiles_names():
    """Regressão da Run 3 do piloto Windows (2026-08-10, QUEUE_CONTAMINATION -- ver
    docs/data/connectors/PUBCHEM_CONNECTOR.md): o conector pedia os nomes de campo DEPRECIADOS
    `CanonicalSMILES`/`IsomericSMILES`; a resposta real do PubChem (durante a Run 3) não incluía
    mais essas chaves, fazendo ambas aparecerem em `missing_fields` para os 3 CIDs testados,
    sempre -- nunca um problema pontual de composto. Este teste prova que o endpoint agora
    solicita os nomes ATUAIS (`ConnectivitySMILES`/`SMILES`, que substituem os depreciados,
    confirmado via documentação oficial do PubChemPy que reflete o mapeamento do PUG REST)."""
    assert "ConnectivitySMILES" in REQUESTED_PROPERTY_FIELDS
    assert "SMILES" in REQUESTED_PROPERTY_FIELDS
    assert "CanonicalSMILES" not in REQUESTED_PROPERTY_FIELDS
    assert "IsomericSMILES" not in REQUESTED_PROPERTY_FIELDS


def test_normalize_maps_current_smiles_field_names_without_missing_fields():
    """Complementa o teste acima: com uma resposta que usa os nomes ATUAIS (o formato real
    esperado do PubChem hoje), `canonical_smiles`/`isomeric_smiles` devem ser preenchidos e
    NUNCA aparecer em `missing_fields` -- reproduzindo o que a Run 4 deve observar na prática,
    ao contrário da Run 3 (que usava os nomes depreciados e via ambos sempre ausentes)."""
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    assert normalized.canonical_smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
    assert normalized.isomeric_smiles == "CC(=O)OC1=CC=CC=C1C(=O)O"
    assert "ConnectivitySMILES" not in normalized.missing_fields
    assert "SMILES" not in normalized.missing_fields


def test_normalize_flags_deprecated_smiles_field_names_as_missing():
    """Reprodução literal da causa raiz da Run 3: uma resposta que só contém os nomes
    DEPRECIADOS (`CanonicalSMILES`/`IsomericSMILES`, sem os atuais) faz o conector reportar
    `ConnectivitySMILES`/`SMILES` como `missing_fields` -- exatamente o sintoma observado nos 3
    CIDs da Run 3 (2244/702/5090), todos com `missing_fields: ["CanonicalSMILES",
    "IsomericSMILES"]` no relatório real. Prova que o comportamento é determinístico e
    explicado pela mudança de nome de campo, não um defeito aleatório da rede."""
    payload = _aspirin_payload()
    props = payload["PropertyTable"]["Properties"][0]
    del props["ConnectivitySMILES"]
    del props["SMILES"]
    props["CanonicalSMILES"] = "CC(=O)OC1=CC=CC=C1C(=O)O"
    props["IsomericSMILES"] = "CC(=O)OC1=CC=CC=C1C(=O)O"
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    assert "ConnectivitySMILES" in normalized.missing_fields
    assert "SMILES" in normalized.missing_fields
    assert normalized.canonical_smiles is None
    assert normalized.isomeric_smiles is None


def test_normalize_records_missing_fields_without_inventing_values():
    payload = {
        "PropertyTable": {
            "Properties": [
                {"CID": 5, "Title": "Composto parcial", "MolecularFormula": "C1H4"}
            ]
        }
    }
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("5")
    normalized = connector.normalize(fetch_result)

    assert "InChIKey" in normalized.missing_fields
    assert "MolecularWeight" in normalized.missing_fields
    assert normalized.inchikey is None
    assert normalized.calculated_properties == []


def test_normalize_flags_non_numeric_value_as_warning_not_invented():
    payload = _aspirin_payload()
    payload["PropertyTable"]["Properties"][0]["MolecularWeight"] = "não disponível"
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    assert not any(p.property_key == "molecular_weight" for p in normalized.calculated_properties)
    assert any("não numérico" in w for w in normalized.mapping_warnings)


# --- fetch: erros estruturados -----------------------------------------------------------


def test_fetch_cid_not_found_404():
    connector = PubChemConnector(client=_FakeClient(404, b""))
    result = connector.fetch("999999999")
    assert result.parsing_status == ParsingStatus.FAILED
    assert result.parsing_error["error_type"] == "cid_not_found"
    assert result.payload_json is None


def test_fetch_bad_request_400():
    connector = PubChemConnector(client=_FakeClient(400, b""))
    result = connector.fetch("2244")
    assert result.parsing_status == ParsingStatus.FAILED
    assert result.parsing_error["error_type"] == "bad_request"


def test_fetch_invalid_json():
    connector = PubChemConnector(client=_FakeClient(200, b"{not valid json"))
    result = connector.fetch("2244")
    assert result.parsing_status == ParsingStatus.FAILED
    assert result.parsing_error["error_type"] == "invalid_json"


def test_fetch_rejects_cid_mismatch():
    payload = _aspirin_payload()  # CID 2244 dentro do payload
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    result = connector.fetch("9999")  # solicitamos um CID diferente do retornado
    assert result.parsing_status == ParsingStatus.FAILED
    assert result.parsing_error["error_type"] == "cid_mismatch"


def test_fetch_empty_property_table():
    payload = {"PropertyTable": {"Properties": []}}
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    result = connector.fetch("2244")
    assert result.parsing_status == ParsingStatus.PARTIAL
    assert result.parsing_error["error_type"] == "empty_property_table"


def test_fetch_unexpected_status():
    connector = PubChemConnector(client=_FakeClient(418, b""))
    result = connector.fetch("2244")
    assert result.parsing_status == ParsingStatus.FAILED
    assert result.parsing_error["error_type"] == "unexpected_status"


def test_normalize_on_failed_fetch_never_crashes_and_reports_all_missing():
    connector = PubChemConnector(client=_FakeClient(404, b""))
    fetch_result = connector.fetch("999999999")
    normalized = connector.normalize(fetch_result)
    assert normalized.missing_fields  # tudo ausente
    assert normalized.mapping_warnings


# --- reconcile / persist (contra Postgres real via db_session) ---------------------------


def _make_source(db_session):
    from biomatcad_api.models.scientific_data import (
        RedistributionStatus,
        ScientificSource,
        SourceType,
    )

    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_reconcile_creates_new_entity_as_draft_unreviewed(db_session):
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    outcome = connector.reconcile(db_session, normalized)
    assert outcome.entity_is_new is True
    assert outcome.entity.review_status == CurationState.DRAFT
    assert outcome.conflicts == []

    identifier = (
        db_session.query(ScientificIdentifier)
        .filter(ScientificIdentifier.namespace == "pubchem_cid", ScientificIdentifier.identifier == "2244")
        .first()
    )
    assert identifier is not None
    assert identifier.entity_id == outcome.entity.id


def test_reconcile_same_cid_twice_reuses_entity_not_duplicated(db_session):
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    first = connector.reconcile(db_session, normalized)
    second = connector.reconcile(db_session, normalized)

    assert first.entity.id == second.entity.id
    assert second.entity_is_new is False
    count = db_session.query(ScientificEntity).filter(ScientificEntity.id == first.entity.id).count()
    assert count == 1


def test_reconcile_flags_inchikey_collision_with_other_entity_never_auto_merges(db_session):
    from biomatcad_api.models.scientific_data import (
        IdentifierVerificationStatus,
        ScientificEntityType,
    )

    other_entity = ScientificEntity(
        organization_id=None,
        entity_type=ScientificEntityType.CHEMICAL_SUBSTANCE,
        preferred_name="Outra entidade pré-existente",
    )
    db_session.add(other_entity)
    db_session.flush()

    db_session.add(
        ScientificIdentifier(
            entity_id=other_entity.id,
            namespace="inchikey",
            identifier="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            identifier_normalized="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            verification_status=IdentifierVerificationStatus.VERIFIED,
        )
    )
    db_session.flush()

    payload = _aspirin_payload()  # mesmo InChIKey, CID diferente/novo -> entidade nova + colisão
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)

    outcome = connector.reconcile(db_session, normalized)
    assert outcome.entity.id != other_entity.id
    assert len(outcome.conflicts) == 1
    assert outcome.conflicts[0].other_entity_id == other_entity.id


def test_persist_never_overwrites_reviewed_observation(db_session):
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    source = _make_source(db_session)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)
    outcome = connector.reconcile(db_session, normalized)

    persist_outcome = connector.persist(
        db_session, normalized=normalized, fetch_result=fetch_result, source_id=source.id,
        raw_source_record=None, reconcile_outcome=outcome,
    )
    assert persist_outcome.created_observations == len(normalized.calculated_properties)

    from biomatcad_api.models.scientific_data import PropertyObservation

    obs = (
        db_session.query(PropertyObservation)
        .filter(PropertyObservation.entity_id == outcome.entity.id)
        .first()
    )
    obs.review_status = CurationState.REVIEWED
    db_session.flush()

    # Reimportar o mesmo payload: fingerprint idêntico -> unchanged, nunca sobrescreve a linha
    # já revisada (persist só ADICIONA linhas, nunca modifica uma existente).
    outcome_2 = connector.reconcile(db_session, normalized)
    persist_outcome_2 = connector.persist(
        db_session, normalized=normalized, fetch_result=fetch_result, source_id=source.id,
        raw_source_record=None, reconcile_outcome=outcome_2,
    )
    assert persist_outcome_2.unchanged is True
    db_session.refresh(obs)
    assert obs.review_status == CurationState.REVIEWED


def test_summarize_counts_created_updated_skipped(db_session):
    payload = _aspirin_payload()
    client = _FakeClient(200, json.dumps(payload).encode("utf-8"))
    connector = PubChemConnector(client=client)
    source = _make_source(db_session)
    fetch_result = connector.fetch("2244")
    normalized = connector.normalize(fetch_result)
    outcome = connector.reconcile(db_session, normalized)
    persist_outcome = connector.persist(
        db_session, normalized=normalized, fetch_result=fetch_result, source_id=source.id,
        raw_source_record=None, reconcile_outcome=outcome,
    )
    summary = connector.summarize([persist_outcome])
    assert summary["received_count"] == 1
    assert summary["created_count"] == 1
    assert summary["skipped_count"] == 0
    assert summary["rejected_count"] == 0


# --- registry ---------------------------------------------------------------------------


def test_registry_resolves_pubchem_connector():
    connector = get_connector("pubchem_pug_rest")
    assert isinstance(connector, PubChemConnector)
    assert connector.connector_id == "pubchem_pug_rest"


def test_registry_lists_planned_connectors_as_not_implemented():
    infos = list_connectors()
    ids = {info.connector_id: info for info in infos}
    assert ids["pubchem_pug_rest"].status == "implemented"
    assert ids["chebi"].status == "planned"
