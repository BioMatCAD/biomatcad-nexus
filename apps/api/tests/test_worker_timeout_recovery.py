"""Testes de regressão da rodada Voronoi (auditoria da execução Windows real
20260806-112714, ver TEST_EVIDENCE.md): a validação Windows daquela rodada mostrou dois
WORKER_TIMEOUT reais (block-voronoi-preview-v1) seguidos de uma cascata de falhas em TODAS as
invocações subsequentes do dispatcher (exit_code=1, inclusive nas golden recipes Gyroid de
controle, já aprovadas). A auditoria (código, sem poder reexecutar PicoGK real neste sandbox)
concluiu que:

1. worker_client.py descartava silenciosamente o stdout/stderr do worker e NUNCA verificava se
   `_kill_process_tree` de fato conseguiu encerrar o processo e seus descendentes -- apenas
   assumia sucesso. Corrigido nesta rodada: `_kill_process_tree` agora RETORNA um booleano
   confirmando (via psutil.pid_exists) que toda a árvore realmente desapareceu, e a mensagem de
   WorkerExecutionError sempre inclui esse resultado mais um trecho final de stdout/stderr.
2. O script de gate (verify_full_pipeline_sha256.py) podia matar seu PRÓPRIO processo filho
   (o dispatcher Python) via `Popen.kill()` quando seu timeout externo era mais curto que o
   orçamento interno do worker para a receita -- isso NÃO mata o neto (o `dotnet.exe` real do
   PicoGK), deixando-o órfão e consumindo recursos pelo resto da sessão (explicação mais
   provável para a cascata). Esse ponto é coberto por testes no próprio script (ver
   test_verify_full_pipeline_timeout_margin.py) e no roteiro PowerShell corrigido.

Este arquivo cobre a parte testável sem PicoGK real: encerramento genuíno da árvore de
processos, recuperação do dispatcher/orquestração após um WORKER_TIMEOUT, e preservação do
diagnóstico de erro persistido em GeometryJob.error_message.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    claim_next_queued_job,
    create_design_run_and_job,
    dispatch_job,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import (
    DotnetPicoGkWorkerClient,
    WorkerExecutionError,
    WorkerResult,
    _kill_process_tree,
    _truncate_for_log,
)
import biomatcad_api.services.worker_client as worker_client_module

from .conftest import load_golden_recipe
from .factories import create_researcher

REPO_ROOT = Path(__file__).resolve().parents[3]


def _setup_project_and_recipe(db_session, user, recipe_name: str = "block-gyroid-v1"):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Teste Timeout")
    db_session.add(project)
    db_session.flush()

    recipe_body = load_golden_recipe(recipe_name)
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Teste Timeout",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
    )
    db_session.add(recipe)
    db_session.flush()
    return project, recipe


# ---------------------------------------------------------------------------
# 1) Encerramento REAL da árvore de processos (pai + filho), com verificação --
#    não apenas "terminate() não levantou exceção".
# ---------------------------------------------------------------------------


def test_kill_process_tree_encerra_pai_e_filho_reais_e_confirma(tmp_path):
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

    deadline = time.monotonic() + 5.0
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists(), "processo filho não chegou a escrever o PID do neto a tempo"
    child_pid = int(marker.read_text().strip())

    assert psutil.pid_exists(parent.pid)
    assert psutil.pid_exists(child_pid)

    confirmed = _kill_process_tree(parent.pid, wait_timeout_seconds=3.0)

    assert confirmed is True
    assert not psutil.pid_exists(parent.pid)
    assert not psutil.pid_exists(child_pid)
    parent.wait(timeout=5)


def test_kill_process_tree_processo_ja_terminado_retorna_true(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=5)
    assert not psutil.pid_exists(proc.pid)

    confirmed = _kill_process_tree(proc.pid)

    assert confirmed is True


# ---------------------------------------------------------------------------
# 2) DotnetPicoGkWorkerClient.execute(): timeout real mata a árvore, preserva
#    stdout/stderr e a confirmação de encerramento na mensagem persistível.
#    Usa sys.executable no lugar de "dotnet" e um arquivo Python como "dll" --
#    exercita o MESMO caminho de código real (subprocess.Popen + polling +
#    _kill_process_tree), sem depender de PicoGK/dotnet instalados.
# ---------------------------------------------------------------------------


def _make_fake_worker_repo(tmp_path: Path, worker_script: str) -> Path:
    bin_dir = tmp_path / "apps" / "geometry-worker" / "bin" / "Release" / "net9.0"
    bin_dir.mkdir(parents=True)
    dll_path = bin_dir / "BioMatCadGeometryWorker.dll"
    dll_path.write_text(worker_script, encoding="utf-8")
    return tmp_path


def test_execute_timeout_mata_processo_e_preserva_diagnostico(tmp_path, monkeypatch):
    # Reduz as constantes de tempo do módulo para que o teste rode em frações de segundo, sem
    # alterar nenhum parâmetro de golden recipe real (a receita usada aqui é sintética, local
    # a este teste, nunca uma das golden recipes aprovadas -- ver restrição da rodada:
    # "não alterar parâmetros/timeout das golden recipes antes de provar a causa").
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 0.2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.05)

    marker = tmp_path / "grandchild_pid.txt"
    worker_script = (
        "import subprocess, sys, time\n"
        f"marker = {str(marker)!r}\n"
        "print('worker simulado iniciou', flush=True)\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "with open(marker, 'w') as f:\n"
        "    f.write(str(child.pid))\n"
        "time.sleep(300)\n"
    )
    repo_root = _make_fake_worker_repo(tmp_path / "fake-repo", worker_script)

    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    deadline = time.monotonic() + 10.0

    with pytest.raises(WorkerExecutionError) as excinfo:
        client.execute(
            recipe_canonical={"compute_limits": {"max_duration_seconds": 0.1}},
            job_id="fake-job-timeout",
            output_dir=tmp_path / "work",
        )

    assert time.monotonic() < deadline, "o timeout não foi respeitado dentro de uma margem razoável"
    err = excinfo.value
    assert err.error_code == "WORKER_TIMEOUT"
    # A mensagem PERSISTIDA (job.error_message, via _mark_failed) precisa conter o diagnóstico
    # real -- não apenas o texto genérico fixo de antes desta correção.
    assert "CONFIRMADA encerrada" in err.message
    assert "worker simulado iniciou" in err.message
    assert err.details.get("process_tree_confirmed_terminated") is True

    # Prova adicional e independente: o NETO (spawnado pelo "worker") também foi encerrado --
    # não apenas o filho direto do DotnetPicoGkWorkerClient.
    while not marker.exists():
        time.sleep(0.05)
    grandchild_pid = int(marker.read_text().strip())
    deadline_gc = time.monotonic() + 3.0
    while psutil.pid_exists(grandchild_pid) and time.monotonic() < deadline_gc:
        time.sleep(0.05)
    assert not psutil.pid_exists(grandchild_pid)


def test_truncate_for_log_preserva_o_trecho_final_mais_relevante():
    long_text = "x" * 50 + "COISA_IMPORTANTE_NO_FIM"
    truncated = _truncate_for_log(long_text, max_chars=30)
    assert truncated.endswith("COISA_IMPORTANTE_NO_FIM")
    assert "truncado" in truncated
    assert _truncate_for_log("curto") == "curto"


# ---------------------------------------------------------------------------
# 3) Recuperação da ORQUESTRAÇÃO: um job que falha com WORKER_TIMEOUT não pode
#    impedir que a PRÓXIMA invocação do dispatcher processe um job novo
#    normalmente (a cascata real observada na rodada 20260806-112714 foi um
#    defeito no SCRIPT de gate/orquestração Windows, não comprovadamente na
#    orquestração Python em si -- este teste prova que, ao menos no nível de
#    dispatch_job/claim_next_queued_job, não há vazamento de estado real).
# ---------------------------------------------------------------------------


class _TimesOutOnceWorkerClient:
    """Test double: simula exatamente o que DotnetPicoGkWorkerClient levantaria após um
    WORKER_TIMEOUT real (mesmo error_code, mesma forma de mensagem enriquecida)."""

    def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
        if on_process_started is not None:
            on_process_started(0)
        raise WorkerExecutionError(
            "WORKER_TIMEOUT",
            "Worker excedeu o tempo limite (30s + margem de 30s). "
            "[árvore de processos CONFIRMADA encerrada; stdout(fim)=''; stderr(fim)='']",
            {"stdout": "", "stderr": "", "process_tree_confirmed_terminated": True},
        )


class _SucceedsWorkerClient:
    def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
        if on_process_started is not None:
            on_process_started(0)
        output_dir.mkdir(parents=True, exist_ok=True)
        stl_path = output_dir / "ok.stl"
        stl_path.write_bytes(b"solid ok\nendsolid ok\n")
        return WorkerResult(
            stl_path=stl_path,
            thumbnail_path=None,
            metrics={
                "bounding_box_mm": [[0, 0, 0], [10, 10, 10]],
                "volume_mm3": 400.0,
                "porosity_pct_measured": 60.0,
                "surface_area_mm2": 950.5,
                "vertex_count_unique": 168,
                "triangle_count": 100,
                "is_watertight": True,
                "stl_reload_validation_passed": True,
            },
            worker_version="0.1.0-fake-test-double",
            dotnet_version="9.0.0",
            picogk_version="2.2.0",
            duration_seconds=0.1,
            effective_parameters={"wall_thickness_requested_mm": 0.6, "wall_thickness_effective_mm": 0.6},
            stl_sha256="1" * 64,
            platform="fake-platform-for-tests",
        )


def test_segunda_execucao_do_dispatcher_apos_timeout_processa_job_novo_normalmente(db_session, tmp_path):
    user = create_researcher(db_session, email="orch-timeout-recovery@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)

    _, job_a, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-timeout-a",
    )
    storage = LocalStorageAdapter(tmp_path / "artifacts")
    claimed_a = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher-recovery")
    assert claimed_a is not None and claimed_a.id == job_a.id
    result_a = dispatch_job(
        db_session,
        job_id=job_a.id,
        worker_client=_TimesOutOnceWorkerClient(),
        storage=storage,
        output_dir=tmp_path / "work-a",
        repo_root=REPO_ROOT,
    )
    assert result_a.status == JobStatus.FAILED
    assert result_a.error_code == "WORKER_TIMEOUT"

    # Job B, submetido e despachado LOGO EM SEGUIDA, na MESMA sessão/dispatcher: prova que o
    # job A falho (via timeout) não deixa a orquestração (claim/dispatch) num estado que
    # impeça o processamento normal de um job novo, independente.
    _, job_b, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-timeout-b",
    )
    claimed_b = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher-recovery")
    assert claimed_b is not None and claimed_b.id == job_b.id
    result_b = dispatch_job(
        db_session,
        job_id=job_b.id,
        worker_client=_SucceedsWorkerClient(),
        storage=storage,
        output_dir=tmp_path / "work-b",
        repo_root=REPO_ROOT,
    )

    assert result_b.status == JobStatus.SUCCEEDED
    assert result_b.metrics is not None


def test_error_message_do_job_preserva_diagnostico_de_timeout(db_session, tmp_path):
    """Preservação dos logs de erro (item 9 da correção): o error_message persistido no
    GeometryJob precisa conter o diagnóstico real (estado da árvore de processos + trecho de
    stdout/stderr), não apenas um texto genérico fixo -- prova, no nível de persistência, que
    o enriquecimento feito em worker_client.py realmente chega ao banco via _mark_failed."""
    user = create_researcher(db_session, email="orch-timeout-diag@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _, job, _ = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-timeout-diag",
    )
    storage = LocalStorageAdapter(tmp_path / "artifacts")
    claimed = claim_next_queued_job(db_session, dispatcher_id="test-dispatcher-diag")
    assert claimed is not None and claimed.id == job.id

    result_job = dispatch_job(
        db_session,
        job_id=job.id,
        worker_client=_TimesOutOnceWorkerClient(),
        storage=storage,
        output_dir=tmp_path / "work",
        repo_root=REPO_ROOT,
    )

    assert result_job.status == JobStatus.FAILED
    assert result_job.error_code == "WORKER_TIMEOUT"
    assert result_job.error_message is not None
    assert "CONFIRMADA encerrada" in result_job.error_message
