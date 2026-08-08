#!/usr/bin/env python3
"""CLI de operação da ingestão PubChem (Incremento 2.3, Rodada 2, Fase H).

Ferramenta de OPERADOR (roda no mesmo host/venv do backend, acesso direto ao banco via
`SessionLocal` -- mesmo padrão de scripts/scientific_ingestion_dispatcher.py, nunca via HTTP).
Exige uma lista EXPLÍCITA de CIDs -- nunca busca por nome, nunca "todos os CIDs de uma
categoria". O default de no máximo 10 CIDs por submissão (mesmo limite de
config.py::pubchem_max_cids_per_request) é aplicado tanto aqui quanto (de forma autoritativa)
dentro de `PubChemConnector.validate_request` -- este script nunca contorna essa validação.

Autorização: exige `--requested-by-email` de um usuário com papel admin/superadmin já existente
no banco (mesmos papéis de `routers/auth.py::ADMIN_ROLES`) -- o script nunca cria um usuário
novo nem eleva privilégio; apenas identifica QUEM está submetendo, para fins de auditoria
(AuditEvent já registrado dentro de `submit_ingestion_request`).

Este script apenas ENFILEIRA a solicitação (dry_run ou real) -- o processamento em si continua
sendo feito pelo dispatcher (scripts/scientific_ingestion_dispatcher.py), rodando em `--once` ou
em modo contínuo. Use `--wait` para que este script, após enfileirar, aguarde (com timeout) até
a solicitação sair de queued/running, útil para uso interativo/roteiros Windows -- mas nunca
processa a solicitação ele mesmo.

Exemplos:
    python scripts/pubchem_ingest_cli.py --requested-by-email admin@biomatcad.example \\
        --source-id <id-da-fonte-pubchem> --cid 2244 --cid 702 --dry-run

    python scripts/pubchem_ingest_cli.py --requested-by-email admin@biomatcad.example \\
        --source-id <id-da-fonte-pubchem> --cid 2244 --wait --wait-timeout-seconds 120
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
    ScientificIngestionRequest,
)
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import ADMIN_ROLES
from biomatcad_api.services.scientific_ingestion_service import (
    IngestionRequestError,
    submit_ingestion_request,
)

DEFAULT_MAX_CIDS = 10
_TERMINAL_STATUSES = frozenset(
    {
        IngestionRequestStatus.SUCCEEDED,
        IngestionRequestStatus.PARTIAL,
        IngestionRequestStatus.FAILED,
        IngestionRequestStatus.CANCELLED,
    }
)


def _request_to_dict(request: ScientificIngestionRequest) -> dict:
    return {
        "id": request.id,
        "status": request.status.value,
        "dry_run": request.dry_run,
        "external_ids": request.external_ids,
        "connector_id": request.connector_id,
        "source_id": request.source_id,
        "created_at": request.created_at.isoformat(),
        "started_at": request.started_at.isoformat() if request.started_at else None,
        "finished_at": request.finished_at.isoformat() if request.finished_at else None,
        "summary": request.summary,
        "error": request.error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submete uma solicitação de ingestão PubChem (lista explícita de CIDs, nunca busca aberta)."
    )
    parser.add_argument("--requested-by-email", required=True, help="E-mail de um usuário admin/superadmin já existente.")
    parser.add_argument("--source-id", required=True, help="ID do ScientificSource (ex.: registro PubChem do seed).")
    parser.add_argument(
        "--cid", action="append", dest="cids", required=True,
        help=f"Um CID do PubChem (repita a flag para vários; máximo {DEFAULT_MAX_CIDS} por submissão).",
    )
    parser.add_argument("--connector-id", default="pubchem_pug_rest", help="ID do conector (default: pubchem_pug_rest).")
    parser.add_argument("--dry-run", action="store_true", help="Apenas mostra o diff -- nunca persiste nada.")
    parser.add_argument("--wait", action="store_true", help="Aguarda a solicitação sair de queued/running antes de retornar.")
    parser.add_argument("--wait-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--wait-poll-interval-seconds", type=float, default=2.0)
    args = parser.parse_args()

    if len(args.cids) > DEFAULT_MAX_CIDS:
        print(
            f"ERRO: {len(args.cids)} CIDs informados, acima do máximo de {DEFAULT_MAX_CIDS} por submissão "
            "deste piloto. Nunca importação em massa -- ver docs/data/connectors/PUBCHEM_CONNECTOR.md.",
            file=sys.stderr,
        )
        return 2

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.requested_by_email, User.is_active.is_(True)).first()
        if user is None:
            print(f"ERRO: usuário '{args.requested_by_email}' não encontrado ou inativo.", file=sys.stderr)
            return 2
        if user.role not in ADMIN_ROLES:
            print(
                f"ERRO: usuário '{args.requested_by_email}' tem papel '{user.role}' -- "
                f"esta operação exige um dos papéis: {sorted(ADMIN_ROLES)}.",
                file=sys.stderr,
            )
            return 2

        try:
            request = submit_ingestion_request(
                db,
                organization_id=user.organization_id,
                requested_by_user_id=user.id,
                connector_id=args.connector_id,
                source_id=args.source_id,
                external_ids=args.cids,
                dry_run=args.dry_run,
            )
        except IngestionRequestError as exc:
            print(f"ERRO ({exc.reason_code}): {exc}", file=sys.stderr)
            return 2

        print(json.dumps(_request_to_dict(request), ensure_ascii=False, indent=2))

        if args.wait:
            deadline = time.monotonic() + args.wait_timeout_seconds
            while time.monotonic() < deadline:
                db.expire(request)
                fresh = db.get(ScientificIngestionRequest, request.id)
                if fresh is not None and fresh.status in _TERMINAL_STATUSES:
                    print("--- resultado final ---")
                    print(json.dumps(_request_to_dict(fresh), ensure_ascii=False, indent=2))
                    return 0
                time.sleep(args.wait_poll_interval_seconds)
            print(
                f"AVISO: tempo limite de {args.wait_timeout_seconds}s atingido sem a solicitação "
                "terminar -- ela continua na fila/em execução; verifique novamente mais tarde "
                "(GET /api/v1/scientific-ingestion/requests/{id}).",
                file=sys.stderr,
            )
            return 3

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
