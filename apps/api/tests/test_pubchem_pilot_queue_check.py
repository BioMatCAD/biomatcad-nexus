"""Testes de scripts/pubchem_pilot_queue_check.py (Incremento 2.3, Rodada 2, Fase I --
preflight anti-contaminação de fila, correção do `QUEUE_CONTAMINATION` confirmado na Run 3 do
piloto PubChem Windows, 2026-08-10, ver docs/data/connectors/PUBCHEM_CONNECTOR.md).

Regressão pedida explicitamente na auditoria da Run 3: "solicitação real antiga à frente do dry
run" -- antes de submeter qualquer coisa nova, o piloto deve detectar se já existe alguma
solicitação queued/running para o mesmo connector_id/source_id e recusar prosseguir."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pubchem_pilot_queue_check import find_contaminating_requests

from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.services.scientific_ingestion_service import (
    claim_next_queued_request,
    submit_ingestion_request,
)
from tests.factories import create_admin


def _make_source(db_session, name: str = "PubChem") -> ScientificSource:
    source = ScientificSource(
        name=name, source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_find_contaminating_requests_empty_queue_is_clean(db_session):
    source = _make_source(db_session)
    contaminating = find_contaminating_requests(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id
    )
    assert contaminating == []


def test_find_contaminating_requests_detects_old_real_request_ahead_of_dry_run(db_session):
    """Regressão direta da Run 3: uma solicitação REAL (dry_run=False) antiga e queued para o
    MESMO connector_id/source_id já existe -- deve ser detectada como contaminação antes de
    qualquer submissão nova."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    old_real_request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"], dry_run=False,
    )
    contaminating = find_contaminating_requests(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id
    )
    assert len(contaminating) == 1
    assert contaminating[0]["id"] == old_real_request.id
    assert contaminating[0]["status"] == "queued"
    assert contaminating[0]["dry_run"] is False


def test_find_contaminating_requests_detects_running_request_too(db_session):
    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    claim_next_queued_request(db_session, dispatcher_id="some-other-dispatcher")
    contaminating = find_contaminating_requests(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id
    )
    assert len(contaminating) == 1
    assert contaminating[0]["id"] == request.id
    assert contaminating[0]["status"] == "running"


def test_find_contaminating_requests_ignores_different_source_or_connector(db_session):
    admin = create_admin(db_session)
    source_a = _make_source(db_session, name="PubChem A")
    source_b = _make_source(db_session, name="PubChem B")
    submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source_b.id, external_ids=["2244"],
    )
    # Verificando contra source_a (diferente de onde a solicitação foi submetida) -- nunca deve
    # aparecer como contaminação, já que é um par connector/source diferente.
    contaminating = find_contaminating_requests(
        db_session, connector_id="pubchem_pug_rest", source_id=source_a.id
    )
    assert contaminating == []


def test_find_contaminating_requests_ignores_terminal_requests(db_session, monkeypatch):
    """Uma solicitação já em estado terminal (succeeded/failed/cancelled/partial) nunca é
    contaminação -- só queued/running representam risco de serem reivindicadas por engano."""
    from datetime import datetime, timezone

    from biomatcad_api.models.scientific_ingestion import IngestionRequestStatus

    admin = create_admin(db_session)
    source = _make_source(db_session)
    request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    request.status = IngestionRequestStatus.SUCCEEDED
    request.finished_at = datetime.now(timezone.utc)
    db_session.commit()

    contaminating = find_contaminating_requests(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id
    )
    assert contaminating == []


def test_find_contaminating_requests_excludes_given_request_ids(db_session):
    """`exclude_request_ids` permite ao próprio chamador ignorar solicitações que ele mesmo
    acabou de submeter intencionalmente -- nunca usado para esconder contaminação real de
    OUTRAS origens."""
    admin = create_admin(db_session)
    source = _make_source(db_session)
    own_request = submit_ingestion_request(
        db_session, organization_id=admin.organization_id, requested_by_user_id=admin.id,
        connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244"],
    )
    contaminating = find_contaminating_requests(
        db_session,
        connector_id="pubchem_pug_rest",
        source_id=source.id,
        exclude_request_ids=(own_request.id,),
    )
    assert contaminating == []
