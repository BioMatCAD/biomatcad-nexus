"""Testes do modo continuo do dispatcher (Incremento 2.2, secao 3 e 9).

Estes testes exercitam `run_continuous()` diretamente, em processo, substituindo
`process_queued_jobs` por um dublê controlado -- não sobem um Postgres real nem um worker
PicoGK real (isso já é coberto pelos testes de concorrência/orquestração existentes em
`test_geometry_job_concurrency.py` e `test_geometry_job_orchestration.py`). O que se testa
aqui é o comportamento do LOOP em si: backoff, shutdown gracioso, status file e logs
estruturados -- que são específicos deste módulo e não tinham nenhuma cobertura antes do
Incremento 2.2.
"""
from __future__ import annotations

import json

import pytest

import scripts.geometry_dispatcher as dispatcher_mod
from scripts.geometry_dispatcher import (
    BACKOFF_MAX_SECONDS,
    BACKOFF_MULTIPLIER,
    GracefulShutdown,
    log_event,
    run_continuous,
    write_status_file,
)


class _FakeClock:
    """Sleep dublê que não espera de verdade e permite instrumentar o loop (ex.: disparar
    shutdown depois de N chamadas, simulando um sinal chegando durante o "sleep")."""

    def __init__(self, on_sleep=None) -> None:
        self.calls: list[float] = []
        self._on_sleep = on_sleep

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._on_sleep is not None:
            self._on_sleep(len(self.calls))


def test_backoff_grows_geometrically_on_consecutive_empty_cycles(monkeypatch, tmp_path):
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 0)
    clock = _FakeClock()

    run_continuous(
        dispatcher_id="test-dispatcher",
        base_poll_interval=1.0,
        limit_per_cycle=None,
        status_file=tmp_path / "status.json",
        shutdown=GracefulShutdown(),
        max_iterations=4,
        sleep_fn=clock,
    )

    assert len(clock.calls) == 4
    # Cresce geometricamente: 1*1.5^1, 1*1.5^2, 1*1.5^3, 1*1.5^4 (todos abaixo do teto).
    expected = [min(1.0 * (BACKOFF_MULTIPLIER**i), BACKOFF_MAX_SECONDS) for i in range(1, 5)]
    assert clock.calls == pytest.approx(expected)
    assert clock.calls == sorted(clock.calls), "backoff deve ser monotonicamente crescente enquanto a fila estiver vazia"


def test_backoff_resets_to_base_interval_after_a_job_is_found(monkeypatch, tmp_path):
    # Ciclos: vazio, vazio, ACHOU 1 job, vazio de novo.
    counts = iter([0, 0, 1, 0])
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: next(counts))
    clock = _FakeClock()

    run_continuous(
        dispatcher_id="test-dispatcher",
        base_poll_interval=2.0,
        limit_per_cycle=None,
        status_file=tmp_path / "status.json",
        shutdown=GracefulShutdown(),
        max_iterations=4,
        sleep_fn=clock,
    )

    assert len(clock.calls) == 4
    # ciclo 1 (vazio): 2*1.5^1; ciclo 2 (vazio): 2*1.5^2; ciclo 3 (achou job): reset -> 2.0 base;
    # ciclo 4 (vazio de novo): volta a crescer a partir da base -> 2*1.5^1.
    assert clock.calls[0] == pytest.approx(2.0 * 1.5)
    assert clock.calls[1] == pytest.approx(2.0 * 1.5**2)
    assert clock.calls[2] == pytest.approx(2.0), "poll_interval deve voltar ao valor base assim que um job é encontrado"
    assert clock.calls[3] == pytest.approx(2.0 * 1.5)


def test_backoff_never_exceeds_configured_maximum(monkeypatch, tmp_path):
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 0)
    clock = _FakeClock()

    run_continuous(
        dispatcher_id="test-dispatcher",
        base_poll_interval=5.0,
        limit_per_cycle=None,
        status_file=tmp_path / "status.json",
        shutdown=GracefulShutdown(),
        max_iterations=20,
        sleep_fn=clock,
    )

    assert all(c <= BACKOFF_MAX_SECONDS for c in clock.calls)
    assert clock.calls[-1] == pytest.approx(BACKOFF_MAX_SECONDS), "após iterações suficientes, o backoff deve saturar no teto"


def test_graceful_shutdown_stops_between_cycles_and_writes_stopped_status(monkeypatch, tmp_path):
    """Simula um Ctrl+C chegando durante o "sleep" do 2º ciclo: o loop não deve iniciar um
    3º ciclo de claim/dispatch, e o status file final deve dizer state=stopped."""
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 0)
    shutdown = GracefulShutdown()

    def on_sleep(call_number: int) -> None:
        if call_number == 2:
            shutdown.requested = True

    clock = _FakeClock(on_sleep=on_sleep)
    status_file = tmp_path / "status.json"

    total = run_continuous(
        dispatcher_id="test-dispatcher",
        base_poll_interval=1.0,
        limit_per_cycle=None,
        status_file=status_file,
        shutdown=shutdown,
        max_iterations=None,  # sem limite artificial -- só o shutdown deve parar o loop
        sleep_fn=clock,
    )

    assert total == 0
    assert len(clock.calls) == 2, "não deve haver um 3º ciclo depois que o shutdown foi sinalizado durante o 2º sleep"
    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["state"] == "stopped"


def test_status_file_contains_expected_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 1)
    status_file = tmp_path / "sub" / "status.json"

    run_continuous(
        dispatcher_id="dispatcher-abc",
        base_poll_interval=3.0,
        limit_per_cycle=None,
        status_file=status_file,
        shutdown=GracefulShutdown(),
        max_iterations=1,
        sleep_fn=lambda seconds: None,
    )

    assert status_file.exists(), "write_status_file deve criar o diretório pai automaticamente"
    payload = json.loads(status_file.read_text(encoding="utf-8"))
    for key in (
        "dispatcher_id",
        "pid",
        "state",
        "started_at",
        "last_poll_at",
        "jobs_processed_total",
        "current_poll_interval_seconds",
        "last_job_id",
    ):
        assert key in payload, f"campo {key} ausente no status file"
    assert payload["dispatcher_id"] == "dispatcher-abc"
    assert payload["jobs_processed_total"] == 1


def test_run_continuous_returns_total_jobs_processed_across_cycles(monkeypatch, tmp_path):
    counts = iter([2, 0, 3, 1])
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: next(counts))

    total = run_continuous(
        dispatcher_id="test-dispatcher",
        base_poll_interval=0.01,
        limit_per_cycle=None,
        status_file=tmp_path / "status.json",
        shutdown=GracefulShutdown(),
        max_iterations=4,
        sleep_fn=lambda seconds: None,
    )

    assert total == 2 + 0 + 3 + 1


def test_log_event_emits_a_single_valid_json_line(capsys):
    log_event("evento_de_teste", dispatcher_id="d1", count=3)
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["event"] == "evento_de_teste"
    assert payload["dispatcher_id"] == "d1"
    assert payload["count"] == 3
    assert "ts" in payload


def test_write_status_file_is_atomic_no_partial_json_left_behind(tmp_path):
    status_file = tmp_path / "status.json"
    write_status_file(
        status_file,
        dispatcher_id="d1",
        state="running",
        started_at="2026-01-01T00:00:00+00:00",
        jobs_processed_total=0,
        current_poll_interval=5.0,
        last_job_id=None,
    )
    assert status_file.exists()
    assert not status_file.with_suffix(".tmp").exists(), "arquivo temporário não deve sobrar após o rename atômico"
    json.loads(status_file.read_text(encoding="utf-8"))  # não deve levantar erro de parsing


def test_graceful_shutdown_flag_starts_false_and_signal_handler_sets_it():
    shutdown = GracefulShutdown()
    assert shutdown.requested is False
    shutdown._handle(2, None)  # simula SIGINT sem de fato enviar um sinal ao processo de teste
    assert shutdown.requested is True


def test_status_file_phase_defaults_to_idle_when_no_job_processed(monkeypatch, tmp_path):
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 0)
    status_file = tmp_path / "status.json"

    run_continuous(
        dispatcher_id="d1",
        base_poll_interval=1.0,
        limit_per_cycle=None,
        status_file=status_file,
        shutdown=GracefulShutdown(),
        max_iterations=1,
        sleep_fn=lambda seconds: None,
    )

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["phase"] == "idle"


def test_on_phase_change_writes_processing_then_idle_immediately(monkeypatch, tmp_path):
    """Simula o dublê de process_queued_jobs invocando on_phase_change como o real faria:
    "processing" logo que reivindica um job, "idle" logo que termina -- e confere que cada
    chamada já reflete no status file na hora (não espera o próximo ciclo)."""
    observed_phases: list[str] = []
    status_file = tmp_path / "status.json"

    def fake_process_queued_jobs(limit, dispatcher_id, on_phase_change=None):
        if on_phase_change is not None:
            on_phase_change("processing", "job-123")
            observed_phases.append(json.loads(status_file.read_text(encoding="utf-8"))["phase"])
            on_phase_change("idle", "job-123")
            observed_phases.append(json.loads(status_file.read_text(encoding="utf-8"))["phase"])
        return 1

    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", fake_process_queued_jobs)

    run_continuous(
        dispatcher_id="d1",
        base_poll_interval=1.0,
        limit_per_cycle=None,
        status_file=status_file,
        shutdown=GracefulShutdown(),
        max_iterations=1,
        sleep_fn=lambda seconds: None,
    )

    assert observed_phases == ["processing", "idle"]
    final_payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert final_payload["last_job_id"] == "job-123"


def test_stop_file_triggers_graceful_shutdown_like_a_signal(monkeypatch, tmp_path):
    monkeypatch.setattr(dispatcher_mod, "process_queued_jobs", lambda limit, dispatcher_id, on_phase_change=None: 0)
    status_file = tmp_path / "status.json"
    stop_file = tmp_path / "stop_requested"

    def on_sleep(_seconds):
        stop_file.write_text("stop", encoding="utf-8")

    total = run_continuous(
        dispatcher_id="d1",
        base_poll_interval=1.0,
        limit_per_cycle=None,
        status_file=status_file,
        shutdown=GracefulShutdown(),
        stop_file=stop_file,
        max_iterations=None,
        sleep_fn=on_sleep,
    )

    assert total == 0
    payload = json.loads(status_file.read_text(encoding="utf-8"))
    assert payload["state"] == "stopped"


def test_stop_requested_helper_checks_both_signal_and_file(tmp_path):
    from scripts.geometry_dispatcher import _stop_requested

    stop_file = tmp_path / "stop_requested"
    shutdown = GracefulShutdown()

    assert _stop_requested(shutdown, None) is False
    assert _stop_requested(shutdown, stop_file) is False  # arquivo ainda não existe

    stop_file.write_text("x", encoding="utf-8")
    assert _stop_requested(shutdown, stop_file) is True

    stop_file.unlink()
    shutdown.requested = True
    assert _stop_requested(shutdown, None) is True
