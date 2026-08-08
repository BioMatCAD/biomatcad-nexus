#!/usr/bin/env python3
"""Relatório de evidência de uma solicitação de ingestão PubChem (Incremento 2.3, Rodada 2,
Fase I). Usado por scripts/Run-PubChemPilotWindows.ps1 para preservar, em JSON, exatamente o
que o piloto Windows precisa provar: status final da solicitação, e para cada identificador
externo envolvido, o(s) `RawSourceRecord` real(is) (endpoint, timestamp, status HTTP,
SHA-256 do payload canônico, predecessor) -- nunca o payload bruto completo aqui (evita um
relatório gigante; o payload continua integralmente preservado na tabela `raw_source_records`
em si, consultável separadamente se necessário)."""
from __future__ import annotations

import argparse
import json
import sys

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_ingestion import RawSourceRecord, ScientificIngestionRequest


def main() -> int:
    parser = argparse.ArgumentParser(description="Relatório JSON de uma solicitação de ingestão PubChem.")
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        request = db.get(ScientificIngestionRequest, args.request_id)
        if request is None:
            print(f"ERRO: solicitação '{args.request_id}' não encontrada.", file=sys.stderr)
            return 2

        raw_records = []
        for external_id in request.external_ids:
            records = (
                db.query(RawSourceRecord)
                .filter(
                    RawSourceRecord.source_id == request.source_id,
                    RawSourceRecord.connector_id == request.connector_id,
                    RawSourceRecord.external_record_id == external_id,
                )
                .order_by(RawSourceRecord.created_at.asc())
                .all()
            )
            raw_records.append(
                {
                    "external_id": external_id,
                    "version_count": len(records),
                    "versions": [
                        {
                            "id": r.id,
                            "requested_endpoint": r.requested_endpoint,
                            "http_status": r.http_status,
                            "content_type": r.content_type,
                            "fetched_at": r.fetched_at.isoformat(),
                            "payload_sha256": r.payload_sha256,
                            "payload_size_bytes": r.payload_size_bytes,
                            "parsing_status": r.parsing_status.value,
                            "predecessor_record_id": r.predecessor_record_id,
                            "created_at": r.created_at.isoformat(),
                        }
                        for r in records
                    ],
                }
            )

        report = {
            "request_id": request.id,
            "status": request.status.value,
            "dry_run": request.dry_run,
            "connector_id": request.connector_id,
            "source_id": request.source_id,
            "external_ids": request.external_ids,
            "created_at": request.created_at.isoformat(),
            "started_at": request.started_at.isoformat() if request.started_at else None,
            "finished_at": request.finished_at.isoformat() if request.finished_at else None,
            "attempt_number": request.attempt_number,
            "summary": request.summary,
            "error": request.error,
            "raw_source_records": raw_records,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
