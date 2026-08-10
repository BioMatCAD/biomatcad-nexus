#!/usr/bin/env python3
"""Validação explícita e testável dos relatórios do piloto PubChem Windows -- correção do falso
positivo confirmado na Run 2 (`INVALID_FALSE_POSITIVE`, relatório com SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`).

Bug real da Run 2 (`Run-PubChemPilotWindows.ps1`): os passos `real_result_1`/`real_result_2`
aceitavam qualquer status DIFERENTE do literal `"failed"` como sucesso
(`-Ok ($report.status -ne "failed")`) -- `"queued"` também passa nesse teste, então uma
solicitação que nunca saiu da fila (started_at/finished_at nulos, zero RawSourceRecord) era
relatada como `ok=true`. Separadamente, o passo `idempotency_proof` construía uma lista de
detalhes por CID marcando cada item individual como `ok=false` quando faltava RawSourceRecord,
mas o branch que fazia isso esquecia de também marcar a variável agregada
`$idempotencyOk = $false` antes do `continue` -- resultado: `idempotency_proof.ok=true` mesmo
com TODOS os itens de `.extra` mostrando `ok=false`. Nenhuma das duas checagens exigia sequer
que a solicitação tivesse saído do estado `queued`.

Este módulo substitui as duas checagens por funções puras (sem acesso a banco -- operam sobre o
dicionário de relatório já construído por `pubchem_pilot_report.py::build_pilot_report`),
diretamente testáveis reproduzindo a evidência literal da Run 2."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

#: Único estado aceito para uma solicitação REAL (persistente) do piloto: com apenas os 3 CIDs
#: sintéticos conhecidos e bem formados (aspirina/etanol/ibuprofeno), qualquer coisa diferente
#: de SUCCEEDED (PARTIAL, FAILED, ou -- o defeito desta rodada -- QUEUED/RUNNING) indica um
#: problema real que este piloto controlado deve expor, nunca mascarar.
_REQUIRED_TERMINAL_STATUS = "succeeded"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str


@dataclass(frozen=True)
class IdempotencyResult:
    ok: bool
    details: list[dict] = field(default_factory=list)


def _raw_records_by_external_id(report: dict) -> dict[str, dict]:
    return {rec["external_id"]: rec for rec in report.get("raw_source_records", [])}


def validate_dry_run_report(report: dict, expected_external_ids: Sequence[str]) -> ValidationResult:
    """Requisito 6: estado terminal de sucesso; started_at/finished_at preenchidos; summary/diff
    coerente; NENHUMA persistência de RawSourceRecord (dry run nunca persiste)."""
    status = report.get("status")
    if status != _REQUIRED_TERMINAL_STATUS:
        return ValidationResult(
            False, f"dry run: status esperado '{_REQUIRED_TERMINAL_STATUS}', obtido '{status}'."
        )
    if not report.get("started_at"):
        return ValidationResult(False, "dry run: started_at ausente -- solicitação nunca foi iniciada.")
    if not report.get("finished_at"):
        return ValidationResult(False, "dry run: finished_at ausente -- solicitação nunca foi concluída.")
    summary = report.get("summary")
    if not summary or not isinstance(summary, dict) or "results" not in summary:
        return ValidationResult(False, "dry run: summary ausente ou sem 'results' -- diff do dry run incoerente.")
    results = summary.get("results") or []
    if len(results) != len(expected_external_ids):
        return ValidationResult(
            False,
            f"dry run: summary.results tem {len(results)} entrada(s), esperado exatamente "
            f"{len(expected_external_ids)} (um por CID solicitado).",
        )
    by_id = _raw_records_by_external_id(report)
    for cid in expected_external_ids:
        rec = by_id.get(cid)
        version_count = rec["version_count"] if rec is not None else 0
        if version_count != 0:
            return ValidationResult(
                False,
                f"dry run: CID {cid} tem {version_count} RawSourceRecord(s) -- dry run NUNCA "
                "deve persistir nada.",
            )
    return ValidationResult(True, "dry run: estado terminal de sucesso, sem nenhuma persistência.")


def validate_real_report(report: dict, expected_external_ids: Sequence[str]) -> ValidationResult:
    """Requisito 7: estado terminal de sucesso; started_at/finished_at preenchidos; ausência de
    error; exatamente um RawSourceRecord por CID esperado; pelo menos uma versão por CID; hash
    SHA-256 não vazio. Reproduz e rejeita exatamente o cenário da Run 2 (status='queued',
    started_at/finished_at nulos, version_count=0 para todos os CIDs)."""
    status = report.get("status")
    if status != _REQUIRED_TERMINAL_STATUS:
        return ValidationResult(
            False, f"execução real: status esperado '{_REQUIRED_TERMINAL_STATUS}', obtido '{status}'."
        )
    if not report.get("started_at"):
        return ValidationResult(False, "execução real: started_at ausente -- solicitação nunca foi iniciada.")
    if not report.get("finished_at"):
        return ValidationResult(False, "execução real: finished_at ausente -- solicitação nunca foi concluída.")
    if report.get("error"):
        return ValidationResult(False, f"execução real: error presente -- {report['error']!r}.")

    for cid in expected_external_ids:
        matches = [rec for rec in report.get("raw_source_records", []) if rec["external_id"] == cid]
        if len(matches) != 1:
            return ValidationResult(
                False, f"execução real: esperava exatamente 1 entrada de RawSourceRecord para o CID {cid}, encontrou {len(matches)}."
            )
        rec = matches[0]
        if rec["version_count"] < 1:
            return ValidationResult(
                False, f"execução real: CID {cid} tem version_count={rec['version_count']} -- esperado >= 1."
            )
        latest_version = rec["versions"][-1] if rec["versions"] else None
        sha256 = latest_version.get("payload_sha256") if latest_version else None
        if not sha256:
            return ValidationResult(False, f"execução real: CID {cid} tem hash SHA-256 vazio/ausente.")
    return ValidationResult(True, "execução real: estado terminal de sucesso, RawSourceRecord completo para todos os CIDs.")


def validate_idempotency(
    report_round_1: dict, report_round_2: dict, expected_external_ids: Sequence[str]
) -> IdempotencyResult:
    """Requisito 8: aprovada somente se, para TODOS os CIDs esperados -- houver registro e
    versão na primeira rodada; houver registro correspondente na segunda; os hashes forem
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
