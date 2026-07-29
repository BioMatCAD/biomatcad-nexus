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


def _kill_process_tree(pid: int) -> None:
    """Encerra o processo `pid` e TODOS os seus descendentes (item 3/7: "encerramento de toda a
    árvore do processo"). Usa psutil (multiplataforma -- Linux e Windows) em vez de depender de
    semântica de grupo de processo específica de SO. Melhor esforço: processos que já
    terminaram entre a listagem e o kill são ignorados (psutil.NoSuchProcess)."""
    if psutil is None:
        return
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = parent.children(recursive=True)
    procs = [*children, parent]
    for p in procs:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(procs, timeout=3)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


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
        while True:
            try:
                proc.wait(timeout=POLL_INTERVAL_SECONDS)
                break
            except subprocess.TimeoutExpired:
                pass
            if cancel_check is not None and cancel_check():
                outcome = "cancelled"
                _kill_process_tree(proc.pid)
                break
            if time.monotonic() > deadline:
                outcome = "timeout"
                _kill_process_tree(proc.pid)
                break

        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            # Processo não drenou os pipes a tempo mesmo após kill -- melhor esforço, segue com
            # o que já temos (normalmente vazio nesse caso extremo).
            stdout, stderr = "", ""

        if outcome == "cancelled":
            raise WorkerExecutionError(
                "WORKER_CANCELLED",
                "Execução do worker interrompida por cancelamento solicitado pelo usuário.",
                {"stdout": stdout, "stderr": stderr},
            )
        if outcome == "timeout":
            raise WorkerExecutionError(
                "WORKER_TIMEOUT",
                f"Worker excedeu o tempo limite ({max_duration_seconds}s + margem de "
                f"{STARTUP_OVERHEAD_SECONDS}s) -- árvore de processos encerrada.",
                {"stdout": stdout, "stderr": stderr},
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
