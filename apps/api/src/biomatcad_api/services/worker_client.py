"""Cliente do worker geométrico C#/PicoGK (Incremento 2.1, item 3/4).

DotnetPicoGkWorkerClient invoca o binário REAL compilado em apps/geometry-worker via
subprocess, com um arquivo JSON já validado/canonicalizado como único insumo -- nunca envia
código executável. Se o runtime nativo do PicoGK não estiver disponível (bloqueio conhecido
em linux-x64 neste sandbox, ver ADR-0007/WORKER_STATUS.md), o processo falha com uma exceção
real do .NET, capturada e traduzida em WorkerExecutionError(code=WORKER_RUNTIME_UNAVAILABLE)
-- este cliente NUNCA fabrica um resultado de sucesso.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


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


class GeometryWorkerClient(Protocol):
    def execute(self, *, recipe_canonical: dict, job_id: str, output_dir: Path) -> WorkerResult: ...


def _find_worker_dll(repo_root: Path) -> Path | None:
    candidates = list(
        (repo_root / "apps" / "geometry-worker" / "bin").glob("**/BioMatCadGeometryWorker.dll")
    )
    # Prioriza builds Release sobre Debug, se ambos existirem.
    candidates.sort(key=lambda p: 0 if "Release" in str(p) else 1)
    return candidates[0] if candidates else None


class DotnetPicoGkWorkerClient:
    def __init__(self, repo_root: Path, dotnet_bin: str | None = None) -> None:
        self.repo_root = repo_root
        self.dotnet_bin = dotnet_bin or shutil.which("dotnet") or "dotnet"

    def execute(self, *, recipe_canonical: dict, job_id: str, output_dir: Path) -> WorkerResult:
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

        try:
            proc = subprocess.run(
                [self.dotnet_bin, str(dll_path), str(job_json_path)],
                capture_output=True,
                text=True,
                timeout=recipe_canonical.get("compute_limits", {}).get("max_duration_seconds", 300) + 30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkerExecutionError(
                "WORKER_TIMEOUT", f"Worker excedeu o tempo limite: {exc}"
            ) from exc

        if proc.returncode != 0:
            details: dict = {"stdout": proc.stdout, "stderr": proc.stderr}
            try:
                structured = json.loads(proc.stderr.strip().splitlines()[-1]) if proc.stderr.strip() else {}
            except (ValueError, IndexError):
                structured = {}
            if structured.get("error_code") == "PICOGK_RUNTIME_UNAVAILABLE" or "DllNotFoundException" in proc.stderr:
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
            result_json = json.loads(proc.stdout.strip().splitlines()[-1])
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
        )


def get_default_worker_client(repo_root: Path) -> DotnetPicoGkWorkerClient:
    return DotnetPicoGkWorkerClient(repo_root=repo_root)
