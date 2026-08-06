"""Cliente do worker geométrico C#/PicoGK (Incremento 2.1, item 3/4; Incremento 2.1.1, itens 3 e 7).

DotnetPicoGkWorkerClient invoca o binário REAL compilado em apps/geometry-worker via
subprocess, com um arquivo JSON já validado/canonicalizado como único insumo -- nunca envia
código executável. Se o runtime nativo do PicoGK não estiver disponível (bloqueio conhecido
em linux-x64 neste sandbox, ver ADR-0007/WORKER_STATUS.md), o processo falha com uma exceção
real do .NET, capturada e traduzida em WorkerExecutionError(code=WORKER_RUNTIME_UNAVAILABLE)
-- este cliente NUNCA fabrica um resultado de sucesso.

Incremento 2.1.1 (itens 3 e 7): substitui o `subprocess.run(timeout=...)` simples por um loop
de polling com `Popen`, que permite (a) encerrar a ÁRVORE INTEIRA de processos (não apenas o
processo filho direto) em caso de timeout real, via psutil (multiplataforma -- funciona tanto
no sandbox Linux quanto no Windows onde o worker de fato roda), e (b) verificar, a cada
intervalo curto, se um cancelamento foi solicitado (callback `cancel_check`), permitindo
interromper o worker em execução em vez de esperar sua conclusão natural.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

try:
    import psutil
except ImportError:  # pragma: no cover -- psutil é dependência obrigatória em produção
    psutil = None  # type: ignore[assignment]

POLL_INTERVAL_SECONDS = 0.5
STARTUP_OVERHEAD_SECONDS = 30  # margem além de max_duration_seconds para custo de start do dotnet


class WorkerExecutionError(RuntimeError):
    def __init__(self, error_code: str, message: str, details: dict | None = None) -> None:
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(f"{error_code}: {message}")


@dataclass
class WorkerResult:
    stl_path: Path
    thumbnail_path: Path | None
    metrics: dict
    worker_version: str
    dotnet_version: str
    picogk_version: str
    duration_seconds: float
    vdb_path: Path | None = None
    effective_parameters: dict | None = None
    stl_sha256: str | None = None
    platform: str | None = None


class GeometryWorkerClient(Protocol):
    def execute(
        self,
        *,
        recipe_canonical: dict,
        job_id: str,
        output_dir: Path,
        cancel_check: Callable[[], bool] | None = None,
        on_process_started: Callable[[int], None] | None = None,
    ) -> WorkerResult: ...


def _find_worker_dll(repo_root: Path) -> Path | None:
    candidates = list(
        (repo_root / "apps" / "geometry-worker" / "bin").glob("**/BioMatCadGeometryWorker.dll")
    )
    # Prioriza builds Release sobre Debug, se ambos existirem.
    candidates.sort(key=lambda p: 0 if "Release" in str(p) else 1)
    return candidates[0] if candidates else None


def _kill_process_tree(pid: int, *, wait_timeout_seconds: float = 3.0) -> bool:
    """Encerra o processo `pid` e TODOS os seus descendentes (item 3/7: "encerramento de toda a
    árvore do processo"). Usa psutil (multiplataforma -- Linux e Windows) em vez de depender de
    semântica de grupo de processo específica de SO. Melhor esforço: processos que já
    terminaram entre a listagem e o kill são ignorados (psutil.NoSuchProcess).

    Correção real (rodada Voronoi, auditoria da execução Windows 20260806-112714): a versão
    anterior desta função assumia silenciosamente que terminate()+kill() sempre funcionam e
    NUNCA verificava se os processos de fato desapareceram -- combinado com o chamador
    (execute(), abaixo) que também nunca checava esse retorno, isso significa que um processo
    (ou um descendente nativo do PicoGK) que sobrevivesse ao kill por qualquer motivo real
    (arquitetura Windows, handle gráfico/GPU não liberado a tempo, processo "zumbi") ficaria
    rodando em segundo plano SEM que ninguém soubesse -- explicação mais provável, encontrada
    nesta auditoria, para a cascata de falhas em toda invocação SUBSEQUENTE do dispatcher na
    rodada 20260806-112714 (ver TEST_EVIDENCE.md). Agora retorna True somente se TODOS os PIDs
    da árvore original (pai + descendentes) foram confirmados ausentes após o kill -- via
    psutil.pid_exists, não apenas "o kill não levantou exceção".
    """
    if psutil is None:
        return False
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True
    children = parent.children(recursive=True)
    procs = [*children, parent]
    original_pids = [p.pid for p in procs]
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=wait_timeout_seconds)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass
    if alive:
        # Segunda espera curta pós-kill(): dá ao SO uma última chance real de liberar o
        # processo antes de declararmos "não confirmado" (nunca assumimos sucesso sem checar).
        psutil.wait_procs(alive, timeout=wait_timeout_seconds)
    return all(not psutil.pid_exists(original_pid) for original_pid in original_pids)


def _truncate_for_log(text: str, max_chars: int = 300) -> str:
    """Corta uma string de diagnóstico (stdout/stderr) para um tamanho seguro de embutir em
    error_message (limitado a 1000 caracteres em _mark_failed, ver geometry_job_service.py) --
    preserva o TRECHO FINAL (mais relevante para diagnosticar onde o processo travou/morreu),
    não o início."""
    if len(text) <= max_chars:
        return text
    return f"...[truncado, {len(text) - max_chars} chars omitidos]...{text[-max_chars:]}"


class DotnetPicoGkWorkerClient:
    def __init__(self, repo_root: Path, dotnet_bin: str | None = None) -> None:
        self.repo_root = repo_root
        self.dotnet_bin = dotnet_bin or shutil.which("dotnet") or "dotnet"

    def execute(
        self,
        *,
        recipe_canonical: dict,
        job_id: str,
        output_dir: Path,
        cancel_check: Callable[[], bool] | None = None,
        on_process_started: Callable[[int], None] | None = None,
    ) -> WorkerResult:
        if shutil.which(self.dotnet_bin) is None and not Path(self.dotnet_bin).exists():
            raise WorkerExecutionError(
                "DOTNET_RUNTIME_NOT_FOUND",
                f"Executável dotnet não encontrado em '{self.dotnet_bin}'. Instale o .NET SDK "
                "(ver apps/geometry-worker/WORKER_STATUS.md) antes de executar jobs geométricos.",
            )

        dll_path = _find_worker_dll(self.repo_root)
        if dll_path is None:
            raise WorkerExecutionError(
                "WORKER_BINARY_NOT_BUILT",
                "apps/geometry-worker não foi compilado (BioMatCadGeometryWorker.dll não "
                "encontrado). Rode 'dotnet build' em apps/geometry-worker antes de despachar jobs.",
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        job_json_path = output_dir / "job.json"
        job_json_path.write_text(
            json.dumps(
                {"job_id": job_id, "recipe": recipe_canonical, "output_dir": str(output_dir)},
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        max_duration_seconds = recipe_canonical.get("compute_limits", {}).get("max_duration_seconds", 300)
        deadline = time.monotonic() + max_duration_seconds + STARTUP_OVERHEAD_SECONDS

        proc = subprocess.Popen(
            [self.dotnet_bin, str(dll_path), str(job_json_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if on_process_started is not None:
            on_process_started(proc.pid)

        outcome = "completed"
        tree_confirmed_terminated: bool | None = None
        while True:
            try:
                proc.wait(timeout=POLL_INTERVAL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_check is not None and cancel_check():
                outcome = "cancelled"
                tree_confirmed_terminated = _kill_process_tree(proc.pid)
                break
            if time.monotonic() > deadline:
                outcome = "timeout"
                tree_confirmed_terminated = _kill_process_tree(proc.pid)
                break

        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # Processo não drenou os pipes a tempo mesmo após kill -- melhor esforço, segue com
            # o que já temos (normalmente vazio nesse caso extremo). Isso NÃO significa que o
            # processo continua vivo -- tree_confirmed_terminated (acima) é quem prova isso.
            stdout, stderr = "", ""

        # Diagnóstico preservado (correção real, auditoria 20260806-112714): stdout/stderr do
        # worker e a confirmação (ou não) do encerramento da árvore de processos SEMPRE entram
        # na mensagem da exceção -- _mark_failed (geometry_job_service.py) persiste esta
        # mensagem inteira em job.error_message, então este diagnóstico agora sobrevive ao
        # término do processo em vez de ser descartado silenciosamente (antes: só
        # `details={"stdout":..., "stderr":...}` era anexado à exceção, mas _mark_failed nunca
        # lia `details`, só `.message` -- o conteúdo nunca chegava a lugar nenhum persistido).
        def _diagnostic_suffix() -> str:
            tree_status = {
                True: "árvore de processos CONFIRMADA encerrada",
                False: "árvore de processos NÃO CONFIRMADA como encerrada -- possível processo órfão sobrevivente",
                None: "encerramento da árvore não verificado",
            }[tree_confirmed_terminated]
            return (
                f" [{tree_status}; stdout(fim)={_truncate_for_log(stdout)!r}; "
                f"stderr(fim)={_truncate_for_log(stderr)!r}]"
            )

        if outcome == "cancelled":
            raise WorkerExecutionError(
                "WORKER_CANCELLED",
                "Execução do worker interrompida por cancelamento solicitado pelo usuário."
                + _diagnostic_suffix(),
                {
                    "stdout": stdout,
                    "stderr": stderr,
                    "process_tree_confirmed_terminated": tree_confirmed_terminated,
                },
            )
        if outcome == "timeout":
            raise WorkerExecutionError(
                "WORKER_TIMEOUT",
                f"Worker excedeu o tempo limite ({max_duration_seconds}s + margem de "
                f"{STARTUP_OVERHEAD_SECONDS}s)." + _diagnostic_suffix(),
                {
                    "stdout": stdout,
                    "stderr": stderr,
                    "process_tree_confirmed_terminated": tree_confirmed_terminated,
                },
            )

        if proc.returncode != 0:
            details: dict = {"stdout": stdout, "stderr": stderr}
            try:
                structured = json.loads(stderr.strip().splitlines()[-1]) if stderr.strip() else {}
            except (ValueError, IndexError):
                structured = {}
            if structured.get("error_code") == "PICOGK_RUNTIME_UNAVAILABLE" or "DllNotFoundException" in stderr:
                raise WorkerExecutionError(
                    "WORKER_RUNTIME_UNAVAILABLE",
                    "O runtime nativo do PicoGK não está disponível nesta plataforma (bloqueio "
                    "conhecido em linux-x64 -- ver apps/geometry-worker/WORKER_STATUS.md).",
                    details,
                )
            raise WorkerExecutionError(
                structured.get("error_code", "WORKER_EXECUTION_FAILED"),
                structured.get("message", "Falha na execução do worker geométrico."),
                details,
            )

        try:
            result_json = json.loads(stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise WorkerExecutionError(
                "WORKER_INVALID_OUTPUT", f"Saída do worker não é JSON válido: {exc}"
            ) from exc

        return WorkerResult(
            stl_path=Path(result_json["stl_path"]),
            thumbnail_path=Path(result_json["thumbnail_path"]) if result_json.get("thumbnail_path") else None,
            vdb_path=Path(result_json["vdb_path"]) if result_json.get("vdb_path") else None,
            metrics=result_json["metrics"],
            worker_version=result_json["worker_version"],
            dotnet_version=result_json["dotnet_version"],
            picogk_version=result_json["picogk_version"],
            duration_seconds=result_json["duration_seconds"],
            effective_parameters=result_json.get("effective_parameters"),
            stl_sha256=result_json.get("stl_sha256"),
            platform=result_json.get("platform"),
        )


def get_default_worker_client(repo_root: Path) -> DotnetPicoGkWorkerClient:
    return DotnetPicoGkWorkerClient(repo_root=repo_root)
