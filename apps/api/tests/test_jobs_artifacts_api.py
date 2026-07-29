"""Testes de API para design-runs/jobs/artefatos (Incremento 2.1, item 8): idempotência via
HTTP, cancelamento, download de artefato, manifesto e métricas -- usando um FakeWorkerClient
para exercitar o caminho de sucesso (ver nota de transparência em
test_geometry_job_orchestration.py sobre por que isso não é uma alegação de execução real do
PicoGK)."""
from __future__ import annotations

from pathlib import Path

from biomatcad_api.config import get_settings
from biomatcad_api.services.geometry_job_service import dispatch_job
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import WorkerResult

from .factories import RESEARCHER_PASSWORD, create_researcher, login

GOOD_RECIPE = {
    "schema_version": "1.0.0",
    "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
    "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "isovalue": 0.0, "target_porosity_pct": 60},
    "resolution": {"voxel_size_mm": 0.2},
    "mode": "preview",
    "seed": 42,
    "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
    "output_formats": ["stl"],
}


def _auth_header(client, db_session, email):
    create_researcher(db_session, email=email)
    token = login(client, email, RESEARCHER_PASSWORD)
    return {"Authorization": f"Bearer {token}"}


def _setup_project_and_recipe(client, headers):
    project_id = client.post("/api/v1/projects", headers=headers, json={"name": "Projeto Jobs"}).json()["id"]
    recipe = client.post(
        f"/api/v1/projects/{project_id}/recipes", headers=headers, json={"name": "Receita Jobs", "recipe_body": GOOD_RECIPE}
    ).json()
    return project_id, recipe["id"]


def test_design_run_creation_is_idempotent_via_http(client, db_session):
    headers = _auth_header(client, db_session, "jobapi1@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers)

    body = {"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-idem-1"}
    r1 = client.post("/api/v1/design-runs", headers=headers, json=body)
    r2 = client.post("/api/v1/design-runs", headers=headers, json=body)

    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["created"] is True
    assert r2.json()["created"] is False
    assert r1.json()["id"] == r2.json()["id"]
    assert r1.json()["latest_job"]["status"] == "queued"


def test_job_status_progress_and_cancel_via_http(client, db_session):
    headers = _auth_header(client, db_session, "jobapi2@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers)

    r = client.post(
        "/api/v1/design-runs", headers=headers,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-cancel-1"},
    )
    job_id = r.json()["latest_job"]["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "queued"
    assert status_resp.json()["progress_pct"] == 0

    cancel_resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"

    second_cancel = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert second_cancel.status_code == 409


def test_job_from_other_organization_is_not_accessible(client, db_session):
    headers_a = _auth_header(client, db_session, "jobcrossa@biomatcad.example")
    headers_b = _auth_header(client, db_session, "jobcrossb@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers_a)

    r = client.post(
        "/api/v1/design-runs", headers=headers_a,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-cross-1"},
    )
    job_id = r.json()["latest_job"]["id"]

    resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers_b)
    assert resp.status_code == 403


def test_manifest_and_metrics_are_404_before_success(client, db_session):
    headers = _auth_header(client, db_session, "jobapi3@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers)
    r = client.post(
        "/api/v1/design-runs", headers=headers,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-404-1"},
    )
    job_id = r.json()["latest_job"]["id"]

    assert client.get(f"/api/v1/jobs/{job_id}/manifest", headers=headers).status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/metrics", headers=headers).status_code == 404
    assert client.get(f"/api/v1/jobs/{job_id}/artifacts", headers=headers).json() == []


class _FakeWorkerClient:
    def __init__(self, stl_content: bytes):
        self.stl_content = stl_content

    def execute(self, *, recipe_canonical, job_id, output_dir):
        output_dir.mkdir(parents=True, exist_ok=True)
        stl_path = output_dir / "fake.stl"
        stl_path.write_bytes(self.stl_content)
        return WorkerResult(
            stl_path=stl_path, thumbnail_path=None,
            metrics={
                "bounding_box_mm": [[0, 0, 0], [10, 10, 10]], "volume_mm3": 400.0,
                "porosity_pct_estimated": 60.0, "surface_area_mm2": 950.5,
                "vertex_count": 300, "triangle_count": 100, "is_watertight": True,
            },
            worker_version="0.1.0-fake-test-double", dotnet_version="9.0.0", picogk_version="2.2.0",
            duration_seconds=0.1,
        )


def test_manifest_metrics_artifacts_and_download_after_success(client, db_session, tmp_path, monkeypatch):
    # A API lê o diretório de artefatos de Settings.artifact_storage_dir (cache via
    # lru_cache). Apontamos para o mesmo tmp_path usado por dispatch_job abaixo, para que o
    # endpoint de download leia do mesmo lugar onde o teste gravou o artefato "sucedido".
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    headers = _auth_header(client, db_session, "jobapi4@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers)
    r = client.post(
        "/api/v1/design-runs", headers=headers,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-success-1"},
    )
    job_id = r.json()["latest_job"]["id"]

    storage = LocalStorageAdapter(tmp_path / "artifacts")
    dispatch_job(
        db_session, job_id=job_id, worker_client=_FakeWorkerClient(b"solid demo\nendsolid demo\n"),
        storage=storage, output_dir=tmp_path / "workdir", repo_root=Path(__file__).resolve().parents[3],
    )

    metrics_resp = client.get(f"/api/v1/jobs/{job_id}/metrics", headers=headers)
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["volume_mm3"] == 400.0

    manifest_resp = client.get(f"/api/v1/jobs/{job_id}/manifest", headers=headers)
    assert manifest_resp.status_code == 200
    assert manifest_resp.json()["manifest_json"]["seed"] == 42

    artifacts = client.get(f"/api/v1/jobs/{job_id}/artifacts", headers=headers).json()
    kinds = {a["kind"] for a in artifacts}
    assert "stl" in kinds and "manifest" in kinds

    stl_artifact = next(a for a in artifacts if a["kind"] == "stl")
    download_resp = client.get(f"/api/v1/artifacts/{stl_artifact['id']}/download", headers=headers)
    assert download_resp.status_code == 200
    assert download_resp.content == b"solid demo\nendsolid demo\n"

    get_settings.cache_clear()  # não deixa a configuração de teste vazar para outros testes


def test_list_design_runs_for_project_returns_history_ordered_recent_first(client, db_session):
    headers = _auth_header(client, db_session, "jobapi5@biomatcad.example")
    project_id, recipe_id = _setup_project_and_recipe(client, headers)

    client.post(
        "/api/v1/design-runs", headers=headers,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-history-1"},
    )
    client.post(
        "/api/v1/design-runs", headers=headers,
        json={"project_id": project_id, "recipe_id": recipe_id, "idempotency_key": "http-history-2"},
    )

    resp = client.get(f"/api/v1/projects/{project_id}/design-runs", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    keys = {"http-history-1", "http-history-2"}
    assert {run["idempotency_key"] for run in body} == keys
    assert all(run["latest_job"]["status"] == "queued" for run in body)


def test_list_design_runs_for_project_denied_for_other_organization(client, db_session):
    headers_a = _auth_header(client, db_session, "jobapi6a@biomatcad.example")
    headers_b = _auth_header(client, db_session, "jobapi6b@biomatcad.example")
    project_id, _recipe_id = _setup_project_and_recipe(client, headers_a)

    resp = client.get(f"/api/v1/projects/{project_id}/design-runs", headers=headers_b)
    assert resp.status_code == 403
