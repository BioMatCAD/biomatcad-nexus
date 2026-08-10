#!/usr/bin/env python3
"""Preflight de limpeza da fila (Incremento 2.3, Rodada 2, Fase I) -- correção do
`QUEUE_CONTAMINATION` confirmado na Run 3 do piloto PubChem Windows (2026-08-10, ver
docs/data/connectors/PUBCHEM_CONNECTOR.md).

Antes de submeter qualquer solicitação nova, o piloto precisa saber se já existe alguma
solicitação `queued`/`running` ANTIGA para o mesmo `connector_id`/`source_id` -- porque, mesmo
com `pubchem_pilot_wait_for_terminal.py` corrigido para reivindicar SOMENTE o `request_id` exato
(nunca drenar a fila global), uma solicitação antiga do mesmo par conector/fonte ainda pode ser
reivindicada e processada por um dispatcher de produção real rodando em paralelo, ou por uma
execução manual concorrente -- criando `RawSourceRecord`s/entidades cujo timing pode ser
confundido com o desta execução do piloto (exatamente o que a Run 3 expôs). Detectar isso ANTES
de submeter é preferível a detectar depois: falha rápido, com diagnóstico explícito, em vez de
deixar o piloto inteiro rodar para só então descobrir uma contaminação que já aconteceu.

Nunca resolve a contaminação automaticamente (nunca cancela/apaga a solicitação antiga) -- isso
exigiria uma decisão humana sobre o que fazer com ela (é uma solicitação legítima de um
dispatcher de produção real? um teste manual esquecido? uma falha anterior do próprio piloto?).
Apenas relata e recusa prosseguir."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.orm import Session

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
    ScientificIngestionRequest,
)


def find_contaminating_requests(
    db: Session, *, connector_id: str, source_id: str, exclude_request_ids: tuple[str, ...] = ()
) -> list[dict]:
    """Solicitações `queued`/`running` já existentes para o mesmo `connector_id`/`source_id`,
    em ordem FIFO real (a ordem em que um dispatcher de produção as reivindicaria) -- nunca
    filtra por quem as submeteu, porque a contaminação é sobre a FILA compartilhada, não sobre o
    usuário."""
    query = db.query(ScientificIngestionRequest).filter(
        ScientificIngestionRequest.connector_id == connector_id,
        ScientificIngestionRequest.source_id == source_id,
        ScientificIngestionRequest.status.in_(
            [IngestionRequestStatus.QUEUED, IngestionRequestStatus.RUNNING]
        ),
    )
    if exclude_request_ids:
        query = query.filter(ScientificIngestionRequest.id.notin_(exclude_request_ids))
    rows = query.order_by(ScientificIngestionRequest.created_at.asc()).all()
    return [
        {
            "id": r.id,
            "status": r.status.value,
            "dry_run": r.dry_run,
            "external_ids": r.external_ids,
            "created_at": r.created_at.isoformat(),
            "claimed_by_dispatcher_id": r.claimed_by_dispatcher_id,
        }
        for r in rows
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verifica se existe alguma solicitação queued/running antiga para o mesmo "
            "connector_id/source_id antes de submeter uma nova (preflight anti-contaminação)."
        )
    )
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--exclude-request-id",
        action="append",
        default=[],
        help="request_id a ignorar na verificação (repetível) -- nunca usado para esconder "
        "contaminação real, apenas para excluir solicitações que o próprio chamador acabou de "
        "submeter intencionalmente nesta mesma execução, se aplicável.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        contaminating = find_contaminating_requests(
            db,
            connector_id=args.connector_id,
            source_id=args.source_id,
            exclude_request_ids=tuple(args.exclude_request_id),
        )
        ok = len(contaminating) == 0
        reason = (
            "fila limpa: nenhuma solicitação queued/running pré-existente para este "
            "connector_id/source_id."
            if ok
            else f"fila contaminada: {len(contaminating)} solicitação(ões) queued/running "
            "pré-existente(s) encontrada(s) para este connector_id/source_id -- ver "
            "'contaminating' para os detalhes. Nenhuma delas será processada por este preflight "
            "(nunca resolvida automaticamente); decisão humana necessária antes de prosseguir."
        )
        print(
            json.dumps(
                {"ok": ok, "reason": reason, "contaminating": contaminating}, ensure_ascii=False
            )
        )
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
