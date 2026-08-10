#!/usr/bin/env python3
"""Acompanha uma solicitação de ingestão ESPECÍFICA (por `request_id`) até um estado terminal,
processando a fila enquanto espera -- correção do falso positivo confirmado na Run 2 do piloto
PubChem Windows (`INVALID_FALSE_POSITIVE`, relatório com SHA-256
`83c22b55db98e5a4daea6f9e9fcabdee0aac56c1d1429510be0fce023bb8610f`).

Causa real da Run 2: `Run-PubChemPilotWindows.ps1` chamava o dispatcher uma única vez
(`scientific_ingestion_dispatcher.py --once --limit 1`) e só verificava a CONTAGEM devolvida
("Processada(s) N solicitação(ões)."), nunca se a solicitação ESPECÍFICA que o próprio roteiro
tinha acabado de submeter chegou a um estado terminal. `claim_next_queued_request()` reivindica
sempre a solicitação MAIS ANTIGA da fila inteira (FIFO global, por design -- correto para um
dispatcher de produção, que deve processar QUALQUER solicitação pendente, de qualquer
organização). Se já existir qualquer solicitação `queued` mais antiga no mesmo banco Postgres
persistente do usuário (de uma tentativa anterior, de outro teste manual, etc.), o dispatcher
processa de verdade essa OUTRA solicitação a cada chamada -- e devolve `count=1`, uma contagem
literalmente correta -- enquanto a solicitação que o piloto está esperando nunca é sequer
reivindicada, permanecendo `queued` para sempre. Este módulo resolve isso ACOMPANHANDO o
`request_id` exato, chamando o dispatcher repetidamente (drenando a fila item a item, na ordem
real) até que ESSA solicitação especificamente atinja um estado terminal, com timeout explícito
e polling limitado -- nunca aceita `queued`/`running` como sucesso, nunca se contenta com uma
contagem global."""
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
    claim_next_queued_request,
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
    limite): a cada iteração, tenta reivindicar e processar UMA solicitação da fila (que pode ou
    não ser a que estamos esperando -- drenando assim qualquer backlog antigo item a item, na
    ordem FIFO real do dispatcher de produção), depois relê o estado ATUAL de `request_id` a
    partir de uma consulta nova (nunca um objeto ORM em cache). Retorna o relatório assim que o
    estado for terminal. Levanta `RequestTerminalTimeoutError` se o timeout for atingido antes
    disso, e `RequestNotFoundError` se `request_id` nunca existiu."""
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

        claimed = claim_next_queued_request(db, dispatcher_id=dispatcher_id)
        if claimed is not None:
            process_request(db, request=claimed)
            # Processou algo (talvez a nossa, talvez uma solicitação antiga da fila) --
            # verifica de novo imediatamente, sem dormir, já que há trabalho real acontecendo.
            continue

        # Fila vazia neste instante e a nossa solicitação ainda não é terminal -- só faz
        # sentido se outro processo a reivindicou concorrentemente e ainda não terminou (ou
        # commitou). Espera um intervalo curto e tenta de novo, sempre respeitando o timeout.
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
