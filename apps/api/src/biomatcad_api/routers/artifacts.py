"""Artefatos, manifesto e métricas de um GeometryJob (Incremento 2.1, item 5/7)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from biomatcad_api.config import get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.artifact import Artifact, ArtifactManifest
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.routers.jobs import _get_job_or_403
from biomatcad_api.schemas.artifacts import ArtifactResponse, ManifestResponse
from biomatcad_api.services.storage import LocalStorageAdapter

router = APIRouter(prefix="/api/v1", tags=["artifacts"])


def _storage() -> LocalStorageAdapter:
    settings = get_settings()
    return LocalStorageAdapter(Path(settings.artifact_storage_dir))


@router.get("/jobs/{job_id}/artifacts", response_model=list[ArtifactResponse])
def list_job_artifacts(
    job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[Artifact]:
    _get_job_or_403(db, job_id, current_user)
    return db.query(Artifact).filter(Artifact.geometry_job_id == job_id).all()


@router.get("/artifacts/{artifact_id}/download")
def download_artifact(
    artifact_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> Response:
    artifact = db.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artefato não encontrado.")
    _get_job_or_403(db, artifact.geometry_job_id, current_user)

    storage = _storage()
    if not storage.exists(artifact.storage_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo do artefato não encontrado no armazenamento.")
    data = storage.get(artifact.storage_key)

    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="artifact_downloaded",
            description=f"Artefato {artifact.id} ({artifact.kind.value}) baixado.",
        )
    )
    db.commit()
    return Response(content=data, media_type="application/octet-stream")


@router.get("/jobs/{job_id}/manifest", response_model=ManifestResponse)
def get_job_manifest(
    job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> ArtifactManifest:
    _get_job_or_403(db, job_id, current_user)
    manifest = db.query(ArtifactManifest).filter(ArtifactManifest.geometry_job_id == job_id).first()
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manifesto ainda não disponível (job não concluído com sucesso).")
    return manifest


@router.get("/jobs/{job_id}/metrics")
def get_job_metrics(
    job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> dict:
    job = _get_job_or_403(db, job_id, current_user)
    if job.metrics is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Métricas ainda não disponíveis (job não concluído com sucesso).")
    return job.metrics
