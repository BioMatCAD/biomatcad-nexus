#!/usr/bin/env python3
"""Validação explícita e testável dos relatórios do piloto PubChem Windows.

Histórico de duas correções nesta camada de validação:

Run 2 (`INVALID_FALSE_POSITIVE`, relatório SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`): os passos
`real_result_1`/`real_result_2` do antigo `.ps1` aceitavam qualquer status DIFERENTE do literal
`"failed"` como sucesso (`-Ok ($report.status -ne "failed")`) -- `"queued"` também passava nesse
teste. Separadamente, `idempotency_proof` esquecia de propagar o agregado `$idempotencyOk =
$false` quando um item individual falhava. Corrigido nesta rodada com `validate_real_report` e
`validate_idempotency` (ver histórico completo nas docstrings de cada função).

Run 3 (`QUEUE_CONTAMINATION`, relatório com request_id `bb30bdf9-e78d-401f-8f56-c43b12231b60`,
2026-08-10, ver docs/data/connectors/PUBCHEM_CONNECTOR.md): `validate_dry_run_report` exigia
ZERO `RawSourceRecord` ABSOLUTO por CID esperado no relatório final do dry run. Isso é uma
premissa errada -- `RawSourceRecord`s de uma solicitação REAL anterior e legítima para o MESMO
CID são normais em produção (o mesmo composto pode já ter sido importado antes). O que
realmente aconteceu na Run 3: uma solicitação REAL antiga (não relacionada, sobrevivente de uma
execução anterior) foi reivindicada e processada por `pubchem_pilot_wait_for_terminal.py`
enquanto este esperava o dry run terminar -- ver correção em
`scripts/pubchem_pilot_wait_for_terminal.py`/`claim_specific_request` -- criando
`RawSourceRecord`s reais para os 3 CIDs, TODOS com `created_at` anterior ao `started_at` do
próprio dry run (prova temporal de que não podem ter sido criados por ele; prova de código
adicional: o ramo `dry_run` de `process_request()` nunca chama `_persist_raw_source_record`, ou
seja, é estruturalmente impossível um dry run persistir qualquer coisa). `validate_dry_run_report`
foi reescrita para comparar um BASELINE (capturado ANTES da submissão, via
`pubchem_pilot_capture_baseline.py`) contra o estado final por CID, e exigir ausência de
qualquer DELTA (nenhuma versão nova) -- nunca mais uma contagem absoluta. Se houver delta, a
causa nunca pode ser atribuída ao dry run (estruturalmente impossível) nem a um request_id
específico (o schema de `RawSourceRecord` não tem nenhuma coluna de proveniência por
solicitação -- é um registro deliberadamente compartilhável entre solicitações que buscam o
mesmo CID) -- por isso o veredito correto é sempre `QUEUE_CONTAMINATION`, nunca uma acusação ao
dry run."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

#: Único estado aceito para uma solicitação REAL ou dry run (persistente) do piloto: com apenas
#: os 3 CIDs sintéticos conhecidos e bem formados (aspirina/etanol/ibuprofeno), qualquer coisa
#: diferente de SUCCEEDED (PARTIAL, FAILED, CANCELLED, ou -- o defeito da Run 2 -- QUEUED/RUNNING)
#: indica um problema real que este piloto controlado deve expor, nunca mascarar.
_REQUIRED_TERMINAL_STATUS = "succeeded"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str
    #: Código curto e estável, pensado para asserções de teste e para o `.ps1` decidir o
    #: `final_status` correto sem precisar fazer parsing de texto livre. Valores possíveis:
    #: "ok", "invalid_status", "missing_data", "queue_contamination", "invalid_response",
    #: "fetch_errors_present".
    reason_code: str = "ok"


@dataclass(frozen=True)
class IdempotencyResult:
    ok: bool
    details: list[dict] = field(default_factory=list)


def _raw_records_by_external_id(report: dict) -> dict[str, dict]:
    return {rec["external_id"]: rec for rec in report.get("raw_source_records", [])}


def validate_dry_run_report(
    report: dict,
    expected_external_ids: Sequence[str],
    baseline_record_ids: Mapping[str, Sequence[str]],
) -> ValidationResult:
    """Requisito 6 (Run 2) + correção da Run 3 (`QUEUE_CONTAMINATION`): estado terminal de
    sucesso; started_at/finished_at preenchidos; summary/diff coerente; e -- em vez de exigir
    ZERO RawSourceRecord absoluto -- exige que o conjunto de IDs de RawSourceRecord por CID seja
    IDÊNTICO ao capturado em `baseline_record_ids` (nenhum ID novo apareceu durante a janela do
    dry run). `baseline_record_ids` é OBRIGATÓRIO -- sem ele, não há como distinguir "sempre
    esteve vazio" de "já tinha registros de antes"; um baseline vazio (`{}` ou listas vazias) é
    um valor legítimo (fila/CID nunca importado antes), não um valor ausente.

    Se algum CID esperado não tiver entrada em `baseline_record_ids` (nunca deveria acontecer se
    o chamador capturou o baseline corretamente para TODOS os CIDs da solicitação), o CID é
    tratado como baseline vazio (`[]`) -- explícito, nunca uma exceção não tratada."""
    status = report.get("status")
    if status != _REQUIRED_TERMINAL_STATUS:
        return ValidationResult(
            False,
            f"dry run: status esperado '{_REQUIRED_TERMINAL_STATUS}', obtido '{status}'.",
            reason_code="invalid_status",
        )
    if not report.get("started_at"):
        return ValidationResult(
            False, "dry run: started_at ausente -- solicitação nunca foi iniciada.", reason_code="missing_data"
        )
    if not report.get("finished_at"):
        return ValidationResult(
            False, "dry run: finished_at ausente -- solicitação nunca foi concluída.", reason_code="missing_data"
        )
    summary = report.get("summary")
    if not summary or not isinstance(summary, dict) or "results" not in summary:
        return ValidationResult(
            False, "dry run: summary ausente ou sem 'results' -- diff do dry run incoerente.", reason_code="missing_data"
        )
    results = summary.get("results") or []
    if len(results) != len(expected_external_ids):
        return ValidationResult(
            False,
            f"dry run: summary.results tem {len(results)} entrada(s), esperado exatamente "
            f"{len(expected_external_ids)} (um por CID solicitado).",
            reason_code="missing_data",
        )

    by_id = _raw_records_by_external_id(report)
    for cid in expected_external_ids:
        rec = by_id.get(cid)
        after_ids = {v["id"] for v in rec["versions"]} if rec is not None else set()
        before_ids = set(baseline_record_ids.get(cid, ()))
        new_ids = after_ids - before_ids
        if new_ids:
            return ValidationResult(
                False,
                f"CONTAMINAÇÃO DE FILA: CID {cid} tem {len(new_ids)} RawSourceRecord(s) novo(s) "
                f"(ids={sorted(new_ids)}) que não existiam no baseline capturado antes da "
                "submissão do dry run. Isto é ESTRUTURALMENTE IMPOSSÍVEL de ter sido criado pelo "
                "próprio dry run (o ramo dry_run de process_request() nunca persiste "
                "RawSourceRecord) -- portanto foi criado por outra solicitação (provavelmente "
                "uma solicitação real antiga reivindicada da fila compartilhada enquanto este "
                "dry run aguardava). Nunca atribuído ao dry run.",
                reason_code="queue_contamination",
            )
    return ValidationResult(True, "dry run: estado terminal de sucesso, sem nenhum novo RawSourceRecord (delta vazio).")


def validate_network_reachability(report: dict, expected_external_ids: Sequence[str]) -> ValidationResult:
    """Correção da Run 3 (item 9 da auditoria): o antigo passo `network_reachability` só exigia
    `status != "failed"` -- aceitando até um `status="partial"` com a maioria dos CIDs falhos, ou
    um `summary.fetch_errors` não vazio, como "rede alcançável". Esta função exige: status
    terminal literalmente `succeeded`; `summary.fetch_errors` vazio; e uma resposta
    genuinamente válida para cada CID esperado (`preferred_name` ou `formula` presente -- prova
    de que a resposta oficial realmente descreveu o composto, não um objeto vazio)."""
    status = report.get("status")
    if status != _REQUIRED_TERMINAL_STATUS:
        return ValidationResult(
            False,
            f"network_reachability: status esperado '{_REQUIRED_TERMINAL_STATUS}', obtido '{status}'.",
            reason_code="invalid_status",
        )
    summary = report.get("summary") or {}
    fetch_errors = summary.get("fetch_errors") or []
    if fetch_errors:
        return ValidationResult(
            False,
            f"network_reachability: summary.fetch_errors não vazio -- {fetch_errors!r}.",
            reason_code="fetch_errors_present",
        )
    results = summary.get("results") or []
    if len(results) != len(expected_external_ids):
        return ValidationResult(
            False,
            f"network_reachability: summary.results tem {len(results)} entrada(s), esperado "
            f"{len(expected_external_ids)}.",
            reason_code="missing_data",
        )
    by_external_id = {r.get("external_identifier"): r for r in results}
    for cid in expected_external_ids:
        r = by_external_id.get(cid)
        if r is None or not (r.get("preferred_name") or r.get("formula")):
            return ValidationResult(
                False,
                f"network_reachability: resposta para o CID {cid} sem preferred_name nem "
                "formula -- não é uma resposta oficial válida.",
                reason_code="invalid_response",
            )
    return ValidationResult(
        True,
        "network_reachability: resposta oficial válida (succeeded, sem fetch_errors) confirmada para todos os CIDs esperados.",
    )


def validate_real_report(report: dict, expected_external_ids: Sequence[str]) -> ValidationResult:
    """Requisito 7 (Run 2): estado terminal de sucesso; started_at/finished_at preenchidos;
    ausência de error; exatamente um RawSourceRecord por CID esperado; pelo menos uma versão por
    CID; hash SHA-256 não vazio. Reproduz e rejeita exatamente o cenário da Run 2
    (status='queued', started_at/finished_at nulos, version_count=0 para todos os CIDs) e
    qualquer status não-terminal ou terminal-mas-não-succeeded (cancelled, partial, failed)."""
    status = report.get("status")
    if status != _REQUIRED_TERMINAL_STATUS:
        return ValidationResult(
            False,
            f"execução real: status esperado '{_REQUIRED_TERMINAL_STATUS}', obtido '{status}'.",
            reason_code="invalid_status",
        )
    if not report.get("started_at"):
        return ValidationResult(
            False, "execução real: started_at ausente -- solicitação nunca foi iniciada.", reason_code="missing_data"
        )
    if not report.get("finished_at"):
        return ValidationResult(
            False, "execução real: finished_at ausente -- solicitação nunca foi concluída.", reason_code="missing_data"
        )
    if report.get("error"):
        return ValidationResult(
            False, f"execução real: error presente -- {report['error']!r}.", reason_code="missing_data"
        )

    for cid in expected_external_ids:
        matches = [rec for rec in report.get("raw_source_records", []) if rec["external_id"] == cid]
        if len(matches) != 1:
            return ValidationResult(
                False,
                f"execução real: esperava exatamente 1 entrada de RawSourceRecord para o CID {cid}, encontrou {len(matches)}.",
                reason_code="missing_data",
            )
        rec = matches[0]
        if rec["version_count"] < 1:
            return ValidationResult(
                False,
                f"execução real: CID {cid} tem version_count={rec['version_count']} -- esperado >= 1.",
                reason_code="missing_data",
            )
        latest_version = rec["versions"][-1] if rec["versions"] else None
        sha256 = latest_version.get("payload_sha256") if latest_version else None
        if not sha256:
            return ValidationResult(
                False, f"execução real: CID {cid} tem hash SHA-256 vazio/ausente.", reason_code="missing_data"
            )
    return ValidationResult(True, "execução real: estado terminal de sucesso, RawSourceRecord completo para todos os CIDs.")


def validate_idempotency(
    report_round_1: dict, report_round_2: dict, expected_external_ids: Sequence[str]
) -> IdempotencyResult:
    """Requisito 8 (Run 2): aprovada somente se, para TODOS os CIDs esperados -- houver registro
    e versão na primeira rodada; houver registro correspondente na segunda; os hashes forem
    iguais; a contagem de versões não aumentar; e `every(extra.ok)` for verdadeiro. Lista vazia
    (nenhum CID esperado) ou qualquer item falso reprova -- nunca aprovado por omissão."""
    by_id_1 = _raw_records_by_external_id(report_round_1)
    by_id_2 = _raw_records_by_external_id(report_round_2)
    details: list[dict] = []

    for cid in expected_external_ids:
        rec1 = by_id_1.get(cid)
        rec2 = by_id_2.get(cid)
        if rec1 is None or rec1["version_count"] == 0:
            details.append(
                {
                    "cid": cid,
                    "ok": False,
                    "reason": "sem RawSourceRecord na primeira rodada (busca deste CID pode ter falhado)",
                }
            )
            continue
        if rec2 is None or rec2["version_count"] == 0:
            details.append(
                {"cid": cid, "ok": False, "reason": "sem RawSourceRecord na segunda rodada"}
            )
            continue

        hash1 = rec1["versions"][-1]["payload_sha256"]
        hash2 = rec2["versions"][-1]["payload_sha256"]
        count1 = rec1["version_count"]
        count2 = rec2["version_count"]
        same_hash = hash1 == hash2
        no_new_version = count2 == count1
        item_ok = same_hash and no_new_version
        detail: dict = {
            "cid": cid,
            "ok": item_ok,
            "sha256_round1": hash1,
            "sha256_round2": hash2,
            "version_count_round1": count1,
            "version_count_round2": count2,
        }
        if not item_ok:
            detail["reason"] = (
                "hash divergente entre rodadas" if not same_hash else "nova versão criada na segunda rodada (não deveria)"
            )
        details.append(detail)

    # Requisito 8, literal: lista vazia reprova; qualquer item falso reprova.
    overall_ok = bool(details) and all(d["ok"] for d in details)
    return IdempotencyResult(ok=overall_ok, details=details)
