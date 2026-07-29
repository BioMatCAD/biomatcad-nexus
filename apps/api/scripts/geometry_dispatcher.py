#!/usr/bin/env python3
"""Dispatcher de jobs geométricos -- processo separado da API (Incremento 2.1, item 4;
Incremento 2.1.1, item 6).

Consome a fila via claim_next_queued_job() (SELECT ... FOR UPDATE SKIP LOCKED, atômico -- dois
dispatchers concorrentes nunca reivindicam o mesmo job) e chama dispatch_job() para cada job já
reivindicado. Roda como um processo Python distinto (`python scripts/geometry_dispatcher.py`),
nunca dentro do processo uvicorn da API -- satisfaz o requisito explícito de que o processo
geométrico seja separado da API. O worker C#/PicoGK em si é o processo verdadeiramente
separado, invocado via subprocess a partir daqui. Também recupera jobs órfãos (heartbeat
expirado) a cada ciclo.
"""
from __future__ import annotations

import argparse
import os
import socket
import time
import uuid
from pathlib import Path

from biomatcad_api.config import get_settings
from biomatcad_api.db import SessionLocal
from biomatcad_api.services.geometry_job_service import (
    claim_next_queued_job,
    dispatch_job,
    recover_orphaned_jobs,
)
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import get_default_worker_client

REPO_ROOT = Path(__file__).resolve().parents[3]


def _make_dispatcher_id() -> str:
    """Identificador único deste processo dispatcher (item 6: "identificação do
    dispatcher/worker") -- hostname:pid:uuid-curto, suficiente para diagnosticar qual processo
    reivindicou qual job em ambientes com múltiplos dispatchers."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def process_queued_jobs(limit: int | None = None, dispatcher_id: str | None = None) -> int:
    settings = get_settings()
    storage = LocalStorageAdapter(Path(settings.artifact_storage_dir))
    worker_client = get_default_worker_client(REPO_ROOT)
    dispatcher_id = dispatcher_id or _make_dispatcher_id()
    db = SessionLocal()
    processed = 0
    try:
        recovered = recover_orphaned_jobs(db)
        if recovered:
            print(f"Recuperados {len(recovered)} job(s) órfão(s): {recovered}")
        while limit is None or processed < limit:
            job = claim_next_queued_job(db, dispatcher_id=dispatcher_id)
            if job is None:
                break
            dispatch_job(
                db,
                job_id=job.id,
                worker_client=worker_client,
                storage=storage,
                output_dir=Path(settings.artifact_storage_dir) / "_work" / job.id,
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

    dispatcher_id = _make_dispatcher_id()
    print(f"Dispatcher ID: {dispatcher_id}")

    if args.once:
        n = process_queued_jobs(limit=args.limit, dispatcher_id=dispatcher_id)
        print(f"Processados {n} job(s).")
        return

    print("Dispatcher geométrico iniciado (Ctrl+C para parar).")
    while True:
        n = process_queued_jobs(limit=args.limit, dispatcher_id=dispatcher_id)
        if n:
            print(f"Processados {n} job(s).")
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
