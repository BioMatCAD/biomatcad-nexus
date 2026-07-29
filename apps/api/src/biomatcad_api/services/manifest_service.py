"""Manifesto de reprodutibilidade (Incremento 2.1, item 7).

Todo GeometryJob bem-sucedido recebe um manifesto contendo tudo necessário para reproduzir a
execução: receita canônica, versão do schema, usuário/organização, commit Git, versões do
worker/.NET/PicoGK, seed, hardware, duração, métricas e checksum do próprio manifesto.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from biomatcad_api.models.artifact import Artifact, ArtifactKind, ArtifactManifest
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob
from biomatcad_api.models.geometry_recipe import GeometryRecipe
from biomatcad_api.services.recipe_service import canonicalize_recipe
from biomatcad_api.services.storage import StorageAdapter, sha256_of_bytes


def _current_git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=5, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def build_and_store_manifest(
    db: Session,
    *,
    job: GeometryJob,
    design_run: DesignRun,
    recipe: GeometryRecipe,
    versions: dict,
    duration_seconds: float,
    storage: StorageAdapter,
    repo_root: Path,
) -> ArtifactManifest:
    import json

    manifest_dict = {
        "job_id": job.id,
        "design_run_id": design_run.id,
        "recipe_canonical": recipe.canonical_json,
        "schema_version": recipe.schema_version,
        "recipe_checksum_sha256": recipe.checksum_sha256,
        "organization_id": design_run.organization_id,
        "created_by_user_id": design_run.created_by_user_id,
        "git_commit": _current_git_commit(repo_root),
        "worker_version": versions.get("worker_version"),
        "dotnet_version": versions.get("dotnet_version"),
        "picogk_version": versions.get("picogk_version"),
        "seed": recipe.canonical_json.get("seed"),
        "hardware_info": job.hardware_info,
        "duration_seconds": duration_seconds,
        "metrics": job.metrics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_json_str = canonicalize_recipe(manifest_dict)
    manifest_sha256 = sha256_of_bytes(manifest_json_str.encode("utf-8"))

    manifest_key = f"jobs/{job.id}/manifest.json"
    storage.put(manifest_key, manifest_json_str.encode("utf-8"))
    db.add(
        Artifact(
            geometry_job_id=job.id,
            kind=ArtifactKind.MANIFEST,
            storage_key=manifest_key,
            sha256=manifest_sha256,
            size_bytes=len(manifest_json_str.encode("utf-8")),
        )
    )

    manifest = ArtifactManifest(
        geometry_job_id=job.id,
        manifest_json=json.loads(manifest_json_str),
        manifest_sha256=manifest_sha256,
    )
    db.add(manifest)
    db.commit()
    db.refresh(manifest)
    return manifest
