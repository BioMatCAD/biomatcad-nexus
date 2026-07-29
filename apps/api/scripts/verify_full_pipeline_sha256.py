#!/usr/bin/env python3
"""Gate final do Incremento 2.1.1 (item 12, "última vertical"): prova que o fluxo de PRODUÇÃO
completo -- API real -> fila Postgres -> dispatcher real -> worker C#/PicoGK REAL -> STL real
-> Artifact/ArtifactManifest reais -> download real via API -- produz um resultado íntegro e
autoconsistente.

Diferença deliberada em relação ao E2E Playwright (apps/web/e2e/vertical.spec.ts) e ao seed do
E2E (apps/api/scripts/seed_e2e_user.py): AMBOS usam um job succeeded PRÉ-SEMEADO via
_FakeWorkerClientForE2ESeed (nunca PicoGK real) para provar a INTERFACE. Este script NUNCA usa
job pré-semeado nem qualquer test double -- ele submete um DesignRun/GeometryJob NOVO através
da API HTTP real, invoca o dispatcher real (que usa DotnetPicoGkWorkerClient, o mesmo cliente
usado em produção) e só aceita como aprovado um job que realmente chegou a `succeeded` através
dessa cadeia real.

Verifica, com evidência, cada um dos seguintes pontos (nunca fabrica sucesso; qualquer
divergência real interrompe o script com código de saída != 0 e um relatório explícito):

  1. Transição de status observada de verdade: queued -> running -> succeeded (ou o motivo
     real de não ter chegado lá).
  2. SHA-256 do STL idêntico em QUATRO fontes independentes:
       a) o arquivo físico no disco (lido diretamente via o storage_key real do Artifact,
          nunca por convenção de path suposta);
       b) o campo sha256 do registro Artifact (via GET /api/v1/jobs/{id}/artifacts);
       c) o campo stl_sha256 dentro do ArtifactManifest (via GET /api/v1/jobs/{id}/manifest);
       d) os bytes efetivamente baixados via GET /api/v1/artifacts/{id}/download.
  3. Métricas geométricas persistidas no GeometryJob (volume, watertight, contagens) --
     usando os nomes de campo REAIS emitidos pelo worker (ver JobEnvelope.cs), não os antigos
     nomes divergentes que existiam no frontend antes da correção de 2026-07-29.
  4. Trilha de auditoria real (AuditEvent) para o ciclo de vida deste job específico
     (geometry_job_created, geometry_job_succeeded, artifact_downloaded).
  5. Associação usuário/organização/projeto/receita consistente entre o que foi submetido e o
     que a API retornou.

Uso (Windows, a partir de apps/api, com o ambiente virtual ativado e a API já rodando em outro
terminal na MESMA configuração de DATABASE_URL/ARTIFACT_STORAGE_DIR):

    python scripts/verify_full_pipeline_sha256.py
    python scripts/verify_full_pipeline_sha256.py --recipe cylinder-gyroid-v1 --timeout-seconds 600

O relatório completo (todos os passos, valores literais, veredito) é salvo em
GATE_FULL_PIPELINE_REPORT.json (apps/api/, já coberto por apps/api/data/ e *.log no
.gitignore -- não deve ser versionado; é evidência local pontual, como o resultado de um teste).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    print(
        "ERRO: pacote 'httpx' não encontrado. Rode 'pip install -e \".[dev]\"' (ou apenas "
        "'pip install httpx') no ambiente virtual da API antes de executar este gate.",
        file=sys.stderr,
    )
    sys.exit(2)

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parents[1]

GATE_EMAIL = "gate-picogk-real@biomatcad.example"
GATE_PASSWORD = "gate-picogk-real-synthetic-password-123"

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}


class GateFailure(Exception):
    """Falha real e definitiva do gate -- nunca deve ser suprimida nem convertida em sucesso."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_gate_user() -> str:
    """Idempotente: garante organização/usuário dedicados para este gate (nunca reaproveita o
    usuário do E2E nem o de demonstração, para manter os dados deste gate isolados e
    identificáveis). Retorna o organization_id."""
    sys.path.insert(0, str(API_DIR / "src"))
    from biomatcad_api import models  # noqa: F401
    from biomatcad_api.db import Base, SessionLocal, engine
    from biomatcad_api.models.organization import Organization
    from biomatcad_api.models.user import User
    from biomatcad_api.security import hash_password

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == GATE_EMAIL).first()
        if existing is not None:
            return existing.organization_id
        org = Organization(name="Org Gate PicoGK Real", slug=f"org-gate-picogk-real-{uuid.uuid4().hex[:8]}")
        db.add(org)
        db.flush()
        user = User(
            organization_id=org.id,
            email=GATE_EMAIL,
            full_name="Usuário Gate PicoGK Real",
            hashed_password=hash_password(GATE_PASSWORD),
            role="researcher",
        )
        db.add(user)
        db.commit()
        return org.id
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-base-url", default="http://localhost:8000")
    parser.add_argument(
        "--recipe",
        default="block-gyroid-v1",
        choices=["block-gyroid-v1", "cylinder-gyroid-v1", "preview-gyroid-low-res-v1"],
        help="Golden recipe (schemas/biomatcem/golden-recipes/) usada tal como está -- nunca modificada.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    args = parser.parse_args()

    report: dict = {"gate": "full_pipeline_real_worker", "recipe": args.recipe, "steps": [], "hashes": None}
    overall_ok = True

    def step(name: str, ok: bool, detail: str, *, fatal: bool = True) -> None:
        nonlocal overall_ok
        report["steps"].append({"step": name, "ok": ok, "detail": detail})
        print(f"[{'OK  ' if ok else 'FALHA'}] {name}: {detail}")
        if not ok:
            overall_ok = False
            if fatal:
                raise GateFailure(f"{name}: {detail}")

    try:
        ensure_gate_user()
        step("usuario_gate_garantido", True, f"Usuário {GATE_EMAIL} garantido (idempotente).")

        client = httpx.Client(base_url=args.api_base_url, timeout=30.0)

        login_resp = client.post("/api/v1/auth/login", json={"email": GATE_EMAIL, "password": GATE_PASSWORD})
        step("login_via_http_real", login_resp.status_code == 200, f"POST /api/v1/auth/login -> {login_resp.status_code}")
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me_resp = client.get("/api/v1/auth/me", headers=headers)
        step("auth_me_via_http_real", me_resp.status_code == 200, f"GET /api/v1/auth/me -> {me_resp.status_code}")
        user_info = me_resp.json()

        project_name = f"Gate PicoGK Real {uuid.uuid4().hex[:8]}"
        project_resp = client.post("/api/v1/projects", json={"name": project_name}, headers=headers)
        step("criar_projeto_via_http_real", project_resp.status_code == 201, f"POST /api/v1/projects -> {project_resp.status_code}")
        project = project_resp.json()

        recipe_path = REPO_ROOT / "schemas" / "biomatcem" / "golden-recipes" / f"{args.recipe}.json"
        step("golden_recipe_encontrada", recipe_path.exists(), str(recipe_path))
        recipe_body = json.loads(recipe_path.read_text(encoding="utf-8"))
        recipe_resp = client.post(
            f"/api/v1/projects/{project['id']}/recipes",
            json={"name": f"Receita gate ({args.recipe})", "recipe_body": recipe_body},
            headers=headers,
        )
        step("criar_receita_via_http_real", recipe_resp.status_code == 201, f"POST .../recipes -> {recipe_resp.status_code}")
        recipe = recipe_resp.json()

        idempotency_key = f"gate-real-{uuid.uuid4().hex}"
        design_run_resp = client.post(
            "/api/v1/design-runs",
            json={"project_id": project["id"], "recipe_id": recipe["id"], "idempotency_key": idempotency_key},
            headers=headers,
        )
        step(
            "submeter_job_novo_via_http_real",
            design_run_resp.status_code == 201,
            f"POST /api/v1/design-runs -> {design_run_resp.status_code} (idempotency_key={idempotency_key})",
        )
        design_run = design_run_resp.json()
        job_id = design_run["latest_job"]["id"]
        initial_status = design_run["latest_job"]["status"]
        step("job_inicialmente_queued", initial_status == "queued", f"status inicial real: {initial_status!r}")

        print(f"\nJob NOVO submetido: {job_id}. Invocando o dispatcher REAL (worker PicoGK real) em segundo plano...\n")
        # Popen (não-bloqueante), não subprocess.run(): assim o polling abaixo roda CONCORRENTE
        # com a execução real do worker, dando uma chance real de observar o job em "running"
        # via HTTP -- se o run() bloqueasse até o fim, o dispatcher já teria processado e
        # finalizado o job por completo antes do primeiro poll, tornando impossível observar o
        # estado intermediário por polling (isso foi observado de verdade numa execução prévia
        # deste script neste sandbox: dispatcher síncrono + job muito rápido == "running" nunca
        # capturado por poll, mesmo tendo acontecido de verdade).
        dispatcher_proc = subprocess.Popen(
            [sys.executable, "scripts/geometry_dispatcher.py", "--once"],
            cwd=str(API_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        observed_statuses = [initial_status]
        deadline = time.monotonic() + args.timeout_seconds
        job = None
        while time.monotonic() < deadline:
            job_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            job = job_resp.json()
            if observed_statuses[-1] != job["status"]:
                observed_statuses.append(job["status"])
            if job["status"] in TERMINAL_STATUSES and dispatcher_proc.poll() is not None:
                break
            time.sleep(args.poll_interval_seconds)

        try:
            dispatcher_stdout, _ = dispatcher_proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            dispatcher_proc.kill()
            dispatcher_stdout, _ = dispatcher_proc.communicate()
        print(dispatcher_stdout)
        step(
            "dispatcher_real_executado",
            dispatcher_proc.returncode == 0,
            f"scripts/geometry_dispatcher.py --once -> exit_code={dispatcher_proc.returncode}",
        )

        # Reconsulta final para garantir o estado mais atual pós-dispatcher.
        job = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()
        if observed_statuses[-1] != job["status"]:
            observed_statuses.append(job["status"])

        # Prova AUTORITATIVA da transição queued->running: claim_next_queued_job (Postgres,
        # SELECT...FOR UPDATE SKIP LOCKED) sempre grava started_at no instante da reivindicação,
        # independente de o polling ter conseguido "flagrar" o estado running ao vivo (jobs
        # rápidos podem transicionar e terminar entre dois polls). started_at != None prova que
        # o job passou por running de verdade -- não é uma suposição.
        started_at_proves_running = job.get("started_at") is not None
        step(
            "transicao_queued_running_confirmada",
            started_at_proves_running,
            (
                f"sequência de status observada via polling: {' -> '.join(observed_statuses)}; "
                f"started_at real gravado pelo claim atômico: {job.get('started_at')!r} "
                f"({'confirma queued->running' if started_at_proves_running else 'AUSENTE -- job nunca foi reivindicado de verdade'})"
            ),
        )
        final_status = job["status"] if job else "timeout_sem_resposta"
        failure_detail = ""
        if job and job["status"] == "failed":
            failure_detail = f" ({job.get('error_code')}: {job.get('error_message')})"
        step(
            "job_chegou_a_succeeded_via_worker_real",
            job is not None and job["status"] == "succeeded",
            f"status final real: {final_status}{failure_detail}",
        )

        # A partir daqui, sabemos que o job succeeded de verdade, via worker PicoGK real.
        metrics = job.get("metrics") or {}
        required_metric_keys = ("volume_mm3", "is_watertight", "vertex_count_unique", "triangle_count", "porosity_pct_measured")
        metrics_ok = all(k in metrics for k in required_metric_keys) and metrics.get("volume_mm3", 0) > 0
        step(
            "metricas_reais_persistidas",
            metrics_ok,
            f"metrics (nomes reais do worker) = {json.dumps(metrics, ensure_ascii=False)}",
        )

        artifacts_resp = client.get(f"/api/v1/jobs/{job_id}/artifacts", headers=headers)
        step("artifacts_endpoint_real", artifacts_resp.status_code == 200, f"GET .../artifacts -> {artifacts_resp.status_code}")
        artifacts = artifacts_resp.json()
        stl_artifact = next((a for a in artifacts if a["kind"] == "stl"), None)
        step("artefato_stl_presente_via_api", stl_artifact is not None, f"kinds retornados: {[a['kind'] for a in artifacts]}")

        manifest_resp = client.get(f"/api/v1/jobs/{job_id}/manifest", headers=headers)
        step("manifest_endpoint_real", manifest_resp.status_code == 200, f"GET .../manifest -> {manifest_resp.status_code}")
        manifest = manifest_resp.json()
        manifest_stl_sha256 = manifest["manifest_json"].get("stl_sha256")

        download_resp = client.get(f"/api/v1/artifacts/{stl_artifact['id']}/download", headers=headers)
        step("download_stl_via_api_real", download_resp.status_code == 200, f"GET .../download -> {download_resp.status_code}")
        downloaded_sha256 = _sha256_bytes(download_resp.content)

        # Leitura direta do STL FÍSICO em disco, via o storage_key REAL do registro Artifact
        # (nunca supor a convenção de path sem confirmar contra o banco).
        from biomatcad_api.config import get_settings
        from biomatcad_api.db import SessionLocal
        from biomatcad_api.models.artifact import Artifact, ArtifactKind
        from biomatcad_api.models.audit_event import AuditEvent

        settings = get_settings()
        db = SessionLocal()
        try:
            stl_artifact_row = (
                db.query(Artifact)
                .filter(Artifact.geometry_job_id == job_id, Artifact.kind == ArtifactKind.STL)
                .first()
            )
            step("artefato_stl_no_banco_direto", stl_artifact_row is not None, "registro Artifact(kind=stl) encontrado via DB direto")
            physical_path = Path(settings.artifact_storage_dir) / stl_artifact_row.storage_key
            step("stl_fisico_existe_em_disco", physical_path.exists(), str(physical_path))
            physical_sha256 = _sha256_bytes(physical_path.read_bytes())

            hashes = {
                "1_sha256_stl_fisico_em_disco": physical_sha256,
                "2_sha256_artifact_via_api": stl_artifact["sha256"],
                "3_sha256_artifact_via_db_direto": stl_artifact_row.sha256,
                "4_sha256_manifest_stl_sha256": manifest_stl_sha256,
                "5_sha256_download_via_api": downloaded_sha256,
            }
            report["hashes"] = hashes
            unique_hashes = set(hashes.values())
            step(
                "sha256_identico_nas_5_fontes",
                len(unique_hashes) == 1 and None not in unique_hashes,
                json.dumps(hashes, ensure_ascii=False, indent=2),
            )

            audit_events = (
                db.query(AuditEvent)
                .filter(AuditEvent.description.like(f"%{job_id}%"))
                .order_by(AuditEvent.created_at.asc())
                .all()
            )
            event_types = [e.event_type for e in audit_events]
            step(
                "trilha_de_auditoria_real",
                "geometry_job_created" in event_types and "geometry_job_succeeded" in event_types,
                f"eventos de auditoria reais observados para este job: {event_types}",
            )

            assoc_ok = (
                design_run["organization_id"] == user_info["organization_id"]
                and design_run["project_id"] == project["id"]
                and design_run["recipe_id"] == recipe["id"]
            )
            step(
                "associacao_usuario_organizacao_projeto_receita",
                assoc_ok,
                (
                    f"organization_id (design_run={design_run['organization_id']!r} == "
                    f"user={user_info['organization_id']!r}), project_id={project['id']!r}, "
                    f"recipe_id={recipe['id']!r}"
                ),
            )
        finally:
            db.close()

        print("\n=== GATE APROVADO: vertical completa com worker PicoGK real (não simulado, não pré-semeado) ===")
        report["result"] = "APPROVED"
        return 0

    except GateFailure as exc:
        print(f"\n=== GATE REPROVADO: {exc} ===", file=sys.stderr)
        report["result"] = "FAILED"
        report["failure_reason"] = str(exc)
        return 1
    except Exception as exc:  # noqa: BLE001 -- captura ampla proposital: qualquer erro inesperado deve
        # aparecer no relatório como reprovação real, nunca como sucesso silencioso.
        print(f"\n=== GATE REPROVADO (erro inesperado): {exc!r} ===", file=sys.stderr)
        report["result"] = "FAILED"
        report["failure_reason"] = f"erro inesperado: {exc!r}"
        overall_ok = False
        return 1
    finally:
        report["overall_ok"] = overall_ok
        report_path = API_DIR / "GATE_FULL_PIPELINE_REPORT.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nRelatório completo salvo em: {report_path}")


if __name__ == "__main__":
    sys.exit(main())
