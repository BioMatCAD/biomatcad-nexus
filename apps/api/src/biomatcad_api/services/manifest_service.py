"""Manifesto de reprodutibilidade (Incremento 2.1, item 7; Incremento 2.1.1, itens 10 e 11).

Todo GeometryJob bem-sucedido recebe um manifesto contendo tudo necessário para reproduzir e
AUDITAR a execução: receita canônica, versão do schema, usuário/organização/projeto/material/
design_run, commit Git, versões do worker/.NET/PicoGK, plataforma/hardware, parâmetros
SOLICITADOS vs. EFETIVAMENTE utilizados (espessura/isovalor/porosidade/seed/voxel size), lista
completa de artefatos (tipo, caminho lógico, tamanho, sha256), status de validação do STL,
watertight, duração, métricas e timestamp UTC.

Sem circularidade de checksum (item 10): o SHA-256 do PRÓPRIO manifesto (manifest_sha256) NUNCA
é incluído dentro do conteúdo JSON que ele mesmo descreve -- é calculado sobre o conteúdo já
fechado e armazenado em uma coluna separada (ArtifactManifest.manifest_sha256) e também como
Artifact.sha256 do artefato de tipo MANIFEST, nunca embutido recursivamente no manifest_json.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from biomatcad_api.models.artifact import Artifact, ArtifactKind, ArtifactManifest
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob
from biomatcad_api.models.geometry_recipe import GeometryRecipe
from biomatcad_api.models.user import User
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
    effective_parameters: dict | None = None,
    platform_info: str | None = None,
    stl_sha256: str | None = None,
) -> ArtifactManifest:
    created_by_user = db.get(User, design_run.created_by_user_id)

    # Artefatos já persistidos para este job ANTES do manifesto (STL, thumbnail se houver) --
    # listados explicitamente no corpo do manifesto (item 10: "lista completa de artefatos ...
    # tipo, caminho lógico, tamanho e SHA-256 de cada"). O próprio artefato MANIFEST ainda não
    # existe neste ponto (evita a circularidade descrita no docstring do módulo).
    existing_artifacts = db.query(Artifact).filter(Artifact.geometry_job_id == job.id).all()
    artifacts_summary = [
        {
            "kind": a.kind.value,
            "logical_path": a.storage_key,
            "size_bytes": a.size_bytes,
            "sha256": a.sha256,
        }
        for a in existing_artifacts
    ]

    metrics = job.metrics or {}

    manifest_dict = {
        "job_id": job.id,
        "design_run_id": design_run.id,
        "organization_id": design_run.organization_id,
        "project_id": design_run.project_id,
        "material_id": design_run.material_id,
        "recipe_id": recipe.id,
        "created_by_user_id": design_run.created_by_user_id,
        "created_by_user_email": created_by_user.email if created_by_user is not None else None,
        "recipe_canonical": recipe.canonical_json,
        "schema_version": recipe.schema_version,
        "recipe_checksum_sha256": recipe.checksum_sha256,
        "git_commit": _current_git_commit(repo_root),
        "worker_version": versions.get("worker_version"),
        "dotnet_version": versions.get("dotnet_version"),
        "picogk_version": versions.get("picogk_version"),
        "platform": platform_info,
        "hardware_info": job.hardware_info,
        "effective_parameters": effective_parameters,
        "duration_seconds": duration_seconds,
        "metrics": metrics,
        "stl_validation_passed_after_write": metrics.get("stl_reload_validation_passed"),
        "is_watertight": metrics.get("is_watertight"),
        "stl_sha256": stl_sha256,
        "artifacts": artifacts_summary,
        "logs_sanitized": {
            "note": (
                "stdout/stderr brutos do worker nunca são incluídos aqui (podem conter caminhos "
                "absolutos do sistema de arquivos) -- ver AuditEvent para eventos de ciclo de "
                "vida do job; erro estruturado (se falhou) está em GeometryJob.error_code/"
                "error_message, já sanitizado."
            ),
            "job_status": job.status.value,
        },
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
