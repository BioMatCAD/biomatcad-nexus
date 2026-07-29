"""Projetos BioMatCAD (Incremento 2.1, item 5) -- autorização estrita por organização."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.project import BioMatProject
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.schemas.projects import ProjectCreateRequest, ProjectResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _get_project_or_403(db: Session, project_id: str, current_user: User) -> BioMatProject:
    project = db.get(BioMatProject, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto não encontrado.")
    if project.organization_id != current_user.organization_id:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="cross_organization_access_denied",
                description=f"Usuário {current_user.email} tentou acessar projeto {project_id} de outra organização.",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este projeto.")
    return project


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BioMatProject:
    project = BioMatProject(
        organization_id=current_user.organization_id,
        owner_user_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    db.add(project)
    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="project_created",
            description=f"Projeto '{payload.name}' criado.",
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[BioMatProject]:
    return (
        db.query(BioMatProject)
        .filter(BioMatProject.organization_id == current_user.organization_id)
        .order_by(BioMatProject.created_at.desc())
        .all()
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> BioMatProject:
    return _get_project_or_403(db, project_id, current_user)
