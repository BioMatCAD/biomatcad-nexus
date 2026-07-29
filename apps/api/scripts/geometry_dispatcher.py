#!/usr/bin/env python3
"""Dispatcher de jobs geométricos -- processo separado da API (Incremento 2.1, item 4).

Consome GeometryJob.status == QUEUED (a própria coluna é a fila) e chama dispatch_job() para
cada um. Roda como um processo Python distinto (`python scripts/geometry_dispatcher.py`),
nunca dentro do processo uvicorn da API -- satisfaz o requisito explícito de que o processo
geométrico seja separado da API. O worker C#/PicoGK em si é o processo verdadeiramente
separado, invocado via subprocess a partir daqui.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from biomatcad_api.config import get_settings
from biomatcad_api.db import SessionLocal
from biomatcad_api.models.geometry_job import GeometryJob, JobStatus
from biomatcad_api.services.geometry_job_service import dispatch_job
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import get_default_worker_client

REPO_ROOT = Path(__file__).resolve().parents[3]


def process_queued_jobs(limit: int | None = None) -> int:
    settings = get_settings()
    storage = LocalStorageAdapter(Path(settings.artifact_storage_dir))
    worker_client = get_default_worker_client(REPO_ROOT)
    db = SessionLocal()
    processed = 0
    try:
        query = db.query(GeometryJob).filter(GeometryJob.status == JobStatus.QUEUED)
        if limit is not None:
            query = query.limit(limit)
        job_ids = [j.id for j in query.all()]
        for job_id in job_ids:
            dispatch_job(
                db,
                job_id=job_id,
                worker_client=worker_client,
                storage=storage,
                output_dir=Path(settings.artifact_storage_dir) / "_work" / job_id,
                repo_root=REPO_ROOT,
            )
            processed += 1
    finally:
        db.close()
    return processed


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatcher de jobs geométricos BioMatCAD Nexus.")
    parser.add_argument("--once", action="store_true", help="Processa a fila uma vez e sai.")
    parser.add_argument("--limit", type=int, default=None, help="Número máximo de jobs a processar.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Segundos entre polls.")
    args = parser.parse_args()

    if args.once:
        n = process_queued_jobs(limit=args.limit)
        print(f"Processados {n} job(s).")
        return

    print("Dispatcher geométrico iniciado (Ctrl+C para parar).")
    while True:
        n = process_queued_jobs(limit=args.limit)
        if n:
            print(f"Processados {n} job(s).")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
