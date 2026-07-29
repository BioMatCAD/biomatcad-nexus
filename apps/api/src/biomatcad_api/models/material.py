"""Modelos de material científico (Incremento 2.1, item 1).

Todo valor científico (MaterialProperty) registra valor, unidade, fonte, referência/DOI,
método, faixa/incerteza (quando conhecida), versão e status de revisão — nenhuma propriedade é
inventada; usar dados sintéticos claramente rotulados (source_type=SYNTHETIC) ou valores
expressamente presentes nos documentos-fonte auditados (source_type=LITERATURE, com
reference_id apontando para ScientificReference).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biomatcad_api.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MaterialSourceType(str, PyEnum):
    SYNTHETIC = "synthetic"
    LITERATURE = "literature"


class ReviewStatus(str, PyEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    DEPRECATED = "deprecated"


class MaterialRecord(Base):
    """Um material biocompatível documentado (ex.: beta-TCP, HAp, Ti-6Al-4V)."""

    __tablename__ = "material_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[MaterialSourceType] = mapped_column(
        Enum(MaterialSourceType, native_enum=False), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False), nullable=False, default=ReviewStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    properties: Mapped[list[MaterialProperty]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    references: Mapped[list[ScientificReference]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class MaterialProperty(Base):
    """Um valor científico único de uma propriedade de material, com proveniência completa."""

    __tablename__ = "material_properties"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    material_id: Mapped[str] = mapped_column(String(36), ForeignKey("material_records.id"), nullable=False)
    property_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scientific_references.id"), nullable=True
    )
    method: Mapped[str | None] = mapped_column(String(300), nullable=True)
    uncertainty_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, native_enum=False), nullable=False, default=ReviewStatus.DRAFT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    material: Mapped[MaterialRecord] = relationship(back_populates="properties")


class ScientificReference(Base):
    """Referência bibliográfica (DOI/citação) associada a um material."""

    __tablename__ = "scientific_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    material_id: Mapped[str] = mapped_column(String(36), ForeignKey("material_records.id"), nullable=False)
    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_document: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    material: Mapped[MaterialRecord] = relationship(back_populates="references")
