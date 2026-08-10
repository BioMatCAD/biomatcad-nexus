"""Testes de scripts/pubchem_pilot_capture_baseline.py (Incremento 2.3, Rodada 2, Fase I --
correção do `QUEUE_CONTAMINATION` confirmado na Run 3, ver
docs/data/connectors/PUBCHEM_CONNECTOR.md). `validate_dry_run_report` agora compara um
snapshot ANTES (capturado por este script) contra o estado final por CID, em vez de exigir
zero registros absolutos."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pubchem_pilot_capture_baseline import capture_raw_record_baseline

from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.models.scientific_ingestion import ParsingStatus, RawSourceRecord


def _make_source(db_session) -> ScientificSource:
    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.flush()
    return source


def _add_raw_record(db_session, *, source_id: str, connector_id: str, external_id: str) -> RawSourceRecord:
    record = RawSourceRecord(
        source_id=source_id, connector_id=connector_id, connector_version="0.1.0",
        external_record_id=external_id, requested_endpoint="/rest/pug/x", http_status=200,
        content_type="application/json", fetched_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        payload_json={"a": 1}, payload_sha256="a" * 64, payload_size_bytes=10,
        schema_mapping_version="v1", parsing_status=ParsingStatus.PARSED,
    )
    db_session.add(record)
    db_session.flush()
    return record


def test_capture_baseline_empty_when_no_prior_records(db_session):
    source = _make_source(db_session)
    baseline = capture_raw_record_baseline(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "702"]
    )
    assert baseline == {"2244": [], "702": []}


def test_capture_baseline_reflects_preexisting_records(db_session):
    source = _make_source(db_session)
    record = _add_raw_record(db_session, source_id=source.id, connector_id="pubchem_pug_rest", external_id="2244")
    baseline = capture_raw_record_baseline(
        db_session, connector_id="pubchem_pug_rest", source_id=source.id, external_ids=["2244", "702"]
    )
    assert baseline == {"2244": [record.id], "702": []}


def test_capture_baseline_scoped_by_connector_and_source(db_session):
    source_a = _make_source(db_session)
    source_b = ScientificSource(
        name="PubChem B", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source_b)
    db_session.flush()
    _add_raw_record(db_session, source_id=source_b.id, connector_id="pubchem_pug_rest", external_id="2244")

    baseline = capture_raw_record_baseline(
        db_session, connector_id="pubchem_pug_rest", source_id=source_a.id, external_ids=["2244"]
    )
    assert baseline == {"2244": []}
