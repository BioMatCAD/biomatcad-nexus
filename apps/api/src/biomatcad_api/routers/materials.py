"""Catálogo de materiais (Incremento 2.1, item 5). Todo valor científico carrega proveniência
completa (ver models/material.py) -- este router não inventa nem infere nenhum valor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from biomatcad_api.db import get_db
from biomatcad_api.models.material import MaterialProperty, MaterialRecord, ScientificReference
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user
from biomatcad_api.schemas.materials import MaterialCreateRequest, MaterialDetail, MaterialSummary

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])


@router.post("", response_model=MaterialDetail, status_code=201)
def create_material(
    payload: MaterialCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialRecord:
    material = MaterialRecord(
        organization_id=current_user.organization_id,
        name=payload.name,
        category=payload.category,
        source_type=payload.source_type,
        description=payload.description,
    )
    db.add(material)
    db.flush()

    for prop in payload.properties:
        db.add(MaterialProperty(material_id=material.id, **prop.model_dump()))
    for ref in payload.references:
        db.add(ScientificReference(material_id=material.id, **ref.model_dump()))

    db.commit()
    db.refresh(material)
    return material


@router.get("", response_model=list[MaterialSummary])
def list_materials(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[MaterialRecord]:
    return (
        db.query(MaterialRecord)
        .filter(MaterialRecord.organization_id == current_user.organization_id)
        .order_by(MaterialRecord.created_at.desc())
        .all()
    )


@router.get("/{material_id}", response_model=MaterialDetail)
def get_material(
    material_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> MaterialRecord:
    material = (
        db.query(MaterialRecord)
        .options(joinedload(MaterialRecord.properties), joinedload(MaterialRecord.references))
        .filter(
            MaterialRecord.id == material_id,
            MaterialRecord.organization_id == current_user.organization_id,
        )
        .first()
    )
    if material is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Material não encontrado.")
    return material
