"""Testes de regressão (rodada Voronoi, correção pós-auditoria da execução Windows
20260806-112714) para scripts/verify_full_pipeline_sha256.py: o defeito real encontrado foi que
o timeout externo padrão deste gate (--timeout-seconds, default 300.0s) podia ser MENOR OU
IGUAL ao orçamento interno do worker (max_duration_seconds + STARTUP_OVERHEAD_SECONDS) para
receitas com max_duration_seconds=300 (ex.: block-voronoi-final-v1, modo final) -- nesse caso o
próprio script podia matar seu processo filho (o dispatcher) antes do watchdog interno do
worker (worker_client.py) ter chance de agir, e um Popen.kill() comum não mata o neto
(dotnet.exe real), deixando-o órfão -- explicação mais provável para a cascata de falhas
observada em TODAS as invocações subsequentes daquela rodada real.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_full_pipeline_sha256 as gate


def test_timeout_efetivo_nunca_e_menor_que_o_orcamento_interno_do_worker():
    # Receita "pesada" (modo final, max_duration_seconds=300) -- o cenário real que causou o
    # bug: orçamento interno do worker = 300 + 30 (STARTUP_OVERHEAD_SECONDS espelhado) = 330s,
    # maior que o --timeout-seconds default de 300.0s usado na rodada real.
    recipe_body = {"compute_limits": {"max_duration_seconds": 300}}
    effective = gate.compute_effective_gate_timeout_seconds(recipe_body, requested_timeout_seconds=300.0)

    worker_internal_deadline = 300 + gate._WORKER_STARTUP_OVERHEAD_SECONDS_MIRROR
    assert effective > worker_internal_deadline, (
        "o timeout efetivo do gate precisa ser ESTRITAMENTE maior que o deadline interno do "
        "worker, nunca igual nem menor -- essa é exatamente a condição de corrida que causou "
        "a cascata de falhas na rodada 20260806-112714"
    )


def test_timeout_efetivo_respeita_override_explicito_maior_do_usuario():
    recipe_body = {"compute_limits": {"max_duration_seconds": 30}}
    # Usuário pediu um timeout bem maior que o necessário -- o cálculo nunca deve reduzi-lo.
    effective = gate.compute_effective_gate_timeout_seconds(recipe_body, requested_timeout_seconds=900.0)
    assert effective == 900.0


def test_timeout_efetivo_para_receita_leve_preview_usa_o_default_pedido():
    # Receita leve (preview, max_duration_seconds=30): orçamento interno do worker = 60s, bem
    # abaixo do default de 300s -- o timeout efetivo deve continuar sendo o default (nenhuma
    # regressão para o caso comum, já correto antes desta correção).
    recipe_body = {"compute_limits": {"max_duration_seconds": 30}}
    effective = gate.compute_effective_gate_timeout_seconds(recipe_body, requested_timeout_seconds=300.0)
    assert effective == 300.0


def test_timeout_efetivo_usa_fallback_conservador_quando_compute_limits_ausente():
    # Sem compute_limits, o fallback (300s, mesmo default de worker_client.py) é tratado como
    # o pior caso possível -- o cálculo aplica a mesma margem de segurança, resultando em um
    # timeout efetivo MAIOR que o requested_timeout_seconds pedido (comportamento defensivo
    # correto: nunca assume que uma receita sem compute_limits é leve).
    effective = gate.compute_effective_gate_timeout_seconds({}, requested_timeout_seconds=300.0)
    assert effective == 300 + gate._WORKER_STARTUP_OVERHEAD_SECONDS_MIRROR + gate._GATE_TIMEOUT_SAFETY_MARGIN_SECONDS


def test_kill_process_tree_best_effort_mata_pai_e_filho_e_confirma(tmp_path):
    marker = tmp_path / "child_pid.txt"
    child_script = tmp_path / "spawn_child_and_sleep.py"
    child_script.write_text(
        "import subprocess, sys, time\n"
        f"marker = {str(marker)!r}\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "with open(marker, 'w') as f:\n"
        "    f.write(str(child.pid))\n"
        "time.sleep(300)\n",
        encoding="utf-8",
    )
    parent = subprocess.Popen([sys.executable, str(child_script)])

    import time as _time

    deadline = _time.monotonic() + 5.0
    while not marker.exists() and _time.monotonic() < deadline:
        _time.sleep(0.05)
    assert marker.exists()
    child_pid = int(marker.read_text().strip())

    assert psutil.pid_exists(parent.pid)
    assert psutil.pid_exists(child_pid)

    confirmed = gate._kill_process_tree_best_effort(parent.pid)

    assert confirmed is True
    assert not psutil.pid_exists(parent.pid)
    assert not psutil.pid_exists(child_pid)
    parent.wait(timeout=5)
