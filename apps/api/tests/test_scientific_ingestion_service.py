"""Testes do orquestrador da fila de ingestão científica (Incremento 2.3, Rodada 2 -- Fase D,
com os 2 casos adicionados para a correção de dry_run que descarta falhas de busca -- ver
docstring de `process_request` em scientific_ingestion_service.py).

Nenhuma rede real é usada -- `get_connector` é substituído (monkeypatch) por um
`PubChemConnector` real com um cliente HTTP fake injetado (`_FakeMultiClient`), preservando a
lógica real de normalize/reconcile/persist/summarize (compartilhada, ver services/connectors/
base.py) mas sem nenhuma dependência de rede ou de dados congelados do PubChem."""
from __future__ import annotations

import json

import pytest

from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
    ScientificIngestionRequest,
)
from biomatcad_api.services import scientific_ingestion_service as svc
from biomatcad_api.services.connectors.http_client import HttpFetchResult
from biomatcad_api.services.connectors.pubchem import PubChemConnector
from biomatcad_api.services.scientific_ingestion_service import (
    IngestionRequestError,
    claim_next_queued_request,
    list_conflicts_for_request,
    process_request,
    recover_orphaned_requests,
    request_cancel,
    submit_ingestion_request,
)
from tests.factories import create_admin


def _cid_payload(cid: int, name: str = "Composto", inchikey: str | None = None) -> dict:
    props = {
        "CID": cid,
        "Title": name,
        "MolecularFormula": "C1H4",
        "MolecularWeight": "16.04",
    }
    if inchikey:
        props["InChIKey"] = inchikey
    return {"PropertyTable": {"Properties": [props]}}


class _FakeMultiClient:
    """Cliente HTTP fake capaz de responder de forma diferente por CID (path contém o CID) --
    permite montar cenários de lote (alguns CIDs OK, alguns falhando) sem nenhuma rede real."""

    def __init__(self, responses: dict[str, tuple[int, bytes]]):
        # responses: cid_str -> (status_code, body_bytes)
        self.responses = responses
        self.calls: list[str] = []

    def get(self, path: str) -> HttpFetchResult:
        self.calls.append(path)
        cid = path.split("/cid/", 1)[1].split("/", 1)[0]
        status_code, body = self.responses.get(cid, (404, b""))
        return HttpFetchResult(
            status_code=status_code, content_type="application/json", body_bytes=body,
            attempt_count=1, final_url_path=path,
        )


def _fake_connector(responses: dict[str, tuple[int, bytes]]) -> PubChemConnector:
    return PubChemConnector(client=_FakeMultiClient(responses))


def _patch_connector(monkeypatch, connector: PubChemConnector) -> None:
    monkeypatch.setattr(svc, "get_connector", lambda connector_id: connector)


def _make_source(db_session) -> ScientificSource:
    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


def _ok_response(cid: int, **kwargs) -> tuple[int, bytes]:
    return 200, json.dumps(_cid_payload(cid, **kwargs)).encode("utf-8")


# --- submit_ingestion_request --------------------------------------------------------------


def test_submit_ingestion_request_rejects_unknown_connector(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    with pytest.raises(IngestionRequestError) as exc_info:
        submit_ingestion_request(
            db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
            connector_id="chebi", source_id=source.id, external_ids=["100"],
        )
    assert exc_info.value.reason_code == "unknown_connector"


def test_submit_ingestion_request_rejects_invalid_external_ids(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    with pytest.raises(IngestionRequestError) as exc_info:
        submit_ingestion_request(
            db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
            connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["aspirin"],
        )
    assert exc_info.value.reason_code == "invalid_request"


def test_submit_ingestion_request_queues_valid_request(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "702"],
    )
    assert request.status == IngestionRequestStatus.QUEUED
    assert request.external_ids == ["2244", "702"]
    assert request.dry_run is False


def test_submit_ingestion_request_never_auto_starts(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    fetched = db_session.get(ScientificIngestionRequest, request.id)
    assert fetched.status == IngestionRequestStatus.QUEUED
    assert fetched.started_at is None


# --- claim_next_queued_request -------------------------------------------------------------


def test_claim_next_queued_request_returns_none_when_empty(db_session):
    assert claim_next_queued_request(db_session, dispatcher_id="d1") is None


def test_claim_next_queued_request_claims_oldest_first(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    first = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    assert claimed.id == first.id
    assert claimed.status == IngestionRequestStatus.RUNNING
    assert claimed.claimed_by_dispatcher_id == "d1"
    assert claimed.heartbeat_at is not None


def test_claim_next_queued_request_skips_already_running(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    claim_next_queued_request(db_session, dispatcher_id="d1")
    assert claim_next_queued_request(db_session, dispatcher_id="d2") is None


# --- recover_orphaned_requests --------------------------------------------------------------


def test_recover_orphaned_requests_requeues_stale_heartbeat(db_session):
    from datetime import timedelta

    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    claimed.heartbeat_at = svc._utcnow() - timedelta(seconds=svc.ORPHAN_HEARTBEAT_TIMEOUT_SECONDS + 5)
    db_session.commit()

    recovered_ids = recover_orphaned_requests(db_session)
    assert recovered_ids == [request.id]
    db_session.refresh(claimed)
    assert claimed.status == IngestionRequestStatus.QUEUED
    assert claimed.claimed_by_dispatcher_id is None
    assert claimed.attempt_number == 2


def test_recover_orphaned_requests_leaves_fresh_heartbeat_untouched(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    claim_next_queued_request(db_session, dispatcher_id="d1")
    assert recover_orphaned_requests(db_session) == []


# --- request_cancel ---------------------------------------------------------------------


def test_request_cancel_queued_cancels_immediately(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    cancelled = request_cancel(db_session, request=request, cancelled_by_user_id=admin.id)
    assert cancelled.status == IngestionRequestStatus.CANCELLED
    assert cancelled.finished_at is not None


def test_request_cancel_running_only_signals_does_not_change_status(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    result = request_cancel(db_session, request=claimed, cancelled_by_user_id=admin.id)
    assert result.status == IngestionRequestStatus.RUNNING
    assert result.cancel_requested_at is not None


def test_request_cancel_is_idempotent(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    first = request_cancel(db_session, request=request, cancelled_by_user_id=admin.id)
    second = request_cancel(db_session, request=first, cancelled_by_user_id=admin.id)
    assert second.status == IngestionRequestStatus.CANCELLED


def test_request_cancel_rejects_terminal_state(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, _fake_connector({"2244": _ok_response(2244)}))
    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.SUCCEEDED
    with pytest.raises(IngestionRequestError) as exc_info:
        request_cancel(db_session, request=finished, cancelled_by_user_id=admin.id)
    assert exc_info.value.reason_code == "invalid_transition"


# --- list_conflicts_for_request -----------------------------------------------------------


def test_list_conflicts_for_request_empty_when_no_conflicts(db_session):
    assert list_conflicts_for_request(db_session, request_id="does-not-exist") == []


# --- process_request: caminho real (persistência) ------------------------------------------


def test_process_request_rejects_non_running(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    with pytest.raises(IngestionRequestError) as exc_info:
        process_request(db_session, request=request)
    assert exc_info.value.reason_code == "invalid_transition"


def test_process_request_succeeds_and_persists_new_entity(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, _fake_connector({"2244": _ok_response(2244, name="Aspirin")}))

    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.SUCCEEDED
    assert finished.summary["received_count"] == 1
    assert finished.summary["created_count"] == 1
    assert finished.ingestion_run_id is not None


def test_process_request_idempotent_second_run_is_unchanged(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    connector = _fake_connector({"2244": _ok_response(2244, name="Aspirin")})

    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed_1 = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, connector)
    process_request(db_session, request=claimed_1)

    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed_2 = claim_next_queued_request(db_session, dispatcher_id="d1")
    finished_2 = process_request(db_session, request=claimed_2)

    assert finished_2.status == IngestionRequestStatus.SUCCEEDED
    assert finished_2.summary["created_count"] == 0
    assert finished_2.summary["skipped_count"] == 1


def test_process_request_never_promotes_to_reviewed(db_session, monkeypatch):
    from biomatcad_api.models.scientific_data import (
        CurationState,
        PropertyObservation,
        ScientificEntity,
    )

    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, _fake_connector({"2244": _ok_response(2244)}))
    process_request(db_session, request=claimed)

    entities = db_session.query(ScientificEntity).all()
    observations = db_session.query(PropertyObservation).all()
    assert entities and all(e.review_status == CurationState.DRAFT for e in entities)
    assert observations and all(o.review_status == CurationState.DRAFT for o in observations)


def test_process_request_partial_when_some_cids_fail(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "999999999"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(
        monkeypatch, _fake_connector({"2244": _ok_response(2244), "999999999": (404, b"")})
    )
    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.PARTIAL
    assert finished.error["rejected_external_ids"] == ["999999999"]


def test_process_request_failed_when_all_cids_fail(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["999999999"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, _fake_connector({"999999999": (404, b"")}))
    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.FAILED


def test_process_request_rejects_oversized_payload(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    huge_payload = _cid_payload(2244)
    huge_payload["PropertyTable"]["Properties"][0]["Title"] = "x" * (svc.MAX_PAYLOAD_BYTES + 1000)
    _patch_connector(
        monkeypatch, _fake_connector({"2244": (200, json.dumps(huge_payload).encode("utf-8"))})
    )
    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.FAILED
    assert "acima do limite" in finished.error["reasons"][0]


def test_process_request_records_conflict_never_auto_merges(db_session, monkeypatch):
    from biomatcad_api.models.scientific_data import (
        IdentifierVerificationStatus,
        ScientificEntity,
        ScientificEntityType,
        ScientificIdentifier,
    )
    from biomatcad_api.models.scientific_ingestion import IngestionConflictType

    admin = create_admin(db_session)
    source = _make_source(db_session)

    other_entity = ScientificEntity(
        organization_id=None, entity_type=ScientificEntityType.CHEMICAL_SUBSTANCE,
        preferred_name="Entidade pré-existente",
    )
    db_session.add(other_entity)
    db_session.flush()
    db_session.add(
        ScientificIdentifier(
            entity_id=other_entity.id, namespace="inchikey", identifier="ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
            identifier_normalized="ZZZZZZZZZZZZZZ-UHFFFAOYSA-N",
            verification_status=IdentifierVerificationStatus.VERIFIED,
        )
    )
    db_session.commit()

    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(
        monkeypatch,
        _fake_connector({"2244": _ok_response(2244, inchikey="ZZZZZZZZZZZZZZ-UHFFFAOYSA-N")}),
    )
    finished = process_request(db_session, request=claimed)
    assert finished.summary["conflicts_count"] == 1

    conflicts = list_conflicts_for_request(db_session, request_id=request.id)
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == IngestionConflictType.INCHIKEY_SHARED_WITH_OTHER_ENTITY
    assert conflicts[0].other_entity_id == other_entity.id


def test_process_request_cancellation_stops_before_next_cid(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "702"],
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    request_cancel(db_session, request=claimed, cancelled_by_user_id=admin.id)
    _patch_connector(
        monkeypatch, _fake_connector({"2244": _ok_response(2244), "702": _ok_response(702)})
    )
    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.CANCELLED


# --- process_request: dry_run (incluindo os 2 casos da correção de fetch-error) -------------


def test_process_request_dry_run_never_persists_anything(db_session, monkeypatch):
    from biomatcad_api.models.scientific_data import ScientificEntity

    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"], dry_run=True,
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    assert claimed.id == request.id
    _patch_connector(monkeypatch, _fake_connector({"2244": _ok_response(2244, name="Aspirin")}))

    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.SUCCEEDED
    assert finished.summary["dry_run"] is True
    assert finished.summary["results"][0]["would_create_new_entity"] is True
    assert db_session.query(ScientificEntity).count() == 0


def test_process_request_dry_run_reports_fetch_failures_never_silently_dropped(db_session, monkeypatch):
    """Regressão da Fase D/I: um dry_run cujo ÚNICO CID falha ao buscar (rede bloqueada, CID
    inexistente etc.) nunca pode parecer 'SUCCEEDED com zero resultados' -- deve reportar
    FAILED com o erro de busca explícito em `summary.fetch_errors`."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["999999999"], dry_run=True,
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, _fake_connector({"999999999": (404, b"")}))

    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.FAILED
    assert finished.summary["results"] == []
    assert len(finished.summary["fetch_errors"]) == 1
    assert finished.summary["fetch_errors"][0]["external_identifier"] == "999999999"
    assert finished.error["rejected_external_ids"] == ["999999999"]


def test_process_request_dry_run_partial_when_some_cids_fail_to_fetch(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id,
        external_ids=["2244", "999999999"], dry_run=True,
    )
    claimed = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(
        monkeypatch, _fake_connector({"2244": _ok_response(2244), "999999999": (404, b"")})
    )

    finished = process_request(db_session, request=claimed)
    assert finished.status == IngestionRequestStatus.PARTIAL
    assert len(finished.summary["results"]) == 1
    assert len(finished.summary["fetch_errors"]) == 1


def test_process_request_dry_run_detects_existing_entity(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    connector = _fake_connector({"2244": _ok_response(2244, name="Aspirin")})

    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    real_claim = claim_next_queued_request(db_session, dispatcher_id="d1")
    _patch_connector(monkeypatch, connector)
    process_request(db_session, request=real_claim)

    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"], dry_run=True,
    )
    dry_claim = claim_next_queued_request(db_session, dispatcher_id="d1")
    finished = process_request(db_session, request=dry_claim)
    assert finished.summary["results"][0]["would_create_new_entity"] is False
    assert finished.summary["results"][0]["existing_entity_id"] is not None
