#!/usr/bin/env python3
"""Dispatcher de jobs geometricos -- processo separado da API (Incremento 2.1, item 4;
Incremento 2.1.1, item 6; Incremento 2.2, secao 3: modo continuo executavel).

Consome a fila via claim_next_queued_job() (SELECT ... FOR UPDATE SKIP LOCKED, atomico -- dois
dispatchers concorrentes nunca reivindicam o mesmo job) e chama dispatch_job() para cada job ja
reivindicado. Roda como um processo Python distinto (`python scripts/geometry_dispatcher.py`),
nunca dentro do processo uvicorn da API -- satisfaz o requisito explicito de que o processo
geometrico seja separado da API. O worker C#/PicoGK em si e o processo verdadeiramente
separado, invocado via subprocess a partir daqui. Tambem recupera jobs orfaos (heartbeat
expirado) a cada ciclo.

Incremento 2.2 (secao 3, "dispatcher continuo") acrescenta ao modo `--once` ja existente
(inalterado, usado por scripts/verify_full_pipeline_sha256.py) um modo continuo com:

- backoff quando a fila esta vazia (poll_interval cresce geometricamente ate um teto quando
  ciclos consecutivos nao encontram nenhum job, e volta ao valor base assim que um job e
  encontrado) -- evita busy loop e reduz carga ociosa no Postgres;
- shutdown gracioso via SIGINT/SIGTERM: o sinal so marca uma flag; o dispatcher nunca aborta um
  job em andamento no meio -- termina o ciclo de claim/dispatch atual (dispatch_job ja e
  bloqueante e teuconecta o cancel_check real) e so entao sai, escrevendo estado "stopped" no
  arquivo de status;
- logs estruturados (uma linha JSON por evento em stdout), para consumo por um painel de
  observabilidade ou pelo launcher, sem depender de parsing de texto livre;
- um arquivo de status (status_file, JSON) atualizado a cada ciclo com dispatcher_id, pid,
  started_at, last_poll_at, state, jobs_processed_total e o poll_interval efetivo atual --
  permite que um processo externo (o launcher Windows, por exemplo) verifique liveness sem
  depender só de "o processo do SO ainda existe" (um dispatcher pode estar vivo mas travado);
  o mesmo padrão de "heartbeat com limite de atraso" já usado para jobs órfãos.

Incremento 2.2 (seção 2, integração com o launcher Windows) acrescenta mais dois mecanismos:

- campo "phase" no status file ("idle" | "processing"), atualizado com escrita IMEDIATA (sem o
  throttle do heartbeat periódico) no exato momento em que um job é reivindicado e no momento em
  que termina -- permite ao launcher distinguir "starting/idle/processing/stopping/stopped"
  (estado pedido explicitamente na seção 2), não apenas "rodando ou não";
- arquivo de pedido de parada (stop_file): além de SIGINT/SIGTERM, o loop também aceita um
  pedido de shutdown gracioso via a simples EXISTÊNCIA de um arquivo sentinela no disco. Isso
  existe porque um launcher .NET no Windows não tem uma forma simples e confiável de entregar
  SIGINT/Ctrl+C a um processo filho iniciado sem console próprio (CreateNoWindow=true) --
  GenerateConsoleCtrlEvent exige o mesmo grupo de console, o que não se aplica aqui. Um arquivo
  sentinela funciona identicamente em qualquer SO e é trivial de testar.
"""
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
from biomatcad_api.services.geometry_job_service import (
    claim_next_queued_job,
    dispatch_job,
    recover_orphaned_jobs,
)
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import get_default_worker_client

REPO_ROOT = Path(__file__).resolve().parents[3]

# Defaults do backoff (secao 3: "backoff quando a fila estiver vazia"). Nao sao parametros de
# linha de comando porque o comportamento -- crescer geometricamente e nunca ultrapassar um
# teto -- e uma politica interna, nao algo que o operador deva precisar ajustar no dia a dia.
BACKOFF_MULTIPLIER = 1.5
BACKOFF_MAX_SECONDS = 30.0

# Intervalo minimo entre escritas do arquivo de status, para nao gerar I/O de disco a cada
# iteracao do loop quando o poll_interval efetivo for muito curto.
STATUS_FILE_MIN_WRITE_INTERVAL_SECONDS = 1.0


def _make_dispatcher_id() -> str:
    """Identificador unico deste processo dispatcher (item 6: "identificacao do
    dispatcher/worker") -- hostname:pid:uuid-curto, suficiente para diagnosticar qual processo
    reivindicou qual job em ambientes com multiplos dispatchers."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(event: str, **fields: Any) -> None:
    """Log estruturado (uma linha JSON por evento) em stdout -- Incremento 2.2, secao 3 ("logs
    estruturados"). Nunca inclui segredos: quem chama e responsavel por não passar
    connection strings completas, senhas ou tokens em `fields`."""
    record = {"ts": _utcnow_iso(), "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False), flush=True)


class GracefulShutdown:
    """Handler de SIGINT/SIGTERM que apenas marca uma flag (Incremento 2.2, secao 3: "shutdown
    gracioso"). O loop principal checa `requested` somente ENTRE ciclos de claim/dispatch --
    nunca interrompe um job que ja esta em `dispatch_job()` (que e bloqueante e so retorna
    quando o worker termina, e' cancelado, ou falha). Isso evita deixar um job em estado
    inconsistente por causa de um shutdown mal-cronometrado; na pior das hipoteses, um job
    "running" cujo processo morreu de fato sera recuperado pelo proprio
    `recover_orphaned_jobs()` na proxima subida de um dispatcher."""

    def __init__(self) -> None:
        self.requested = False
        self._signal_received: int | None = None

    def install(self) -> None:
        signal.signal(signal.SIGINT, self._handle)
        try:
            signal.signal(signal.SIGTERM, self._handle)
        except (ValueError, AttributeError):
            # SIGTERM pode não existir/ser configuravel em algumas plataformas (ex.: threads
            # secundárias no Windows) -- SIGINT sozinho já cobre Ctrl+C, o caso principal.
            pass

    def _handle(self, signum: int, frame: object) -> None:  # pragma: no cover - trivial
        self._signal_received = signum
        self.requested = True


def _status_file_path(settings_artifact_storage_dir: str) -> Path:
    return Path(settings_artifact_storage_dir) / "_dispatcher" / "status.json"


def write_status_file(
    status_file: Path,
    *,
    dispatcher_id: str,
    state: str,
    started_at: str,
    jobs_processed_total: int,
    current_poll_interval: float,
    last_job_id: str | None,
    phase: str = "idle",
) -> None:
    """Escreve o snapshot de status do dispatcher em disco (Incremento 2.2, secao 3 e 7:
    observabilidade de liveness sem depender apenas do processo do SO). Escrita atomica
    (arquivo temporario + rename) para nunca deixar um leitor externo ler um JSON parcial.

    `phase` distingue "idle" (loop rodando, nenhum job sendo processado agora) de "processing"
    (dentro de dispatch_job() para last_job_id neste exato momento) -- ver `run_continuous`."""
    status_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dispatcher_id": dispatcher_id,
        "pid": os.getpid(),
        "state": state,
        "phase": phase,
        "started_at": started_at,
        "last_poll_at": _utcnow_iso(),
        "jobs_processed_total": jobs_processed_total,
        "current_poll_interval_seconds": current_poll_interval,
        "last_job_id": last_job_id,
    }
    tmp_path = status_file.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, status_file)


def process_queued_jobs(
    limit: int | None = None,
    dispatcher_id: str | None = None,
    *,
    on_phase_change: Any = None,
) -> int:
    """`on_phase_change`, se fornecido, é chamado como `on_phase_change("processing", job_id)`
    logo após um job ser reivindicado e `on_phase_change("idle", job_id)` logo depois que
    `dispatch_job` retorna (sucesso, falha ou cancelamento) -- usado por `run_continuous` para
    manter o status file atualizado em tempo real, sem esperar o próximo ciclo de heartbeat
    (Incremento 2.2, seção 2: estados "processing"/"idle" observáveis pelo launcher)."""
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
            if on_phase_change is not None:
                on_phase_change("processing", job.id)
            try:
                dispatch_job(
                    db,
                    job_id=job.id,
                    worker_client=worker_client,
                    storage=storage,
                    output_dir=Path(settings.artifact_storage_dir) / "_work" / job.id,
                    repo_root=REPO_ROOT,
                )
            finally:
                if on_phase_change is not None:
                    on_phase_change("idle", job.id)
            processed += 1
    finally:
        db.close()
    return processed


def _stop_requested(shutdown: GracefulShutdown, stop_file: Path | None) -> bool:
    """OR de duas fontes independentes de pedido de shutdown gracioso: sinal do SO
    (SIGINT/SIGTERM, via `shutdown.requested`) OU a simples existência de `stop_file` no disco
    -- o mecanismo que o launcher Windows usa, já que entregar um sinal POSIX real a um processo
    filho sem console próprio não é confiável no Windows (ver docstring do módulo)."""
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
    """Loop principal do modo continuo (Incremento 2.2, secao 3; stop_file: secao 2). Extraido
    de `main()` para ser testavel sem precisar rodar um processo real: os testes injetam
    `max_iterations` (para terminar deterministicamente em vez de `while True`), `sleep_fn`
    (para não esperar de verdade) e um `GracefulShutdown` já com `requested=True` programado
    para disparar após N iterações, simulando Ctrl+C -- ou um `stop_file` que os testes criam
    em disco no meio da execução, simulando o launcher pedindo parada.

    Retorna o total de jobs processados na chamada (usado pelos testes para verificar
    comportamento).
    """
    started_at = _utcnow_iso()
    poll_interval = base_poll_interval
    consecutive_empty_cycles = 0
    jobs_processed_total = 0
    last_job_id: str | None = None
    last_status_write = 0.0
    iteration = 0

    def write_now(*, state: str, phase: str) -> None:
        write_status_file(
            status_file,
            dispatcher_id=dispatcher_id,
            state=state,
            started_at=started_at,
            jobs_processed_total=jobs_processed_total,
            current_poll_interval=poll_interval,
            last_job_id=last_job_id,
            phase=phase,
        )

    def on_phase_change(phase: str, job_id: str) -> None:
        nonlocal last_job_id
        last_job_id = job_id
        log_event("job_phase_changed", dispatcher_id=dispatcher_id, job_id=job_id, phase=phase)
        # Escrita IMEDIATA (não sujeita ao throttle de heartbeat) -- transições de fase são
        # eventos raros e importantes para quem está observando o status file de fora.
        write_now(state="running", phase=phase)

    log_event("dispatcher_started", dispatcher_id=dispatcher_id, base_poll_interval=base_poll_interval)

    while not _stop_requested(shutdown, stop_file):
        if max_iterations is not None and iteration >= max_iterations:
            break
        iteration += 1

        # Resiliencia a indisponibilidade TEMPORARIA do banco (Incremento 2.2, Fase D):
        # process_queued_jobs() faz consultas reais (claim_next_queued_job,
        # recover_orphaned_jobs) que podem falhar com uma excecao de conexao/protocolo real se
        # o Postgres estiver temporariamente fora do ar (reinicio, blip de rede). Antes desta
        # correcao, essa excecao NAO era capturada aqui -- propagava e derrubava o processo
        # inteiro do dispatcher continuo, exigindo um supervisor externo para reiniciar. Agora
        # o ciclo trata isso como um ciclo vazio (mesmo backoff geometrico), loga o erro e
        # CONTINUA tentando no proximo ciclo -- o dispatcher sobrevive a uma indisponibilidade
        # transitoria sem intervencao externa, assim que o banco volta a responder.
        try:
            n = process_queued_jobs(
                limit=limit_per_cycle,
                dispatcher_id=dispatcher_id,
                on_phase_change=on_phase_change,
            )
        except DBAPIError as exc:
            n = 0
            log_event(
                "database_temporarily_unavailable",
                dispatcher_id=dispatcher_id,
                error=str(exc.orig) if exc.orig is not None else str(exc),
            )
        jobs_processed_total += n

        if n > 0:
            consecutive_empty_cycles = 0
            poll_interval = base_poll_interval
            log_event("jobs_processed", dispatcher_id=dispatcher_id, count=n, poll_interval=poll_interval)
        else:
            consecutive_empty_cycles += 1
            poll_interval = min(
                base_poll_interval * (BACKOFF_MULTIPLIER ** consecutive_empty_cycles),
                BACKOFF_MAX_SECONDS,
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

    log_event("dispatcher_stopping", dispatcher_id=dispatcher_id, jobs_processed_total=jobs_processed_total)
    write_now(state="stopped", phase="idle")
    log_event("dispatcher_stopped", dispatcher_id=dispatcher_id, jobs_processed_total=jobs_processed_total)
    return jobs_processed_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatcher de jobs geométricos BioMatCAD Nexus.")
    parser.add_argument("--once", action="store_true", help="Processa a fila uma vez e sai.")
    parser.add_argument("--limit", type=int, default=None, help="Número máximo de jobs a processar por ciclo.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Segundos entre polls (base do backoff no modo contínuo).")
    parser.add_argument(
        "--status-file",
        type=str,
        default=None,
        help="Caminho do arquivo de status JSON (padrão: <artifact_storage_dir>/_dispatcher/status.json).",
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default=None,
        help=(
            "Caminho de um arquivo sentinela: se existir, o dispatcher inicia o shutdown "
            "gracioso (mesmo efeito de SIGINT/SIGTERM). Usado pelo launcher Windows, que não "
            "tem uma forma confiável de entregar Ctrl+C a um processo filho sem console."
        ),
    )
    args = parser.parse_args()

    dispatcher_id = _make_dispatcher_id()
    # flush=True (correção real, auditoria da rodada Voronoi/execução Windows
    # 20260806-112714): quando stdout é redirecionado para um pipe (subprocess.Popen(...,
    # stdout=subprocess.PIPE), caso de verify_full_pipeline_sha256.py), o Python usa buffer de
    # BLOCO por padrão, não de linha -- se este processo for morto (kill/TerminateProcess)
    # antes de sair normalmente, qualquer print() sem flush=True explícito nunca chega ao pipe,
    # mesmo que a linha já tivesse sido "impressa" do ponto de vista do código. Isso apagava
    # justamente o diagnóstico ("Dispatcher ID: ...") que provaria até onde o processo chegou
    # antes de travar/ser morto -- log_event() já usava flush=True (linha correspondente
    # abaixo), só faltava aqui.
    print(f"Dispatcher ID: {dispatcher_id}", flush=True)

    if args.once:
        # Modo usado por scripts/verify_full_pipeline_sha256.py e por operadores que querem
        # processar a fila manualmente uma vez -- comportamento inalterado desde o Incremento
        # 2.1.1, sem log estruturado nem status file (chamada curta, sem necessidade de
        # observabilidade contínua).
        n = process_queued_jobs(limit=args.limit, dispatcher_id=dispatcher_id)
        print(f"Processados {n} job(s).", flush=True)
        return

    settings = get_settings()
    status_file = Path(args.status_file) if args.status_file else _status_file_path(settings.artifact_storage_dir)

    shutdown = GracefulShutdown()
    shutdown.install()

    stop_file = Path(args.stop_file) if args.stop_file else None

    print("Dispatcher geométrico iniciado em modo contínuo (Ctrl+C para parar com segurança).")
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
