#!/usr/bin/env python3
"""Dispatcher da fila de ingestão científica -- processo separado da API (Incremento 2.3,
Rodada 2, Fase D). Mirroa deliberadamente os padrões de `scripts/geometry_dispatcher.py`
(claim atômico, backoff geométrico quando a fila está vazia, shutdown gracioso via
SIGINT/SIGTERM ou arquivo sentinela, logs estruturados em JSON, arquivo de status) -- mas é um
processo INDEPENDENTE: nunca compartilha estado em memória com o dispatcher geométrico, e uma
falha em um nunca derruba o outro.

Consome a fila via `claim_next_queued_request()` (SELECT ... FOR UPDATE SKIP LOCKED -- dois
dispatchers concorrentes nunca reivindicam a mesma solicitação) e chama `process_request()`
para cada solicitação já reivindicada. Também recupera solicitações órfãs (heartbeat expirado)
a cada ciclo. Nunca faz varredura/importação em massa -- cada solicitação já contém a lista
EXPLÍCITA de identificadores (CIDs) definida no momento da submissão (ver
services/scientific_ingestion_service.py::submit_ingestion_request)."""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import DBAPIError

from biomatcad_api.config import get_settings
from biomatcad_api.db import SessionLocal
from biomatcad_api.services.scientific_ingestion_service import (
    claim_next_queued_request,
    process_request,
    recover_orphaned_requests,
)

BACKOFF_MULTIPLIER = 1.5
BACKOFF_MAX_SECONDS = 30.0
STATUS_FILE_MIN_WRITE_INTERVAL_SECONDS = 1.0


def _make_dispatcher_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, **fields: Any) -> None:
    """Log estruturado (uma linha JSON por evento) em stdout. Nunca inclui segredos -- quem
    chama é responsável por não passar connection strings completas, tokens, ou payloads brutos
    de terceiros em `fields` (apenas contadores/IDs/identificadores estruturais)."""
    record = {"ts": _utcnow_iso(), "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False), flush=True)


class GracefulShutdown:
    """Handler de SIGINT/SIGTERM que apenas marca uma flag -- o loop principal só checa
    `requested` ENTRE ciclos de claim/process, nunca no meio de `process_request()` (que já
    verifica `cancel_requested_at` entre cada CID, cooperativamente)."""

    def __init__(self) -> None:
        self.requested = False

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._handle)
        try:
            signal.signal(signal.SIGTERM, self._handle)
        except (ValueError, AttributeError):
            pass

    def _handle(self, signum: int, frame: object) -> None:  # pragma: no cover - trivial
        self.requested = True


def _status_file_path(artifact_storage_dir: str) -> Path:
    return Path(artifact_storage_dir) / "_scientific_ingestion_dispatcher" / "status.json"


def write_status_file(
    status_file: Path,
    *,
    dispatcher_id: str,
    state: str,
    started_at: str,
    requests_processed_total: int,
    current_poll_interval: float,
    last_request_id: str | None,
    phase: str = "idle",
) -> None:
    """Escrita atômica (arquivo temporário + rename) -- nunca deixa um leitor externo ler um
    JSON parcial."""
    status_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dispatcher_id": dispatcher_id,
        "pid": os.getpid(),
        "state": state,
        "phase": phase,
        "started_at": started_at,
        "last_poll_at": _utcnow_iso(),
        "requests_processed_total": requests_processed_total,
        "current_poll_interval_seconds": current_poll_interval,
        "last_request_id": last_request_id,
    }
    tmp_path = status_file.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, status_file)


def process_queued_requests(
    limit: int | None = None,
    dispatcher_id: str | None = None,
    *,
    on_phase_change: Any = None,
) -> int:
    """`on_phase_change`, se fornecido, é chamado como `on_phase_change("processing", req_id)`
    logo após uma solicitação ser reivindicada e `on_phase_change("idle", req_id)` logo depois
    que `process_request` retorna."""
    dispatcher_id = dispatcher_id or _make_dispatcher_id()
    db = SessionLocal()
    processed = 0
    try:
        recovered = recover_orphaned_requests(db)
        if recovered:
            print(f"Recuperada(s) {len(recovered)} solicitação(ões) órfã(s): {recovered}")
        while limit is None or processed < limit:
            request = claim_next_queued_request(db, dispatcher_id=dispatcher_id)
            if request is None:
                break
            if on_phase_change is not None:
                on_phase_change("processing", request.id)
            try:
                process_request(db, request=request)
            finally:
                if on_phase_change is not None:
                    on_phase_change("idle", request.id)
            processed += 1
    finally:
        db.close()
    return processed


def _stop_requested(shutdown: GracefulShutdown, stop_file: Path | None) -> bool:
    if shutdown.requested:
        return True
    return stop_file is not None and stop_file.exists()


def run_continuous(
    *,
    dispatcher_id: str,
    base_poll_interval: float,
    limit_per_cycle: int | None,
    status_file: Path,
    shutdown: GracefulShutdown,
    stop_file: Path | None = None,
    max_iterations: int | None = None,
    sleep_fn: Any = time.sleep,
) -> int:
    """Loop principal do modo contínuo. `max_iterations`/`sleep_fn` existem para tornar isto
    testável sem um processo real (mesmo padrão de `geometry_dispatcher.py::run_continuous`)."""
    started_at = _utcnow_iso()
    poll_interval = base_poll_interval
    consecutive_empty_cycles = 0
    requests_processed_total = 0
    last_request_id: str | None = None
    last_status_write = 0.0
    iteration = 0

    def write_now(*, state: str, phase: str) -> None:
        write_status_file(
            status_file,
            dispatcher_id=dispatcher_id,
            state=state,
            started_at=started_at,
            requests_processed_total=requests_processed_total,
            current_poll_interval=poll_interval,
            last_request_id=last_request_id,
            phase=phase,
        )

    def on_phase_change(phase: str, request_id: str) -> None:
        nonlocal last_request_id
        last_request_id = request_id
        log_event("request_phase_changed", dispatcher_id=dispatcher_id, request_id=request_id, phase=phase)
        write_now(state="running", phase=phase)

    log_event("dispatcher_started", dispatcher_id=dispatcher_id, base_poll_interval=base_poll_interval)

    while not _stop_requested(shutdown, stop_file):
        if max_iterations is not None and iteration >= max_iterations:
            break
        iteration += 1

        try:
            n = process_queued_requests(
                limit=limit_per_cycle, dispatcher_id=dispatcher_id, on_phase_change=on_phase_change
            )
        except DBAPIError as exc:
            n = 0
            log_event(
                "database_temporarily_unavailable",
                dispatcher_id=dispatcher_id,
                error=str(exc.orig) if exc.orig is not None else str(exc),
            )
        requests_processed_total += n

        if n > 0:
            consecutive_empty_cycles = 0
            poll_interval = base_poll_interval
            log_event("requests_processed", dispatcher_id=dispatcher_id, count=n, poll_interval=poll_interval)
        else:
            consecutive_empty_cycles += 1
            poll_interval = min(
                base_poll_interval * (BACKOFF_MULTIPLIER**consecutive_empty_cycles), BACKOFF_MAX_SECONDS
            )
            log_event(
                "poll_cycle_empty",
                dispatcher_id=dispatcher_id,
                consecutive_empty_cycles=consecutive_empty_cycles,
                poll_interval=poll_interval,
            )

        now_monotonic = time.monotonic()
        if now_monotonic - last_status_write >= STATUS_FILE_MIN_WRITE_INTERVAL_SECONDS:
            write_now(state="running", phase="idle")
            last_status_write = now_monotonic

        if _stop_requested(shutdown, stop_file):
            break
        sleep_fn(poll_interval)

    log_event("dispatcher_stopping", dispatcher_id=dispatcher_id, requests_processed_total=requests_processed_total)
    write_now(state="stopped", phase="idle")
    log_event("dispatcher_stopped", dispatcher_id=dispatcher_id, requests_processed_total=requests_processed_total)
    return requests_processed_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatcher da fila de ingestão científica BioMatCAD Nexus.")
    parser.add_argument("--once", action="store_true", help="Processa a fila uma vez e sai.")
    parser.add_argument("--limit", type=int, default=None, help="Número máximo de solicitações a processar por ciclo.")
    parser.add_argument(
        "--poll-interval", type=float, default=5.0, help="Segundos entre polls (base do backoff no modo contínuo)."
    )
    parser.add_argument("--status-file", type=str, default=None, help="Caminho do arquivo de status JSON.")
    parser.add_argument(
        "--stop-file",
        type=str,
        default=None,
        help="Caminho de um arquivo sentinela: se existir, inicia o shutdown gracioso (mesmo efeito de SIGINT/SIGTERM).",
    )
    args = parser.parse_args()

    dispatcher_id = _make_dispatcher_id()
    print(f"Dispatcher ID: {dispatcher_id}", flush=True)

    if args.once:
        n = process_queued_requests(limit=args.limit, dispatcher_id=dispatcher_id)
        print(f"Processada(s) {n} solicitação(ões).", flush=True)
        return

    settings = get_settings()
    status_file = Path(args.status_file) if args.status_file else _status_file_path(settings.artifact_storage_dir)
    shutdown = GracefulShutdown()
    shutdown.install()
    stop_file = Path(args.stop_file) if args.stop_file else None

    print("Dispatcher de ingestão científica iniciado em modo contínuo (Ctrl+C para parar com segurança).")
    run_continuous(
        dispatcher_id=dispatcher_id,
        base_poll_interval=args.poll_interval,
        limit_per_cycle=args.limit,
        status_file=status_file,
        shutdown=shutdown,
        stop_file=stop_file,
    )


if __name__ == "__main__":
    main()
