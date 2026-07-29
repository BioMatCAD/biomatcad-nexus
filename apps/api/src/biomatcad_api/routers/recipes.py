"""Receitas BioMatCEM (Incremento 2.1, item 2/5). Toda validação real acontece aqui via
services/recipe_service.py (JSON Schema Draft 2020-12) -- nunca confia em validação já feita
no frontend."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.geometry_recipe import GeometryRecipe, RecipeStatus
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.routers.projects import _get_project_or_403
from biomatcad_api.schemas.recipes import (
    RecipeCreateRequest,
    RecipeResponse,
    RecipeValidateRequest,
    RecipeValidateResponse,
    RecipeValidationErrorItem,
)
from biomatcad_api.services.recipe_service import (
    RecipeValidationError,
    schema_version,
    validate_and_canonicalize,
    validate_recipe,
)

router = APIRouter(prefix="/api/v1", tags=["recipes"])


def _get_recipe_or_403(db: Session, recipe_id: str, current_user: User) -> GeometryRecipe:
    recipe = db.get(GeometryRecipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receita não encontrada.")
    if recipe.organization_id != current_user.organization_id:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="cross_organization_access_denied",
                description=f"Usuário {current_user.email} tentou acessar receita {recipe_id} de outra organização.",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a esta receita.")
    return recipe


@router.post("/recipes/validate", response_model=RecipeValidateResponse)
def validate_recipe_endpoint(payload: RecipeValidateRequest) -> RecipeValidateResponse:
    errors = validate_recipe(payload.recipe_body)
    checksum = None
    if not errors:
        _, checksum = validate_and_canonicalize(payload.recipe_body)
    return RecipeValidateResponse(
        valid=not errors,
        errors=[RecipeValidationErrorItem(**e) for e in errors],
        checksum_sha256=checksum,
        schema_version=schema_version(),
    )


@router.post("/projects/{project_id}/recipes", response_model=RecipeResponse, status_code=201)
def create_recipe(
    project_id: str,
    payload: RecipeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GeometryRecipe:
    _get_project_or_403(db, project_id, current_user)
    try:
        canonical_str, checksum = validate_and_canonicalize(payload.recipe_body)
    except RecipeValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Receita inválida.", "details": exc.errors},
        ) from exc

    import json

    recipe = GeometryRecipe(
        organization_id=current_user.organization_id,
        project_id=project_id,
        created_by_user_id=current_user.id,
        name=payload.name,
        schema_version=payload.recipe_body["schema_version"],
        canonical_json=json.loads(canonical_str),
        checksum_sha256=checksum,
        version=1,
        status=RecipeStatus.VALIDATED,
    )
    db.add(recipe)
    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="recipe_created",
            description=f"Receita '{payload.name}' criada para o projeto {project_id}.",
        )
    )
    db.commit()
    db.refresh(recipe)
    return recipe


@router.get("/projects/{project_id}/recipes", response_model=list[RecipeResponse])
def list_recipes(
    project_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[GeometryRecipe]:
    _get_project_or_403(db, project_id, current_user)
    return (
        db.query(GeometryRecipe)
        .filter(GeometryRecipe.project_id == project_id)
        .order_by(GeometryRecipe.created_at.desc())
        .all()
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeResponse)
def get_recipe(
    recipe_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> GeometryRecipe:
    return _get_recipe_or_403(db, recipe_id, current_user)


@router.post("/recipes/{recipe_id}/clone", response_model=RecipeResponse, status_code=201)
def clone_recipe(
    recipe_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> GeometryRecipe:
    """Clona uma receita como nova versão -- NUNCA modifica o corpo canônico da original."""
    original = _get_recipe_or_403(db, recipe_id, current_user)
    clone = GeometryRecipe(
        organization_id=original.organization_id,
        project_id=original.project_id,
        created_by_user_id=current_user.id,
        name=f"{original.name} (v{original.version + 1})",
        schema_version=original.schema_version,
        canonical_json=original.canonical_json,
        checksum_sha256=original.checksum_sha256,
        version=original.version + 1,
        parent_recipe_id=original.id,
        status=original.status,
    )
    db.add(clone)
    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="recipe_cloned",
            description=f"Receita {original.id} clonada como {clone.id} (versão {clone.version}).",
        )
    )
    db.commit()
    db.refresh(clone)
    return clone
