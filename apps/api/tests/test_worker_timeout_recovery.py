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

import biomatcad_api.services.worker_client as worker_client_module
from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import (
    claim_next_queued_job,
    create_design_run_and_job,
    dispatch_job,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize
from biomatcad_api.services.storage import LocalStorageAdapter, sha256_of_bytes
from biomatcad_api.services.worker_client import (
    DotnetPicoGkWorkerClient,
    WorkerExecutionError,
    WorkerResult,
    _kill_process_tree,
    _truncate_for_log,
)

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
# Item 7 (rodada Voronoi 20260806-133141): a evidência real do Windows mostrou um JSON de
# resultado quase completo (mesh_calibration_iterations, porosidade medida etc.) presente no
# stdout de um WORKER_TIMEOUT real -- mas `_truncate_for_log`/`_mark_failed` preservavam apenas
# os últimos ~300/1000 caracteres. Estes testes provam que o stdout/stderr INTEIRO agora
# sobrevive em um arquivo próprio, fora de output_dir (que é sempre apagado em qualquer
# caminho de falha por dispatch_job -- ver _cleanup_output_dir em geometry_job_service.py).
# ---------------------------------------------------------------------------


def test_execute_timeout_preserva_stdout_completo_em_arquivo_proprio(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 0.2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.05)

    # Stdout deliberadamente maior que os 300 caracteres preservados por _truncate_for_log --
    # simula o JSON quase completo observado na evidência real (o essencial aqui é que o
    # CONTEÚDO INICIAL (fora da janela final de 300 chars) também sobreviva em algum lugar).
    marker_content = "INICIO_DO_JSON_" + ("y" * 500) + "_CONTEUDO_QUE_A_TRUNCACAO_DESCARTARIA"
    worker_script = (
        "import time\n"
        f"print({marker_content!r}, flush=True)\n"
        "time.sleep(300)\n"
    )
    repo_root = _make_fake_worker_repo(tmp_path / "fake-repo", worker_script)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    output_dir = tmp_path / "work" / "job-diag-1"
    with pytest.raises(WorkerExecutionError) as excinfo:
        client.execute(
            recipe_canonical={"compute_limits": {"max_duration_seconds": 0.1}},
            job_id="job-diag-1",
            output_dir=output_dir,
        )

    err = excinfo.value
    # A mensagem/.message continua truncada (não muda o comportamento pré-existente de log) --
    # o conteúdo do início do JSON NÃO deve estar na mensagem embutida.
    assert marker_content[:50] not in err.message

    diagnostics_path_str = err.details.get("full_diagnostics_path")
    assert diagnostics_path_str is not None, "full_diagnostics_path ausente em details"
    diagnostics_path = Path(diagnostics_path_str)
    assert diagnostics_path.exists()
    # Preservado FORA de output_dir (irmão, não descendente) -- para sobreviver ao
    # shutil.rmtree(output_dir) que dispatch_job sempre faz após uma falha.
    assert output_dir not in diagnostics_path.parents

    payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert payload["job_id"] == "job-diag-1"
    assert payload["outcome"] == "timeout"
    # O conteúdo INTEIRO (incluindo a parte que a truncação para log descartaria) está presente.
    assert marker_content in payload["stdout_full"]
    assert payload["stdout_char_count"] == len(payload["stdout_full"])


def test_full_diagnostics_file_sobrevive_a_limpeza_do_output_dir(tmp_path, monkeypatch):
    """Reproduz o exato caminho de dispatch_job: depois de _mark_failed, o chamador sempre
    invoca _cleanup_output_dir(output_dir) (shutil.rmtree). Prova que o arquivo de diagnóstico
    completo, por estar em um diretório IRMÃO, sobrevive a essa limpeza."""
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 0.2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.05)

    worker_script = "import time\nprint('conteudo completo relevante', flush=True)\ntime.sleep(300)\n"
    repo_root = _make_fake_worker_repo(tmp_path / "fake-repo", worker_script)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    output_dir = tmp_path / "work" / "job-diag-2"
    with pytest.raises(WorkerExecutionError) as excinfo:
        client.execute(
            recipe_canonical={"compute_limits": {"max_duration_seconds": 0.1}},
            job_id="job-diag-2",
            output_dir=output_dir,
        )

    diagnostics_path = Path(excinfo.value.details["full_diagnostics_path"])
    assert diagnostics_path.exists()

    # Mesma chamada de limpeza usada por dispatch_job (geometry_job_service._cleanup_output_dir).
    import shutil as _shutil

    if output_dir.exists():
        _shutil.rmtree(output_dir, ignore_errors=True)

    assert not output_dir.exists()
    assert diagnostics_path.exists(), "diagnóstico completo não deveria ser apagado pela limpeza de output_dir"
    assert "conteudo completo relevante" in diagnostics_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Item novo (rodada pós-Fase A real no Windows, commit 7a44da4): a Fase A provou, no Windows
# real, que o worker/PicoGK genuíno (invocado DIRETAMENTE, sem este cliente) termina sozinho em
# ~2.5s para block-voronoi-preview-v1 -- exit code 0, sem kill, sem órfão. Isso REFUTA a
# hipótese de que o algoritmo Voronoi/PicoGK em si causa o WORKER_TIMEOUT, e aponta para
# DotnetPicoGkWorkerClient.execute() (este arquivo). Auditoria: a versão anterior deste método
# fazia um loop de `proc.wait(timeout=POLL_INTERVAL_SECONDS)` para cancelamento/timeout SEM
# NUNCA ler `proc.stdout`/`proc.stderr` durante essa espera -- só chamava `proc.communicate()`
# DEPOIS do loop. Pipes do SO têm buffer finito (tipicamente ~64KB no Linux) -- se o processo
# filho escrever mais que isso em stdout OU stderr antes de qualquer leitura, a própria escrita
# do filho BLOQUEIA no nível do SO esperando um leitor que nunca vem (o pai está preso em
# `wait()`), reproduzindo exatamente o sintoma relatado (processo "trava", só resolvido pelo
# watchdog externo) mesmo quando o cálculo em si já tinha terminado.
#
# Os testes abaixo prova(ra)m isso de forma real e permanente: (1) reproduzem o deadlock com um
# processo auxiliar que escreve volume muito acima de qualquer buffer de pipe do SO,
# simultaneamente em stdout e stderr, terminando com um JSON válido -- a versão SEM a correção
# de drenagem contínua sempre resulta em WORKER_TIMEOUT aqui (confirmado manualmente nesta
# sessão via `git stash`, comparando literalmente antes/depois desta mesma correção); (2)
# confirmam que a versão CORRIGIDA completa rapidamente, com sucesso, capturando o stdout/stderr
# completos; (3) confirmam que cancelamento e timeout genuíno continuam funcionando com a
# drenagem contínua ativa.
# ---------------------------------------------------------------------------


def _make_fake_worker_repo_with_large_output_script(tmp_path: Path, *, hang_after_output: bool) -> Path:
    """Processo auxiliar que escreve ~5.7MB simultaneamente em stdout e stderr (muito acima de
    qualquer buffer de pipe do SO, tipicamente ~64KB no Linux/Windows), com flush explícito por
    linha -- se ninguém drenar os dois pipes CONTINUAMENTE, a própria escrita do processo
    bloqueia. Termina com um JSON final válido (linha limpa, como o worker real: Program.cs só
    escreve UMA linha em stdout, o JSON -- qualquer volume grande de log real iria para
    stderr). Se `hang_after_output`, permanece vivo indefinidamente depois (para o teste de
    timeout genuíno); caso contrário, sai imediatamente com exit code 0."""
    worker_script_lines = [
        "import sys, json, time",
        "chunk = ('X' * 8192) + chr(10)",
        "for _ in range(700):",
        "    sys.stdout.write(chunk)",
        "    sys.stdout.flush()",
        "    sys.stderr.write(chunk)",
        "    sys.stderr.flush()",
        (
            "result = {'stl_path': '/fake/scaffold.stl', 'metrics': {'vertex_count': 1}, "
            "'worker_version': 'fake-pipe-test', 'dotnet_version': 'fake', 'picogk_version': 'fake', "
            "'duration_seconds': 0.01}"
        ),
        "print(json.dumps(result), flush=True)",
    ]
    if hang_after_output:
        worker_script_lines.append("time.sleep(300)")
    worker_script = "\n".join(worker_script_lines) + "\n"
    return _make_fake_worker_repo(tmp_path / "fake-repo", worker_script)


def test_execute_nao_trava_quando_processo_escreve_volume_maior_que_buffer_do_pipe(tmp_path, monkeypatch):
    """Reprodução direta e permanente do deadlock relatado: um processo que escreve muito mais
    que o buffer de um pipe do SO em stdout E stderr, simultaneamente, deve ser drenado
    continuamente e concluir rapidamente -- nunca resultar em WORKER_TIMEOUT."""
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.1)

    repo_root = _make_fake_worker_repo_with_large_output_script(tmp_path, hang_after_output=False)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    t0 = time.monotonic()
    result = client.execute(
        recipe_canonical={"compute_limits": {"max_duration_seconds": 3}},
        job_id="pipe-drain-success",
        output_dir=tmp_path / "work",
    )
    elapsed = time.monotonic() - t0

    assert result.worker_version == "fake-pipe-test"
    # Deve completar MUITO antes do prazo (3s+2s=5s) -- se o deadlock não tivesse sido
    # corrigido, isso teria estourado o timeout e levantado WorkerExecutionError.
    assert elapsed < 4.0, f"execução demorou {elapsed:.2f}s -- indica que a drenagem não está funcionando"


def test_execute_captura_stdout_e_stderr_completos_mesmo_com_volume_grande(tmp_path, monkeypatch):
    """Além de não travar, a implementação corrigida deve preservar o CONTEÚDO INTEIRO de
    stdout/stderr (não apenas o suficiente para destravar) -- necessário para diagnóstico real
    em caso de falha, e para a extração correta da última linha JSON."""
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.1)

    repo_root = _make_fake_worker_repo_with_large_output_script(tmp_path, hang_after_output=False)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    # Acessa o stdout/stderr brutos via um cancel_check espião não é necessário aqui -- a prova
    # mais direta é que o JSON final (última linha de stdout) foi corretamente extraído E que
    # nenhuma exceção de parsing ocorreu, o que só é possível se as ~700 linhas anteriores de
    # padding (~5.7MB) foram de fato lidas e a linha final isolada corretamente.
    result = client.execute(
        recipe_canonical={"compute_limits": {"max_duration_seconds": 3}},
        job_id="pipe-drain-content",
        output_dir=tmp_path / "work2",
    )
    assert result.metrics == {"vertex_count": 1}


def test_execute_cancelamento_continua_funcionando_com_drenagem_continua(tmp_path, monkeypatch):
    """A correção de drenagem não pode quebrar o mecanismo de cancelamento real (item 7 do
    Incremento 2.1.1) -- um processo que escreve continuamente mas NUNCA produz o JSON final
    (nunca sai sozinho) deve continuar sendo encerrado corretamente quando cancel_check
    retorna True."""
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 5)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.1)

    worker_script = (
        "import sys, time\n"
        "chunk = ('Y' * 8192) + chr(10)\n"
        "while True:\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.write(chunk)\n"
        "    sys.stderr.flush()\n"
        "    time.sleep(0.01)\n"
    )
    repo_root = _make_fake_worker_repo(tmp_path / "fake-repo", worker_script)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    call_count = {"n": 0}

    def cancel_after_a_bit() -> bool:
        call_count["n"] += 1
        return call_count["n"] >= 3  # cancela depois de algumas checagens (~0.3s)

    with pytest.raises(WorkerExecutionError) as excinfo:
        client.execute(
            recipe_canonical={"compute_limits": {"max_duration_seconds": 60}},
            job_id="pipe-drain-cancel",
            output_dir=tmp_path / "work",
            cancel_check=cancel_after_a_bit,
        )

    assert excinfo.value.error_code == "WORKER_CANCELLED"
    assert excinfo.value.details.get("process_tree_confirmed_terminated") is True


def test_execute_timeout_genuino_continua_funcionando_com_drenagem_continua(tmp_path, monkeypatch):
    """A correção de drenagem não pode mascarar um timeout GENUÍNO (processo que realmente
    nunca termina, mesmo drenado) -- continua resultando em WORKER_TIMEOUT com a árvore
    confirmada encerrada, exatamente como antes desta correção."""
    monkeypatch.setattr(worker_client_module, "STARTUP_OVERHEAD_SECONDS", 0.2)
    monkeypatch.setattr(worker_client_module, "POLL_INTERVAL_SECONDS", 0.05)

    repo_root = _make_fake_worker_repo_with_large_output_script(tmp_path, hang_after_output=True)
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    with pytest.raises(WorkerExecutionError) as excinfo:
        client.execute(
            recipe_canonical={"compute_limits": {"max_duration_seconds": 0.3}},
            job_id="pipe-drain-genuine-timeout",
            output_dir=tmp_path / "work",
        )

    assert excinfo.value.error_code == "WORKER_TIMEOUT"
    assert excinfo.value.details.get("process_tree_confirmed_terminated") is True
    # Mesmo tendo travado de propósito (hang_after_output=True), o JSON final e todo o padding
    # ANTES do hang devem ter sido capturados integralmente no diagnóstico completo -- prova
    # que a drenagem estava ativa durante toda a execução, não apenas até o momento do kill.
    diagnostics_path = Path(excinfo.value.details["full_diagnostics_path"])
    payload = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert '"vertex_count": 1' in payload["stdout_full"] or "vertex_count" in payload["stdout_full"]


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
        stl_content = b"solid ok\nendsolid ok\n"
        stl_path = output_dir / "ok.stl"
        stl_path.write_bytes(stl_content)
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
            # SHA-256 REAL do conteudo escrito (Fase D, Incremento 2.2, tornou dispatch_job()
            # sensivel a divergencia entre este valor e o hash de fato calculado a partir dos
            # bytes armazenados -- ver test_security_hardening/test_geometry_job_orchestration).
            stl_sha256=sha256_of_bytes(stl_content),
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
