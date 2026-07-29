"""Receita BioMatCEM persistida (Incremento 2.1, item 2).

O corpo canônico (canonical_json) e o checksum são calculados por
`services/recipe_service.py` — este modelo apenas persiste o resultado já validado, nunca
valida por si mesmo (a validação real acontece antes, contra o JSON Schema).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from biomatcad_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RecipeStatus(str, PyEnum):
    DRAFT = "draft"
    VALIDATED = "validated"


class GeometryRecipe(Base):
    __tablename__ = "geometry_recipes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("biomat_projects.id"), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False)
    canonical_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_recipe_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("geometry_recipes.id"), nullable=True
    )
    status: Mapped[RecipeStatus] = mapped_column(
        Enum(RecipeStatus, native_enum=False), nullable=False, default=RecipeStatus.VALIDATED
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
