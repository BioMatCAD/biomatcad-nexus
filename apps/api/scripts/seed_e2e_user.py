#!/usr/bin/env python3
"""Semeia um usuário/organização determinísticos para o teste E2E (Playwright) do frontend
(Incremento 2.1.1, item 12) e, opcionalmente, um job já 'succeeded' (via FakeWorkerClient
rotulado, nunca PicoGK real) para permitir verificar a página de detalhe do job / visualizador
3D sem depender do worker real.

Não há endpoint público de registro nesta versão da API (ver routers/auth.py) -- por isso este
script cria os dados diretamente via os modelos SQLAlchemy, como os testes pytest já fazem.

Uso:
    DATABASE_URL=postgresql+psycopg2://... python3 scripts/seed_e2e_user.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

E2E_EMAIL = "e2e-playwright@biomatcad.example"
E2E_PASSWORD = "e2e-synthetic-password-123"


def main() -> None:
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production")

    from biomatcad_api import models  # noqa: F401
    from biomatcad_api.db import Base, SessionLocal, engine
    from biomatcad_api.models.geometry_job import DesignRun, GeometryJob, JobStatus
    from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
    from biomatcad_api.models.organization import Organization
    from biomatcad_api.models.project import BioMatProject
    from biomatcad_api.models.user import User
    from biomatcad_api.security import hash_password
    from biomatcad_api.services.geometry_job_service import claim_next_queued_job, dispatch_job
    from biomatcad_api.services.recipe_service import validate_and_canonicalize
    from biomatcad_api.services.storage import LocalStorageAdapter
    from biomatcad_api.services.worker_client import WorkerResult

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    existing_user = db.query(User).filter(User.email == E2E_EMAIL).first()
    if existing_user is not None:
        print(json.dumps({"status": "already_seeded", "email": E2E_EMAIL}))
        return

    org = Organization(name="Org E2E Playwright", slug="org-e2e-playwright")
    db.add(org)
    db.flush()

    user = User(
        organization_id=org.id,
        email=E2E_EMAIL,
        full_name="Usuário E2E Playwright",
        hashed_password=hash_password(E2E_PASSWORD),
        role="researcher",
    )
    db.add(user)
    db.commit()

    project = BioMatProject(organization_id=org.id, owner_user_id=user.id, name="Projeto E2E (pré-semeado)")
    db.add(project)
    db.flush()

    recipe_body = {
        "schema_version": "1.0.0",
        "domain": {"shape": "block", "dimensions_mm": {"kind": "block", "x_mm": 10, "y_mm": 10, "z_mm": 10}},
        "topology": {"kind": "gyroid", "cell_size_mm": 2.0, "wall_thickness_mm": 0.4, "isovalue": 0.0, "target_porosity_pct": 60},
        "resolution": {"voxel_size_mm": 0.2},
        "mode": "preview",
        "seed": 42,
        "compute_limits": {"max_duration_seconds": 60, "max_memory_mb": 512, "max_voxel_count": 1000000},
        "output_formats": ["stl"],
    }
    canonical_str, checksum = validate_and_canonicalize(recipe_body)
    recipe = GeometryRecipe(
        organization_id=org.id,
        project_id=project.id,
        created_by_user_id=user.id,
        name="Receita E2E (pré-semeada)",
        schema_version="1.0.0",
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db.add(recipe)
    db.flush()

    design_run = DesignRun(
        organization_id=org.id,
        project_id=project.id,
        recipe_id=recipe.id,
        material_id=None,
        created_by_user_id=user.id,
        idempotency_key="e2e-preseeded-succeeded",
    )
    db.add(design_run)
    db.flush()
    job = GeometryJob(design_run_id=design_run.id, attempt_number=1, status=JobStatus.QUEUED)
    db.add(job)
    db.commit()

    class _FakeWorkerClientForE2ESeed:
        """Test double explícito -- NÃO executa PicoGK real (ver
        apps/geometry-worker/WORKER_STATUS.md). Usado apenas para que a página de detalhe do
        job e o visualizador 3D tenham um job 'succeeded' real para exibir durante o E2E,
        já que a geometria real do PicoGK é o próprio objeto do bloqueio parcial deste
        incremento e é testada separadamente."""

        def execute(self, *, recipe_canonical, job_id, output_dir, cancel_check=None, on_process_started=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            stl_path = output_dir / "e2e-seed.stl"
            stl_path.write_bytes(b"solid e2e-seed\nendsolid e2e-seed\n")
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
                worker_version="0.1.0-e2e-seed-fake",
                dotnet_version="9.0.0",
                picogk_version="2.2.0",
                duration_seconds=0.1,
                stl_sha256="0" * 64,
                platform="fake-platform-for-e2e-seed",
            )

    settings_storage_dir = Path(os.environ.get("ARTIFACT_STORAGE_DIR", "./data/artifacts"))
    storage = LocalStorageAdapter(settings_storage_dir)
    claim_next_queued_job(db, dispatcher_id="e2e-seed-script")
    dispatch_job(
        db,
        job_id=job.id,
        worker_client=_FakeWorkerClientForE2ESeed(),
        storage=storage,
        output_dir=settings_storage_dir / "_work" / job.id,
        repo_root=REPO_ROOT,
    )

    print(json.dumps({
        "status": "seeded",
        "email": E2E_EMAIL,
        "password": E2E_PASSWORD,
        "project_id": project.id,
        "recipe_id": recipe.id,
        "succeeded_job_id": job.id,
    }))
    db.close()


if __name__ == "__main__":
    main()
