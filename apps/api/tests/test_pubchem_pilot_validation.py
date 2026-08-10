"""Testes de scripts/pubchem_pilot_validation.py (Incremento 2.3, Rodada 2, Fase I -- correção
do falso positivo confirmado na Run 2 do piloto PubChem Windows,
`final_status=SUCCEEDED`/`exit code 0` apesar de `INVALID_FALSE_POSITIVE`).

Reproduz literalmente a evidência real preservada da Run 2 (relatório com SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`): `dry_run_result` com
`ok=false, status=queued`; `real_result_1`/`real_result_2` com `status=queued,
started_at=null, finished_at=null, summary=null, error=null`, todos os CIDs com
`version_count=0, versions=[]`; e `idempotency_proof.extra` com os 3 CIDs (2244, 702, 5090)
todos `ok=false, sem RawSourceRecord` -- e prova que as novas funções de validação REJEITAM
tudo isso, ao contrário do `.ps1` antigo (que aceitava `status != "failed"` como sucesso, e cujo
loop de idempotência esquecia de propagar `ok=false` para o agregado)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pubchem_pilot_validation import (
    validate_dry_run_report,
    validate_idempotency,
    validate_real_report,
)

EXPECTED_CIDS = ["2244", "702", "5090"]


def _empty_raw_records(cids: list[str]) -> list[dict]:
    return [{"external_id": cid, "version_count": 0, "versions": []} for cid in cids]


def _run2_real_report_literal(status: str = "queued") -> dict:
    """Reproduz literalmente a evidência real de `real_result_1`/`real_result_2` da Run 2."""
    return {
        "request_id": "req-run2",
        "status": status,
        "dry_run": False,
        "connector_id": "pubchem_pug_rest",
        "source_id": "src-1",
        "external_ids": EXPECTED_CIDS,
        "created_at": "2026-08-09T00:00:00+00:00",
        "started_at": None,
        "finished_at": None,
        "attempt_number": 1,
        "summary": None,
        "error": None,
        "raw_source_records": _empty_raw_records(EXPECTED_CIDS),
    }


def _version(sha256: str) -> dict:
    return {
        "id": "rec-1",
        "requested_endpoint": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/x",
        "http_status": 200,
        "content_type": "application/json",
        "fetched_at": "2026-08-09T00:00:00+00:00",
        "payload_sha256": sha256,
        "payload_size_bytes": 128,
        "parsing_status": "parsed",
        "predecessor_record_id": None,
        "created_at": "2026-08-09T00:00:00+00:00",
    }


def _successful_real_report(hashes: dict[str, str]) -> dict:
    return {
        "request_id": "req-ok",
        "status": "succeeded",
        "dry_run": False,
        "connector_id": "pubchem_pug_rest",
        "source_id": "src-1",
        "external_ids": list(hashes.keys()),
        "created_at": "2026-08-09T00:00:00+00:00",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "attempt_number": 1,
        "summary": {"received_count": len(hashes)},
        "error": None,
        "raw_source_records": [
            {"external_id": cid, "version_count": 1, "versions": [_version(sha)]}
            for cid, sha in hashes.items()
        ],
    }


# --- validate_dry_run_report -----------------------------------------------------------------


def test_validate_dry_run_report_rejects_run2_evidence_queued_status():
    report = {
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "summary": None,
        "error": None,
        "raw_source_records": _empty_raw_records(EXPECTED_CIDS),
    }
    result = validate_dry_run_report(report, EXPECTED_CIDS)
    assert result.ok is False
    assert "queued" in result.reason


def test_validate_dry_run_report_accepts_succeeded_with_no_persistence():
    report = {
        "status": "succeeded",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": _empty_raw_records(EXPECTED_CIDS),
    }
    result = validate_dry_run_report(report, EXPECTED_CIDS)
    assert result.ok is True


def test_validate_dry_run_report_rejects_if_any_cid_was_persisted():
    """Dry run nunca deve persistir nada -- se algum CID tiver version_count > 0, é um defeito
    real de produto (dry run vazando para persistência real), não um falso positivo do teste."""
    records = _empty_raw_records(EXPECTED_CIDS)
    records[0]["version_count"] = 1
    records[0]["versions"] = [_version("abc123")]
    report = {
        "status": "succeeded",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": records,
    }
    result = validate_dry_run_report(report, EXPECTED_CIDS)
    assert result.ok is False
    assert "NUNCA" in result.reason or "persistir" in result.reason


def test_validate_dry_run_report_rejects_missing_started_at():
    report = {
        "status": "succeeded",
        "started_at": None,
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": []},
        "error": None,
        "raw_source_records": [],
    }
    result = validate_dry_run_report(report, [])
    assert result.ok is False
    assert "started_at" in result.reason


# --- validate_real_report ----------------------------------------------------------------------


def test_validate_real_report_rejects_run2_evidence_literally():
    """Reprodução exata da Run 2: status=queued, started_at/finished_at nulos, todos os CIDs
    com version_count=0 -- o `.ps1` antigo aceitava isso como ok=true (`status != "failed"`).
    A nova validação deve rejeitar."""
    report = _run2_real_report_literal(status="queued")
    result = validate_real_report(report, EXPECTED_CIDS)
    assert result.ok is False
    assert "queued" in result.reason


def test_validate_real_report_accepts_succeeded_with_complete_records():
    report = _successful_real_report({"2244": "a" * 64, "702": "b" * 64, "5090": "c" * 64})
    result = validate_real_report(report, EXPECTED_CIDS)
    assert result.ok is True


def test_validate_real_report_rejects_when_error_present():
    report = _successful_real_report({"2244": "a" * 64})
    report["error"] = {"rejected_external_ids": ["2244"]}
    result = validate_real_report(report, ["2244"])
    assert result.ok is False
    assert "error" in result.reason


def test_validate_real_report_rejects_missing_record_for_expected_cid():
    report = _successful_real_report({"2244": "a" * 64})
    result = validate_real_report(report, ["2244", "999999999"])
    assert result.ok is False
    assert "999999999" in result.reason


def test_validate_real_report_rejects_empty_sha256():
    report = _successful_real_report({"2244": "a" * 64})
    report["raw_source_records"][0]["versions"][0]["payload_sha256"] = ""
    result = validate_real_report(report, ["2244"])
    assert result.ok is False
    assert "SHA-256" in result.reason


def test_validate_real_report_rejects_partial_status():
    """Com apenas os 3 CIDs conhecidos-bons deste piloto, PARTIAL indica um problema real --
    nunca aceito como sucesso terminal para a checagem de execução real."""
    report = _successful_real_report({"2244": "a" * 64})
    report["status"] = "partial"
    result = validate_real_report(report, ["2244"])
    assert result.ok is False


# --- validate_idempotency ----------------------------------------------------------------------


def test_validate_idempotency_rejects_run2_evidence_all_items_false():
    """Reprodução exata de idempotency_proof.extra da Run 2: os 3 CIDs (2244, 702, 5090) todos
    sem RawSourceRecord em nenhuma das duas rodadas. O `.ps1` antigo reportava
    `idempotency_proof.ok=true` apesar disso (bug: esquecia de propagar ok=false para o
    agregado). A nova validação deve rejeitar, e cada item de `.details` deve ser ok=false."""
    report1 = _run2_real_report_literal(status="queued")
    report2 = _run2_real_report_literal(status="queued")
    result = validate_idempotency(report1, report2, EXPECTED_CIDS)
    assert result.ok is False
    assert len(result.details) == 3
    assert all(d["ok"] is False for d in result.details)
    assert {d["cid"] for d in result.details} == set(EXPECTED_CIDS)


def test_validate_idempotency_accepts_when_all_cids_match():
    report1 = _successful_real_report({"2244": "a" * 64, "702": "b" * 64, "5090": "c" * 64})
    report2 = _successful_real_report({"2244": "a" * 64, "702": "b" * 64, "5090": "c" * 64})
    result = validate_idempotency(report1, report2, EXPECTED_CIDS)
    assert result.ok is True
    assert all(d["ok"] is True for d in result.details)


def test_validate_idempotency_rejects_empty_expected_cids():
    """Requisito literal: lista vazia deve reprovar, nunca ser aprovada vacuamente."""
    report1 = _successful_real_report({})
    report2 = _successful_real_report({})
    result = validate_idempotency(report1, report2, [])
    assert result.ok is False
    assert result.details == []


def test_validate_idempotency_rejects_single_false_item_among_true_ones():
    """Qualquer item falso reprova o agregado -- mesmo que os outros dois estejam corretos."""
    report1 = _successful_real_report({"2244": "a" * 64, "702": "b" * 64, "5090": "c" * 64})
    report2 = _successful_real_report({"2244": "a" * 64, "702": "b" * 64, "5090": "c" * 64})
    # CID 702 nunca foi persistido na segunda rodada.
    report2["raw_source_records"] = [
        rec for rec in report2["raw_source_records"] if rec["external_id"] != "702"
    ]
    result = validate_idempotency(report1, report2, EXPECTED_CIDS)
    assert result.ok is False
    by_cid = {d["cid"]: d["ok"] for d in result.details}
    assert by_cid["2244"] is True
    assert by_cid["5090"] is True
    assert by_cid["702"] is False


def test_validate_idempotency_rejects_hash_divergence():
    report1 = _successful_real_report({"2244": "a" * 64})
    report2 = _successful_real_report({"2244": "DIFFERENT" + "b" * 55})
    result = validate_idempotency(report1, report2, ["2244"])
    assert result.ok is False
    assert result.details[0]["ok"] is False


def test_validate_idempotency_rejects_new_version_created_in_round_2():
    report1 = _successful_real_report({"2244": "a" * 64})
    report2 = _successful_real_report({"2244": "a" * 64})
    report2["raw_source_records"][0]["version_count"] = 2
    report2["raw_source_records"][0]["versions"].append(_version("a" * 64))
    result = validate_idempotency(report1, report2, ["2244"])
    assert result.ok is False
    assert "nova versão" in result.details[0]["reason"]
