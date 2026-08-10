#!/usr/bin/env python3
"""Captura o baseline de `RawSourceRecord` por CID -- ANTES de submeter uma nova solicitação --
para permitir validação por DELTA em vez de contagem absoluta (Incremento 2.3, Rodada 2, Fase
I; correção do `QUEUE_CONTAMINATION` confirmado na Run 3, ver
docs/data/connectors/PUBCHEM_CONNECTOR.md).

Motivo: `validate_dry_run_report` (Run 2) exigia ZERO `RawSourceRecord` absoluto por CID no
relatório final -- mas na Run 3, o CID 2244 já tinha `RawSourceRecord`s de uma solicitação REAL
completamente legítima e anterior (nada a ver com o dry run desta execução), e o roteiro
acusou incorretamente "dry run persistiu dados". Um `RawSourceRecord` pré-existente é NORMAL em
produção (o mesmo CID pode já ter sido importado por outra solicitação, dias antes) -- o que o
dry run realmente nunca pode fazer é CRIAR um novo. A única forma correta de verificar isso é
comparar um snapshot ANTES (este script) com um snapshot DEPOIS (via
`pubchem_pilot_report.py::build_pilot_report`, já usado pelo restante do piloto) e exigir que o
conjunto de versões não mude -- nunca um "sempre zero" absoluto."""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.orm import Session

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_ingestion import RawSourceRecord


def capture_raw_record_baseline(
    db: Session, *, connector_id: str, source_id: str, external_ids: list[str]
) -> dict[str, list[str]]:
    """Devolve, para cada `external_id` informado, a lista de IDs de `RawSourceRecord` já
    existentes NESTE INSTANTE para o par (`connector_id`, `source_id`, `external_id`). Consulta
    sempre uma sessão nova/fresca (nunca reaproveita estado ORM em cache) -- o mesmo cuidado já
    aplicado em `build_pilot_report`."""
    baseline: dict[str, list[str]] = {}
    for external_id in external_ids:
        ids = [
            r.id
            for r in (
                db.query(RawSourceRecord.id)
                .filter(
                    RawSourceRecord.source_id == source_id,
                    RawSourceRecord.connector_id == connector_id,
                    RawSourceRecord.external_record_id == external_id,
                )
                .all()
            )
        ]
        baseline[external_id] = ids
    return baseline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Captura o baseline de RawSourceRecord por CID antes de submeter uma solicitação."
    )
    parser.add_argument("--connector-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--cid", action="append", required=True, dest="external_ids")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        baseline = capture_raw_record_baseline(
            db, connector_id=args.connector_id, source_id=args.source_id, external_ids=args.external_ids
        )
        print(json.dumps(baseline, ensure_ascii=False))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
