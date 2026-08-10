#!/usr/bin/env python3
"""Acompanha uma solicitação de ingestão ESPECÍFICA (por `request_id`) até um estado terminal,
reivindicando e processando SOMENTE essa solicitação -- nunca qualquer outra linha da fila.

Histórico de duas correções nesta mesma função:

Run 2 (`INVALID_FALSE_POSITIVE`, relatório SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`): `Run-PubChemPilotWindows.ps1`
chamava o dispatcher uma única vez (`--once --limit 1`) e só verificava a CONTAGEM devolvida,
nunca se a solicitação ESPECÍFICA que o próprio roteiro tinha acabado de submeter chegou a um
estado terminal -- uma solicitação `queued` mais antiga no mesmo banco persistente era
processada no lugar, e a solicitação do piloto nunca saía de `queued`.

Run 3 (`QUEUE_CONTAMINATION`, ver docs/data/connectors/PUBCHEM_CONNECTOR.md): a primeira
correção deste módulo resolveu a Run 2 acompanhando o `request_id` exato, mas ainda chamava
`claim_next_queued_request()` (FIFO global, `SELECT ... FOR UPDATE SKIP LOCKED` ordenado por
`created_at`) a cada iteração para "drenar a fila enquanto espera" -- e isso tem um efeito
colateral real: se existir qualquer OUTRA solicitação `queued` mais antiga (real, não
relacionada) no mesmo banco persistente, esta função a reivindica e PROCESSA de verdade,
criando `RawSourceRecord`s/entidades reais atribuídos por engano ao dry run que o piloto estava
esperando (evidência literal da Run 3: 3 `RawSourceRecord`s criados entre 17:21:18 e 17:21:21,
todos ANTES do `started_at` do próprio dry run às 17:21:27 -- uma atribuição temporalmente
impossível, já que o ramo `dry_run` de `process_request()` nunca chama
`_persist_raw_source_record`).

Correção definitiva: esta função agora usa `claim_specific_request()`
(`scientific_ingestion_service.py`), que reivindica SOMENTE a linha `request_id` informada --
nunca qualquer outra. Nunca mais drena a fila global. Se a solicitação-alvo ainda não é
`queued` no momento em que tentamos reivindicá-la (por exemplo, outro processo -- um dispatcher
de produção real -- a reivindicou primeiro), esta função apenas aguarda e tenta de novo, sem
tocar em nenhuma outra linha, sempre respeitando o timeout explícito e o polling limitado --
nunca aceita `queued`/`running` como sucesso."""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable

from pubchem_pilot_report import build_pilot_report  # type: ignore[import-not-found]
from sqlalchemy.orm import Session

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
)
from biomatcad_api.services.scientific_ingestion_service import (
    claim_specific_request,
    process_request,
)

#: Estados que encerram o ciclo de vida de uma solicitação -- ver IngestionRequestStatus em
#: models/scientific_ingestion.py. QUEUED e RUNNING nunca são aceitos como resultado final.
TERMINAL_STATUSES = frozenset(
    {
        IngestionRequestStatus.SUCCEEDED,
        IngestionRequestStatus.PARTIAL,
        IngestionRequestStatus.FAILED,
        IngestionRequestStatus.CANCELLED,
    }
)


class RequestNotFoundError(RuntimeError):
    """`request_id` não existe no banco -- nunca deveria acontecer logo após uma submissão bem
    sucedida, mas é tratado explicitamente em vez de deixar uma exceção genérica escapar."""


class RequestTerminalTimeoutError(RuntimeError):
    """A solicitação não atingiu um estado terminal dentro do timeout configurado -- inclui o
    último relatório conhecido (`last_report`) para diagnóstico, nunca escondido."""

    def __init__(self, request_id: str, timeout_seconds: float, last_report: dict | None) -> None:
        self.request_id = request_id
        self.timeout_seconds = timeout_seconds
        self.last_report = last_report
        last_status = last_report["status"] if last_report else "desconhecido (sem relatório)"
        super().__init__(
            f"Solicitação {request_id} não atingiu estado terminal em {timeout_seconds}s "
            f"(último status observado: '{last_status}'). Possíveis causas: um backlog antigo "
            "de solicitações 'queued' pré-existentes no mesmo banco ainda não foi totalmente "
            "drenado, ou nenhum worker está de fato processando a fila."
        )


def wait_for_request_terminal(
    db: Session,
    *,
    request_id: str,
    dispatcher_id: str | None = None,
    poll_interval_seconds: float = 2.0,
    timeout_seconds: float = 180.0,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> dict:
    """Loop de espera com timeout explícito e polling limitado (nunca um `while True` sem
    limite): a cada iteração, tenta reivindicar SOMENTE `request_id` via
    `claim_specific_request()` (nunca qualquer outra linha da fila -- ver docstring do módulo
    para a correção da Run 3, `QUEUE_CONTAMINATION`), depois relê o estado ATUAL a partir de uma
    consulta nova (nunca um objeto ORM em cache). Retorna o relatório assim que o estado for
    terminal. Levanta `RequestTerminalTimeoutError` se o timeout for atingido antes disso, e
    `RequestNotFoundError` se `request_id` nunca existiu."""
    dispatcher_id = dispatcher_id or "pubchem-pilot-wait-for-terminal"
    start = monotonic_fn()
    last_report: dict | None = None

    while True:
        db.expire_all()
        report = build_pilot_report(db, request_id)
        if report is None:
            raise RequestNotFoundError(f"Solicitação '{request_id}' não encontrada.")
        last_report = report
        if IngestionRequestStatus(report["status"]) in TERMINAL_STATUSES:
            return report

        if monotonic_fn() - start >= timeout_seconds:
            raise RequestTerminalTimeoutError(request_id, timeout_seconds, last_report)

        claimed = claim_specific_request(db, request_id=request_id, dispatcher_id=dispatcher_id)
        if claimed is not None:
            process_request(db, request=claimed)
            # Processou a NOSSA solicitação (nunca outra -- claim_specific_request nunca toca em
            # nenhuma outra linha) -- verifica de novo imediatamente, sem dormir.
            continue

        # `claim_specific_request` devolveu None: ou a solicitação já não está mais `queued`
        # (outro processo -- ex.: um dispatcher de produção real -- a reivindicou primeiro, ou
        # ela já terminou entre a leitura do relatório acima e agora), ou ainda não existe
        # nenhuma linha `queued` com esse id no instante exato desta tentativa. Em ambos os
        # casos, NUNCA tentamos reivindicar outra linha da fila -- apenas esperamos um intervalo
        # curto e checamos de novo, sempre respeitando o timeout.
        if monotonic_fn() - start >= timeout_seconds:
            raise RequestTerminalTimeoutError(request_id, timeout_seconds, last_report)
        sleep_fn(poll_interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Acompanha uma solicitação de ingestão PubChem até um estado terminal (nunca aceita queued/running)."
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--dispatcher-id", default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        try:
            report = wait_for_request_terminal(
                db,
                request_id=args.request_id,
                dispatcher_id=args.dispatcher_id,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )
        except RequestNotFoundError as exc:
            print(json.dumps({"ok": False, "reason": str(exc), "report": None}, ensure_ascii=False))
            return 2
        except RequestTerminalTimeoutError as exc:
            print(
                json.dumps(
                    {"ok": False, "reason": str(exc), "report": exc.last_report}, ensure_ascii=False
                )
            )
            return 1
        print(json.dumps({"ok": True, "reason": "estado terminal alcançado", "report": report}, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
