"""Testes de scripts/pubchem_pilot_validation.py (Incremento 2.3, Rodada 2, Fase I).

Reproduz literalmente a evidência real preservada de DUAS rodadas com veredito reprovado:

Run 2 (`INVALID_FALSE_POSITIVE`, relatório SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`): `dry_run_result` com
`ok=false, status=queued`; `real_result_1`/`real_result_2` com `status=queued,
started_at=null, finished_at=null, summary=null, error=null`, todos os CIDs com
`version_count=0, versions=[]`; e `idempotency_proof.extra` com os 3 CIDs (2244, 702, 5090)
todos `ok=false, sem RawSourceRecord` -- e prova que as novas funções de validação REJEITAM
tudo isso, ao contrário do `.ps1` antigo (que aceitava `status != "failed"` como sucesso, e cujo
loop de idempotência esquecia de propagar `ok=false` para o agregado).

Run 3 (`QUEUE_CONTAMINATION`, request_id `bb30bdf9-e78d-401f-8f56-c43b12231b60`, 2026-08-10, ver
docs/data/connectors/PUBCHEM_CONNECTOR.md): `validate_dry_run_report` exigia ZERO
RawSourceRecord ABSOLUTO por CID -- mas os 3 CIDs já tinham RawSourceRecords de uma solicitação
REAL não relacionada, drenada da fila enquanto o dry run aguardava (ver correção em
`scripts/pubchem_pilot_wait_for_terminal.py`). A nova validação usa BASELINE (capturado antes da
submissão) + DELTA, nunca contagem absoluta -- e reprova como `QUEUE_CONTAMINATION` (nunca
acusando o dry run) quando o delta não é vazio."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pubchem_pilot_validation import (
    validate_dry_run_report,
    validate_idempotency,
    validate_network_reachability,
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
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids={})
    assert result.ok is False
    assert result.reason_code == "invalid_status"
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
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids={})
    assert result.ok is True
    assert result.reason_code == "ok"


def test_validate_dry_run_report_accepts_preexisting_records_with_empty_delta():
    """Correção da Run 3 (item 7/11.2-3 da auditoria): um CID pode legitimamente já ter
    RawSourceRecord de uma solicitação REAL anterior -- isso NUNCA deve reprovar o dry run,
    desde que nenhum registro NOVO tenha aparecido durante a janela dele (delta vazio). Prova
    que a validação não exige mais zero absoluto."""
    records = [
        {"external_id": "2244", "version_count": 1, "versions": [dict(_version("preexisting-hash"), id="rec-preexisting")]},
        *_empty_raw_records(["702", "5090"]),
    ]
    report = {
        "status": "succeeded",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": records,
    }
    # Baseline capturado ANTES da submissão já mostrava o mesmo registro preexistente -- nenhum
    # delta real.
    baseline = {"2244": ["rec-preexisting"], "702": [], "5090": []}
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids=baseline)
    assert result.ok is True
    assert result.reason_code == "ok"


def test_validate_dry_run_report_rejects_new_record_delta_as_queue_contamination():
    """Reprodução direta da causa raiz da Run 3: um RawSourceRecord aparece no relatório final
    do dry run que NÃO existia no baseline capturado antes da submissão -- estruturalmente
    impossível de ter sido criado pelo próprio dry run. Deve reprovar como
    `queue_contamination`, NUNCA como 'dry run persistiu dados' (a antiga mensagem incorreta da
    Run 3)."""
    records = _empty_raw_records(EXPECTED_CIDS)
    records[0]["version_count"] = 1
    records[0]["versions"] = [dict(_version("abc123"), id="rec-new-during-window")]
    report = {
        "status": "succeeded",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": records,
    }
    # Baseline vazio -- este registro não existia antes da submissão.
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids={})
    assert result.ok is False
    assert result.reason_code == "queue_contamination"
    assert "CONTAMINAÇÃO" in result.reason
    assert "dry run" not in result.reason.split("CONTAMINAÇÃO")[0]  # nunca acusa o dry run


def test_validate_dry_run_report_rejects_concurrent_delta_not_attributable():
    """Delta concorrente não atribuível: o baseline mostra 1 versão preexistente, mas o
    relatório final mostra 2 -- uma NOVA apareceu durante a janela do dry run, vinda de algum
    lugar que não pode ser identificado (RawSourceRecord não tem coluna de proveniência por
    request_id). Deve reprovar como queue_contamination mesmo havendo registros preexistentes
    legítimos."""
    records = [
        {
            "external_id": "2244",
            "version_count": 2,
            "versions": [
                dict(_version("old-hash"), id="rec-preexisting"),
                dict(_version("new-hash-during-window"), id="rec-concurrent-new"),
            ],
        },
        *_empty_raw_records(["702", "5090"]),
    ]
    report = {
        "status": "succeeded",
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": records,
    }
    baseline = {"2244": ["rec-preexisting"], "702": [], "5090": []}
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids=baseline)
    assert result.ok is False
    assert result.reason_code == "queue_contamination"
    assert "rec-concurrent-new" in result.reason


def test_validate_dry_run_report_rejects_missing_started_at():
    report = {
        "status": "succeeded",
        "started_at": None,
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": []},
        "error": None,
        "raw_source_records": [],
    }
    result = validate_dry_run_report(report, [], baseline_record_ids={})
    assert result.ok is False
    assert result.reason_code == "missing_data"
    assert "started_at" in result.reason


def test_validate_dry_run_report_reproduces_literal_run3_evidence():
    """Reprodução literal da Run 3 (request_id bb30bdf9-e78d-401f-8f56-c43b12231b60): os 3 CIDs
    (2244/702/5090) aparecem no relatório final do dry run com exatamente 1 RawSourceRecord
    cada, todos criados DEPOIS que o baseline teria sido capturado (baseline vazio, pois nenhum
    dos 3 CIDs tinha RawSourceRecord antes desta execução do piloto começar). A validação deve
    reprovar como queue_contamination -- nunca aceitar como a Run 3 antiga aceitou
    (final_status=SUCCEEDED nunca chegou a acontecer aqui porque dry_run_result.ok já era false,
    mas com o motivo ERRADO: "dry run NUNCA deve persistir nada")."""
    report = {
        "status": "succeeded",
        "dry_run": True,
        "started_at": "2026-08-10T17:21:27.071686-03:00",
        "finished_at": "2026-08-10T17:21:31.593691-03:00",
        "summary": {
            "dry_run": True,
            "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS],
            "fetch_errors": [],
        },
        "error": None,
        "raw_source_records": [
            {
                "external_id": "2244",
                "version_count": 1,
                "versions": [dict(_version("fb87b0e0e81640520c73486b861e5d0a"), id="d9f48f36-e73b-4e29-95e4-6abb817407e2")],
            },
            {
                "external_id": "702",
                "version_count": 1,
                "versions": [dict(_version("35f7a7a17960241da394c3eb22b768db"), id="05689767-a5e1-4190-9b27-e763fd1064a3")],
            },
            {
                "external_id": "5090",
                "version_count": 1,
                "versions": [dict(_version("1a7de573afaa7c44acd1cf998a449b50"), id="b14eeebe-bca3-4e2e-8b53-66beb496adc3")],
            },
        ],
    }
    baseline = {"2244": [], "702": [], "5090": []}
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids=baseline)
    assert result.ok is False
    assert result.reason_code == "queue_contamination"


# --- validate_network_reachability -------------------------------------------------------------


def test_validate_network_reachability_accepts_succeeded_valid_response():
    report = {
        "status": "succeeded",
        "summary": {
            "fetch_errors": [],
            "results": [{"external_identifier": cid, "preferred_name": "X", "formula": "C1"} for cid in EXPECTED_CIDS],
        },
    }
    result = validate_network_reachability(report, EXPECTED_CIDS)
    assert result.ok is True


def test_validate_network_reachability_rejects_partial_status():
    """Corrige o defeito confirmado na Run 3 (item 9 da auditoria): o antigo passo aceitava
    qualquer status != "failed", incluindo "partial". Esta validação exige succeeded, literal."""
    report = {
        "status": "partial",
        "summary": {
            "fetch_errors": [],
            "results": [{"external_identifier": cid, "preferred_name": "X"} for cid in EXPECTED_CIDS],
        },
    }
    result = validate_network_reachability(report, EXPECTED_CIDS)
    assert result.ok is False
    assert result.reason_code == "invalid_status"


def test_validate_network_reachability_rejects_fetch_errors_present():
    report = {
        "status": "succeeded",
        "summary": {
            "fetch_errors": [{"external_identifier": "2244", "error": {"error_type": "network_error"}}],
            "results": [{"external_identifier": cid, "preferred_name": "X"} for cid in EXPECTED_CIDS],
        },
    }
    result = validate_network_reachability(report, EXPECTED_CIDS)
    assert result.ok is False
    assert result.reason_code == "fetch_errors_present"


def test_validate_network_reachability_rejects_response_without_name_or_formula():
    report = {
        "status": "succeeded",
        "summary": {
            "fetch_errors": [],
            "results": [
                {"external_identifier": "2244", "preferred_name": None, "formula": None},
                {"external_identifier": "702", "preferred_name": "Ethanol", "formula": "C2H6O"},
                {"external_identifier": "5090", "preferred_name": "Rofecoxib", "formula": "C17H14O4S"},
            ],
        },
    }
    result = validate_network_reachability(report, EXPECTED_CIDS)
    assert result.ok is False
    assert result.reason_code == "invalid_response"
    assert "2244" in result.reason


# --- rejeição de status não-terminal-de-sucesso (cancelled/queued/running) ---------------------


import pytest as _pytest


@_pytest.mark.parametrize("status", ["cancelled", "queued", "running", "partial", "failed"])
def test_validate_real_report_rejects_every_non_succeeded_status(status):
    report = _successful_real_report({"2244": "a" * 64})
    report["status"] = status
    result = validate_real_report(report, ["2244"])
    assert result.ok is False
    assert result.reason_code == "invalid_status"


@_pytest.mark.parametrize("status", ["cancelled", "queued", "running", "partial", "failed"])
def test_validate_dry_run_report_rejects_every_non_succeeded_status(status):
    report = {
        "status": status,
        "started_at": "2026-08-09T00:00:01+00:00",
        "finished_at": "2026-08-09T00:00:02+00:00",
        "summary": {"dry_run": True, "results": [{"external_identifier": cid} for cid in EXPECTED_CIDS]},
        "error": None,
        "raw_source_records": _empty_raw_records(EXPECTED_CIDS),
    }
    result = validate_dry_run_report(report, EXPECTED_CIDS, baseline_record_ids={})
    assert result.ok is False
    assert result.reason_code == "invalid_status"


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
