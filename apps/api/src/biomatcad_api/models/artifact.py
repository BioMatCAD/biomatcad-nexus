"""Artifact/ArtifactManifest — artefatos de execução e envelope de reprodutibilidade
(Incremento 2.1, item 7)."""
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


class ArtifactKind(str, PyEnum):
    STL = "stl"
    VDB = "vdb"
    THUMBNAIL = "thumbnail"
    MANIFEST = "manifest"
    LOG = "log"


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    geometry_job_id: Mapped[str] = mapped_column(String(36), ForeignKey("geometry_jobs.id"), nullable=False)
    kind: Mapped[ArtifactKind] = mapped_column(Enum(ArtifactKind, native_enum=False), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class ArtifactManifest(Base):
    __tablename__ = "artifact_manifests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    geometry_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("geometry_jobs.id"), nullable=False, unique=True
    )
    manifest_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
