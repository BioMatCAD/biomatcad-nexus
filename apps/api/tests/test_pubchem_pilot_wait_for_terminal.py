"""Testes de scripts/pubchem_pilot_wait_for_terminal.py (Incremento 2.3, Rodada 2, Fase I --
correção do falso positivo confirmado na Run 2 do piloto PubChem Windows).

Causa real da Run 2: `Run-PubChemPilotWindows.ps1` chamava o dispatcher uma única vez
(`--once --limit 1`) e confiava apenas na CONTAGEM devolvida ("Processada(s) 1 solicitação(ões)")
-- nunca verificava se a solicitação ESPECÍFICA que o próprio roteiro tinha acabado de submeter
efetivamente saiu do estado `queued`. Como `claim_next_queued_request` reivindica sempre a
solicitação mais antiga da fila inteira (FIFO global -- correto para produção), qualquer
solicitação `queued` mais antiga e não relacionada, já existente no mesmo banco Postgres
persistente, era processada de verdade a cada chamada, enquanto a solicitação do piloto ficava
`queued` para sempre. Estes testes provam que `wait_for_request_terminal` resolve isso:
acompanhando o `request_id` exato, drenando a fila item a item até alcançá-lo, com timeout
explícito quando o processamento genuinamente nunca acontece.

Nenhuma rede real é usada -- mesmo padrão de `test_scientific_ingestion_service.py`
(`PubChemConnector` real com cliente HTTP fake injetado)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pubchem_pilot_validation as validation
import pubchem_pilot_wait_for_terminal as wft
from pubchem_pilot_wait_for_terminal import (
    RequestNotFoundError,
    RequestTerminalTimeoutError,
    wait_for_request_terminal,
)

from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.models.scientific_ingestion import IngestionRequestStatus
from biomatcad_api.services import scientific_ingestion_service as svc
from biomatcad_api.services.connectors.http_client import HttpFetchResult
from biomatcad_api.services.connectors.pubchem import PubChemConnector
from biomatcad_api.services.scientific_ingestion_service import submit_ingestion_request
from tests.factories import create_admin

# Poll/timeout minúsculos -- estes testes nunca dependem de tempo real de rede; existem apenas
# para provar o CONTRATO do polling (drena a fila, respeita timeout), então usam frações de
# segundo para permanecer rápidos mesmo quando o timeout É o cenário sob teste.
FAST_POLL_INTERVAL = 0.01
FAST_TIMEOUT = 0.2


def _cid_payload(cid: int, name: str = "Composto") -> dict:
    return {
        "PropertyTable": {
            "Properties": [
                {"CID": cid, "Title": name, "MolecularFormula": "C1H4", "MolecularWeight": "16.04"}
            ]
        }
    }


class _FakeMultiClient:
    def __init__(self, responses: dict[str, tuple[int, bytes]]):
        self.responses = responses

    def get(self, path: str) -> HttpFetchResult:
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


def _ok_response(cid: int) -> tuple[int, bytes]:
    return 200, json.dumps(_cid_payload(cid)).encode("utf-8")


def _make_source(db_session) -> ScientificSource:
    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_wait_for_request_terminal_raises_not_found_for_unknown_id(db_session):
    with pytest.raises(RequestNotFoundError):
        wait_for_request_terminal(
            db_session, request_id="does-not-exist",
            poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
        )


def test_wait_for_request_terminal_returns_immediately_when_already_terminal(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    _patch_connector(monkeypatch, _fake_connector({"2244": _ok_response(2244)}))
    claimed = svc.claim_next_queued_request(db_session, dispatcher_id="d1")
    svc.process_request(db_session, request=claimed)

    report = wait_for_request_terminal(
        db_session, request_id=request.id,
        poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
    )
    assert report["status"] == "succeeded"


def test_wait_for_request_terminal_drains_older_stale_request_first(db_session, monkeypatch):
    """Reproduz o cenário real da Run 2: uma solicitação MAIS ANTIGA e não relacionada já está
    'queued' no banco quando o piloto submete a sua. `wait_for_request_terminal` deve continuar
    drenando a fila (processando a antiga primeiro, exatamente como o dispatcher real faria)
    até que a solicitação que nos interessa também chegue a um estado terminal -- nunca parar
    cedo demais só porque 'alguma' solicitação foi processada."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    old_request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["1"],
    )
    our_request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    _patch_connector(monkeypatch, _fake_connector({"1": _ok_response(1), "2244": _ok_response(2244)}))

    report = wait_for_request_terminal(
        db_session, request_id=our_request.id,
        poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
    )
    assert report["request_id"] == our_request.id
    assert report["status"] == "succeeded"
    # Prova que a solicitação antiga TAMBÉM foi drenada (não ficou presa/ignorada) -- o
    # dispatcher real de produção teria feito exatamente isso.
    db_session.refresh(old_request)
    assert old_request.status == IngestionRequestStatus.SUCCEEDED


def test_wait_for_request_terminal_raises_timeout_when_never_processed(db_session, monkeypatch):
    """Se nada jamais reivindica a solicitação (nenhum worker rodando de verdade), o polling
    deve parar no timeout explícito -- nunca travar num loop sem limite."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    monkeypatch.setattr(wft, "claim_next_queued_request", lambda db, dispatcher_id: None)

    with pytest.raises(RequestTerminalTimeoutError) as exc_info:
        wait_for_request_terminal(
            db_session, request_id=request.id,
            poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
        )
    assert exc_info.value.last_report["status"] == "queued"
    assert exc_info.value.last_report["request_id"] == request.id


def test_wait_for_request_terminal_reaches_partial_when_one_cid_fails(db_session, monkeypatch):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "999999999"],
    )
    _patch_connector(
        monkeypatch, _fake_connector({"2244": _ok_response(2244), "999999999": (404, b"")})
    )
    report = wait_for_request_terminal(
        db_session, request_id=request.id,
        poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
    )
    assert report["status"] == "partial"
    result = validation.validate_real_report(report, ["2244", "999999999"])
    assert result.ok is False, "PARTIAL nunca deve ser aceito como sucesso terminal deste piloto"


def test_wait_for_request_terminal_full_success_and_no_duplication_on_second_round(db_session, monkeypatch):
    """Cobre, de ponta a ponta (submissão -> espera -> validação), os dois últimos cenários
    pedidos: 'sucesso real de todos os CIDs' e 'ausência de duplicação na segunda rodada'."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    cids = ["2244", "702", "5090"]
    responses = {"2244": _ok_response(2244), "702": _ok_response(702), "5090": _ok_response(5090)}
    _patch_connector(monkeypatch, _fake_connector(responses))

    request_1 = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=cids,
    )
    report_1 = wait_for_request_terminal(
        db_session, request_id=request_1.id,
        poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
    )
    assert validation.validate_real_report(report_1, cids).ok is True

    request_2 = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=cids,
    )
    report_2 = wait_for_request_terminal(
        db_session, request_id=request_2.id,
        poll_interval_seconds=FAST_POLL_INTERVAL, timeout_seconds=FAST_TIMEOUT,
    )
    assert validation.validate_real_report(report_2, cids).ok is True

    idempotency = validation.validate_idempotency(report_1, report_2, cids)
    assert idempotency.ok is True
    for detail in idempotency.details:
        assert detail["version_count_round1"] == 1
        assert detail["version_count_round2"] == 1
        assert detail["sha256_round1"] == detail["sha256_round2"]
