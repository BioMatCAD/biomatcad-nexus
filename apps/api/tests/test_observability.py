"""Testes de observabilidade real (Incremento 2.2, Seção 7).

Cada teste força uma condição REAL (arquivo no disco, linha no banco, ausência de binário) e
verifica que o estado reportado reflete exatamente essa condição -- nunca testa contra um
estado "inventado". Cobre: healthy/degraded/unavailable/stale/stopped/unknown, heartbeat
expirado, dispatcher parado, worker indisponível, fila vazia/congestionada, e isolamento entre
organizações.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from biomatcad_api.models.geometry_job import JobStatus
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.services.geometry_job_service import create_design_run_and_job
from biomatcad_api.services.observability_service import (
    _dispatcher_status_file_path,
    check_dispatcher,
    check_queue,
    check_storage,
    check_worker,
)
from biomatcad_api.services.recipe_service import validate_and_canonicalize

from .conftest import load_golden_recipe
from .factories import create_researcher, login

REPO_ROOT = Path(__file__).resolve().parents[3]


def _setup_project_and_recipe(db_session, user):
    project = BioMatProject(organization_id=user.organization_id, owner_user_id=user.id, name="Projeto Observabilidade")
    db_session.add(project)
    db_session.flush()

    recipe_body = load_golden_recipe("block-gyroid-v1")
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=user.organization_id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita Observabilidade",
        schema_version=recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db_session.add(recipe)
    db_session.commit()
    return project, recipe


class _FakeSettings:
    """Substituto mínimo de Settings para os testes que só precisam de artifact_storage_dir."""

    def __init__(self, artifact_storage_dir: str) -> None:
        self.artifact_storage_dir = artifact_storage_dir


# ---------------------------------------------------------------------------
# check_dispatcher: cada estado vem de um arquivo de status real e controlado.
# ---------------------------------------------------------------------------


def test_dispatcher_unavailable_quando_status_file_nao_existe(tmp_path):
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    result = check_dispatcher(settings)
    assert result.state == "unavailable"
    assert "não encontrado" in result.detail


def test_dispatcher_healthy_quando_poll_recente(tmp_path):
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    status_file = _dispatcher_status_file_path(settings)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        json.dumps(
            {
                "dispatcher_id": "test:123",
                "pid": 123,
                "state": "running",
                "phase": "idle",
                "last_poll_at": datetime.now(timezone.utc).isoformat(),
                "jobs_processed_total": 5,
                "current_poll_interval_seconds": 3.0,
            }
        ),
        encoding="utf-8",
    )
    result = check_dispatcher(settings)
    assert result.state == "healthy"
    assert result.jobs_processed_total == 5


def test_dispatcher_stale_quando_heartbeat_expirado(tmp_path):
    # Regressão direta pedida pelo usuário: "heartbeat expirado" precisa ser um estado real
    # detectável, não apenas teórico.
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    status_file = _dispatcher_status_file_path(settings)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    old_poll = datetime.now(timezone.utc) - timedelta(seconds=999)
    status_file.write_text(
        json.dumps(
            {
                "dispatcher_id": "test:123",
                "pid": 123,
                "state": "running",
                "phase": "idle",
                "last_poll_at": old_poll.isoformat(),
                "jobs_processed_total": 5,
                "current_poll_interval_seconds": 3.0,
            }
        ),
        encoding="utf-8",
    )
    result = check_dispatcher(settings)
    assert result.state == "stale"
    assert "travado" in result.detail or "morto" in result.detail


def test_dispatcher_stopped_quando_estado_e_stopped(tmp_path):
    # Regressão direta pedida pelo usuário: "dispatcher parado" precisa ser distinguível de
    # "dispatcher travado" (stale) -- são estados semanticamente diferentes.
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    status_file = _dispatcher_status_file_path(settings)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(
        json.dumps(
            {
                "dispatcher_id": "test:123",
                "pid": 123,
                "state": "stopped",
                "phase": "idle",
                "last_poll_at": datetime.now(timezone.utc).isoformat(),
                "jobs_processed_total": 5,
                "current_poll_interval_seconds": 3.0,
            }
        ),
        encoding="utf-8",
    )
    result = check_dispatcher(settings)
    assert result.state == "stopped"


def test_dispatcher_unknown_quando_status_file_corrompido(tmp_path):
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    status_file = _dispatcher_status_file_path(settings)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text("isto não é json válido {{{", encoding="utf-8")
    result = check_dispatcher(settings)
    assert result.state == "unknown"


# ---------------------------------------------------------------------------
# check_worker: worker indisponível (binário ausente) é o estado REAL neste sandbox (o
# runtime PicoGK linux-x64 é bloqueado -- ver ADR-0007/WORKER_STATUS.md -- então o binário
# nunca é compilado aqui). Isso não é simulado: é o estado genuíno do ambiente.
# ---------------------------------------------------------------------------


def test_worker_unavailable_quando_binario_nao_compilado(db_session, tmp_path):
    # Correção real (auditoria da rodada Voronoi / execução Windows 20260806-112714): a versão
    # anterior deste teste usava REPO_ROOT (o checkout real ambiente) assumindo que o binário
    # "genuinamente nunca existe" -- premissa válida SÓ neste sandbox Linux (onde o runtime
    # nativo do PicoGK é bloqueado, ADR-0007, então ninguém roda 'dotnet build' de verdade
    # aqui). Em um ambiente Windows real, onde o worker FOI compilado com sucesso antes da
    # validação (ver worker_dotnet_build no roteiro), REPO_ROOT tem o binário presente de
    # verdade -- e o teste falhava ('assert True is False') não por um bug no produto, mas por
    # uma premissa de ambiente equivocada no próprio teste. Corrigido para usar um repo_root
    # ISOLADO (tmp_path, sem apps/geometry-worker/bin/) -- 'binário não compilado' passa a ser
    # uma condição genuinamente determinística e multiplataforma, independente de o checkout
    # ambiente ter sido buildado ou não.
    result = check_worker(db_session, tmp_path)
    assert result.binary_found is False
    assert result.state == "unavailable"


def test_worker_degraded_quando_heartbeat_de_job_running_expirou(db_session, tmp_path):
    # Prova a condição "heartbeat expirado" para o worker (distinta da do dispatcher acima):
    # cria um job real em status RUNNING com heartbeat_at antigo, e um binário FALSO (arquivo
    # vazio no caminho esperado) para isolar exatamente esta condição sem depender de o
    # PicoGK real estar compilado neste sandbox.
    user = create_researcher(db_session, email="worker-degraded@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    _run, job, _created = create_design_run_and_job(
        db_session,
        organization_id=user.organization_id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="idem-worker-degraded",
    )
    job.status = JobStatus.RUNNING
    job.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=999)
    db_session.commit()

    fake_bin_dir = tmp_path / "apps" / "geometry-worker" / "bin" / "Release" / "net8.0"
    fake_bin_dir.mkdir(parents=True)
    (fake_bin_dir / "BioMatCadGeometryWorker.dll").write_bytes(b"fake-binary-for-test")

    result = check_worker(db_session, tmp_path)
    assert result.binary_found is True
    assert result.state == "degraded"
    assert "travado" in result.detail


# ---------------------------------------------------------------------------
# check_queue: fila vazia e fila congestionada são contagens reais do banco.
# ---------------------------------------------------------------------------


def test_queue_vazia(db_session):
    result = check_queue(db_session)
    assert result.queued_count == 0
    assert result.processing_count == 0


def test_queue_congestionada_com_multiplos_jobs_reais(db_session):
    user = create_researcher(db_session, email="queue-congest@biomatcad.example")
    project, recipe = _setup_project_and_recipe(db_session, user)
    for i in range(5):
        create_design_run_and_job(
            db_session,
            organization_id=user.organization_id,
            project_id=project.id,
            recipe_id=recipe.id,
            material_id=None,
            created_by_user_id=user.id,
            idempotency_key=f"idem-congest-{i}",
        )
    result = check_queue(db_session)
    assert result.queued_count == 5


# ---------------------------------------------------------------------------
# check_storage: probe real de escrita.
# ---------------------------------------------------------------------------


def test_storage_healthy_quando_diretorio_gravavel(tmp_path):
    settings = _FakeSettings(str(tmp_path / "artifacts"))
    result = check_storage(settings)
    assert result.state == "healthy"
    assert result.writable is True


# ---------------------------------------------------------------------------
# Endpoint HTTP completo: autenticação obrigatória + isolamento entre organizações.
# ---------------------------------------------------------------------------


def test_observability_status_requer_autenticacao(client):
    resp = client.get("/api/v1/observability/status")
    assert resp.status_code == 401


def test_observability_status_isola_jobs_entre_organizacoes(client, db_session):
    user_a = create_researcher(db_session, email="org-a@biomatcad.example")
    project_a, recipe_a = _setup_project_and_recipe(db_session, user_a)
    create_design_run_and_job(
        db_session,
        organization_id=user_a.organization_id,
        project_id=project_a.id,
        recipe_id=recipe_a.id,
        material_id=None,
        created_by_user_id=user_a.id,
        idempotency_key="idem-org-a",
    )

    user_b = create_researcher(db_session, email="org-b@biomatcad.example")
    project_b, recipe_b = _setup_project_and_recipe(db_session, user_b)
    create_design_run_and_job(
        db_session,
        organization_id=user_b.organization_id,
        project_id=project_b.id,
        recipe_id=recipe_b.id,
        material_id=None,
        created_by_user_id=user_b.id,
        idempotency_key="idem-org-b",
    )

    from .factories import RESEARCHER_PASSWORD

    token_a = login(client, "org-a@biomatcad.example", RESEARCHER_PASSWORD)
    resp = client.get("/api/v1/observability/status", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    body = resp.json()

    # A organização A só pode ver o próprio job na lista de ativos -- nunca o da organização B.
    design_run_ids_visiveis = {j["design_run_id"] for j in body["jobs_active"]}
    assert len(body["jobs_active"]) == 1
    # A fila (queue) É uma contagem global do sistema, não escopada por organização (reflete o
    # estado real da fila compartilhada) -- por isso reporta os 2 jobs, não 1. Documentado
    # explicitamente aqui para não ser confundido com um vazamento entre organizações.
    assert body["queue"]["queued_count"] == 2
    assert design_run_ids_visiveis  # não vazio -- confirma que o proprio job aparece


def test_observability_status_estrutura_completa(client, db_session):
    create_researcher(db_session, email="full-shape@biomatcad.example")
    from .factories import RESEARCHER_PASSWORD

    token = login(client, "full-shape@biomatcad.example", RESEARCHER_PASSWORD)
    resp = client.get("/api/v1/observability/status", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    for key in ("api", "database", "dispatcher", "worker", "queue", "storage", "versions", "jobs_active", "jobs_failed_recent"):
        assert key in body
    assert body["database"]["state"] == "healthy"
    assert body["api"]["state"] == "healthy"
    assert body["versions"]["schema_geometry_recipe"]
