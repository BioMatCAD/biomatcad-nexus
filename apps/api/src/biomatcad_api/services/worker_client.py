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
import threading
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


def _write_full_diagnostics_file(
    *,
    output_dir: Path,
    job_id: str,
    outcome: str,
    stdout: str,
    stderr: str,
    tree_confirmed_terminated: bool | None,
    returncode: int | None,
) -> Path | None:
    """Preserva o stdout/stderr COMPLETO (nunca truncado) do worker em um arquivo próprio,
    fora de `output_dir` (rodada Voronoi 20260806-133141, item 7 da correção pedida pelo
    usuário).

    Por que fora de output_dir: em qualquer caminho de falha (cancelamento, timeout, exit code
    != 0), o chamador (dispatch_job, em geometry_job_service.py) sempre invoca
    `_cleanup_output_dir(output_dir)` logo depois de `_mark_failed`/`_finalize_cancelled` --
    isso apaga `output_dir` inteiro recursivamente (`shutil.rmtree`). Um arquivo de diagnóstico
    gravado DENTRO de `output_dir` seria destruído no mesmo instante em que se tornaria
    necessário (exatamente o cenário que motivou este item: o WORKER_TIMEOUT do Voronoi mostrou
    um JSON quase completo no stdout, mas apenas os últimos ~300 caracteres sobreviviam em
    error_message -- o restante era permanentemente perdido). Em vez disso, grava em um
    diretório IRMÃO de output_dir (`output_dir.parent / "_worker_diagnostics"`), que nenhuma
    rotina de limpeza conhecida remove.

    Melhor esforço: uma falha ao gravar o diagnóstico (ex.: disco cheio, permissão) NUNCA deve
    mascarar o erro original do worker -- por isso todo o corpo roda em try/except e retorna
    None silenciosamente em caso de problema, deixando o chamador seguir com o
    WorkerExecutionError original de qualquer forma."""
    try:
        diagnostics_dir = output_dir.parent / "_worker_diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        diagnostics_path = diagnostics_dir / f"{job_id}.json"
        payload = {
            "job_id": job_id,
            "outcome": outcome,
            "returncode": returncode,
            "process_tree_confirmed_terminated": tree_confirmed_terminated,
            "stdout_full": stdout,
            "stderr_full": stderr,
            "stdout_char_count": len(stdout),
            "stderr_char_count": len(stderr),
        }
        diagnostics_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return diagnostics_path
    except OSError:
        return None


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

        # Correção real (rodada Voronoi 20260806-*, auditoria pedida pelo usuário após a Fase A
        # provar que o worker/PicoGK real termina sozinho em ~2.5s quando invocado diretamente,
        # sem este cliente): a versão anterior deste método fazia um loop de `proc.wait(timeout=
        # POLL_INTERVAL_SECONDS)` para cancelamento/timeout SEM NUNCA LER `proc.stdout`/
        # `proc.stderr` durante essa espera -- só chamava `proc.communicate()` DEPOIS do loop.
        # Pipes do SO têm um buffer FINITO (tipicamente ~64KB no Linux; ordem de grandeza
        # semelhante em pipes anônimos do Windows). Se o processo filho escrever mais do que
        # esse buffer comporta em stdout OU stderr antes que alguém leia, a própria chamada de
        # escrita do filho BLOQUEIA no nível do SO, esperando um leitor que nunca vem (o pai
        # está preso em `wait()`, não lendo nada) -- um deadlock clássico entre processos.
        # `proc.wait()` nunca detecta isso como "processo travado": do ponto de vista do SO, o
        # processo continua vivo (só bloqueado numa chamada de sistema), então o loop de poll
        # simplesmente esgota o prazo e aciona o WORKER_TIMEOUT externo -- exatamente o sintoma
        # relatado (worker "trava" e só é resolvido pelo watchdog), mesmo quando o cálculo em si
        # já tinha terminado (ver o JSON quase completo capturado no stdout parcial de rodadas
        # anteriores). Reproduzido nesta rodada com um processo auxiliar que escreve ~5.7MB
        # simultaneamente em stdout/stderr: a implementação anterior sempre resultava em
        # WORKER_TIMEOUT, mesmo o processo auxiliar sendo capaz de terminar em milissegundos se
        # tivesse um leitor ativo.
        #
        # Correção: duas threads em segundo plano DRENAM stdout e stderr CONTINUAMENTE, em
        # paralelo ao loop de poll/cancelamento/timeout abaixo -- o filho nunca mais bloqueia
        # esperando um leitor, porque sempre há um. As threads terminam sozinhas quando os
        # pipes fecham (processo saiu normalmente, ou foi encerrado pelo kill de árvore abaixo,
        # o que remove todos os escritores restantes do pipe e sinaliza EOF ao leitor). Nunca
        # mais se usa `proc.communicate()` (que faria uma segunda leitura conflitante) -- o
        # conteúdo acumulado pelas threads é a única fonte de verdade para stdout/stderr.
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _drain(stream, sink: list[str]) -> None:
            try:
                while True:
                    chunk = stream.read(65536)
                    if not chunk:
                        break
                    sink.append(chunk)
            except (ValueError, OSError):
                # Stream fechado externamente (ex.: kill do processo enquanto uma leitura
                # estava em andamento) -- encerra silenciosamente; nunca mascara o erro
                # original do worker, que é decidido abaixo pelo outcome/returncode reais.
                pass
            finally:
                try:
                    stream.close()
                except (ValueError, OSError):
                    pass

        stdout_thread = threading.Thread(target=_drain, args=(proc.stdout, stdout_chunks), daemon=True)
        stderr_thread = threading.Thread(target=_drain, args=(proc.stderr, stderr_chunks), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

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

        # Depois que o processo saiu (ou foi encerrado acima), os pipes fecham e as threads de
        # dreno terminam sozinhas -- join com um teto curto de segurança (nunca bloqueia
        # indefinidamente; se algo impedir o fechamento do pipe mesmo após o kill da árvore
        # confirmado, ainda assim seguimos com o que já foi lido até aqui).
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=10)
        stdout = "".join(stdout_chunks)
        stderr = "".join(stderr_chunks)

        # Diagnóstico preservado (correção real, auditoria 20260806-112714): stdout/stderr do
        # worker e a confirmação (ou não) do encerramento da árvore de processos SEMPRE entram
        # na mensagem da exceção -- _mark_failed (geometry_job_service.py) persiste esta
        # mensagem inteira em job.error_message, então este diagnóstico agora sobrevive ao
        # término do processo em vez de ser descartado silenciosamente (antes: só
        # `details={"stdout":..., "stderr":...}` era anexado à exceção, mas _mark_failed nunca
        # lia `details`, só `.message` -- o conteúdo nunca chegava a lugar nenhum persistido).
        # Item 7 (rodada Voronoi 20260806-133141): o stdout/stderr COMPLETO (nunca truncado)
        # é sempre preservado em um arquivo próprio antes de qualquer levantamento de exceção
        # abaixo -- independente do desfecho (cancelado, timeout, ou exit code != 0). O motivo:
        # a evidência real coletada no Windows mostrou um JSON de resultado quase inteiro
        # presente no stdout de um WORKER_TIMEOUT (mesh_calibration_iterations, porosidade
        # medida etc.), mas `_truncate_for_log` (usado só para a mensagem embutida na exceção)
        # descarta tudo, exceto os últimos 300 caracteres -- e `_mark_failed`
        # (geometry_job_service.py) trunca de novo em 1000 -- o restante do diagnóstico nunca
        # sobrevivia. Este arquivo NÃO substitui `_truncate_for_log`/`.message` (que continuam
        # existindo para leitura rápida em logs/AuditEvent), apenas garante que o conteúdo
        # integral fique disponível para auditoria posterior.
        full_diagnostics_path: Path | None = None
        if outcome in ("cancelled", "timeout") or proc.returncode != 0:
            full_diagnostics_path = _write_full_diagnostics_file(
                output_dir=output_dir,
                job_id=job_id,
                outcome=outcome if outcome != "completed" else "failed_exit_code",
                stdout=stdout,
                stderr=stderr,
                tree_confirmed_terminated=tree_confirmed_terminated,
                returncode=proc.returncode,
            )

        def _diagnostic_suffix() -> str:
            tree_status = {
                True: "árvore de processos CONFIRMADA encerrada",
                False: "árvore de processos NÃO CONFIRMADA como encerrada -- possível processo órfão sobrevivente",
                None: "encerramento da árvore não verificado",
            }[tree_confirmed_terminated]
            diagnostics_note = (
                f"; diagnóstico completo (stdout/stderr não truncado) em: {full_diagnostics_path}"
                if full_diagnostics_path is not None
                else ""
            )
            return (
                f" [{tree_status}; stdout(fim)={_truncate_for_log(stdout)!r}; "
                f"stderr(fim)={_truncate_for_log(stderr)!r}{diagnostics_note}]"
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
                    "full_diagnostics_path": str(full_diagnostics_path) if full_diagnostics_path else None,
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
                    "full_diagnostics_path": str(full_diagnostics_path) if full_diagnostics_path else None,
                },
            )

        if proc.returncode != 0:
            details: dict = {
                "stdout": stdout,
                "stderr": stderr,
                "full_diagnostics_path": str(full_diagnostics_path) if full_diagnostics_path else None,
            }
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
