"""DesignRun/GeometryJob (Incremento 2.1, item 4/5): criação idempotente, status, cancelamento,
retry, histórico -- autorização estrita por organização."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_job import DesignRun, GeometryJob
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.routers.projects import _get_project_or_403
from biomatcad_api.schemas.jobs import DesignRunCreate, DesignRunResponse, GeometryJobResponse
from biomatcad_api.services.geometry_job_service import (
    JobTransitionError,
    cancel_job,
    create_design_run_and_job,
    retry_job,
)

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _get_design_run_or_403(db: Session, design_run_id: str, current_user: User) -> DesignRun:
    design_run = db.get(DesignRun, design_run_id)
    if design_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design run não encontrado.")
    if design_run.organization_id != current_user.organization_id:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="cross_organization_access_denied",
                description=f"Usuário {current_user.email} tentou acessar design_run {design_run_id} de outra organização.",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este design run.")
    return design_run


def _get_job_or_403(db: Session, job_id: str, current_user: User) -> GeometryJob:
    job = db.get(GeometryJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job não encontrado.")
    design_run = db.get(DesignRun, job.design_run_id)
    assert design_run is not None
    if design_run.organization_id != current_user.organization_id:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="cross_organization_access_denied",
                description=f"Usuário {current_user.email} tentou acessar job {job_id} de outra organização.",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este job.")
    return job


@router.get("/projects/{project_id}/design-runs", response_model=list[DesignRunResponse])
def list_design_runs_for_project(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DesignRunResponse]:
    """Histórico de execuções de um projeto (Incremento 2.1, item 6)."""
    _get_project_or_403(db, project_id, current_user)
    runs = (
        db.query(DesignRun)
        .filter(DesignRun.project_id == project_id)
        .order_by(DesignRun.created_at.desc())
        .all()
    )
    result = []
    for design_run in runs:
        if not design_run.jobs:
            continue
        latest_job = max(design_run.jobs, key=lambda j: j.attempt_number)
        result.append(
            DesignRunResponse(
                id=design_run.id,
                organization_id=design_run.organization_id,
                project_id=design_run.project_id,
                recipe_id=design_run.recipe_id,
                material_id=design_run.material_id,
                idempotency_key=design_run.idempotency_key,
                created_at=design_run.created_at,
                created=False,
                latest_job=GeometryJobResponse.model_validate(latest_job),
            )
        )
    return result


@router.post("/design-runs", response_model=DesignRunResponse, status_code=status.HTTP_201_CREATED)
def create_design_run(
    payload: DesignRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DesignRunResponse:
    _get_project_or_403(db, payload.project_id, current_user)
    design_run, job, created = create_design_run_and_job(
        db,
        organization_id=current_user.organization_id,
        project_id=payload.project_id,
        recipe_id=payload.recipe_id,
        material_id=payload.material_id,
        created_by_user_id=current_user.id,
        idempotency_key=payload.idempotency_key,
    )
    return DesignRunResponse(
        id=design_run.id,
        organization_id=design_run.organization_id,
        project_id=design_run.project_id,
        recipe_id=design_run.recipe_id,
        material_id=design_run.material_id,
        idempotency_key=design_run.idempotency_key,
        created_at=design_run.created_at,
        created=created,
        latest_job=GeometryJobResponse.model_validate(job),
    )


@router.get("/design-runs/{design_run_id}", response_model=DesignRunResponse)
def get_design_run(
    design_run_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> DesignRunResponse:
    design_run = _get_design_run_or_403(db, design_run_id, current_user)
    latest_job = max(design_run.jobs, key=lambda j: j.attempt_number)
    return DesignRunResponse(
        id=design_run.id,
        organization_id=design_run.organization_id,
        project_id=design_run.project_id,
        recipe_id=design_run.recipe_id,
        material_id=design_run.material_id,
        idempotency_key=design_run.idempotency_key,
        created_at=design_run.created_at,
        created=False,
        latest_job=GeometryJobResponse.model_validate(latest_job),
    )


@router.post("/design-runs/{design_run_id}/retry", response_model=GeometryJobResponse)
def retry_design_run(
    design_run_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> GeometryJob:
    design_run = _get_design_run_or_403(db, design_run_id, current_user)
    try:
        return retry_job(db, design_run=design_run, requested_by_user_id=current_user.id)
    except JobTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=GeometryJobResponse)
def get_job(
    job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> GeometryJob:
    return _get_job_or_403(db, job_id, current_user)


@router.post("/jobs/{job_id}/cancel", response_model=GeometryJobResponse)
def cancel_job_endpoint(
    job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> GeometryJob:
    job = _get_job_or_403(db, job_id, current_user)
    try:
        return cancel_job(db, job=job, cancelled_by_user_id=current_user.id)
    except JobTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
