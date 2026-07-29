from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from biomatcad_api.models.artifact import ArtifactKind


class ArtifactResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    geometry_job_id: str
    kind: ArtifactKind
    sha256: str
    size_bytes: int
    created_at: datetime


class ManifestResponse(BaseModel):
    id: str
    geometry_job_id: str
    manifest_json: dict[str, Any]
    manifest_sha256: str
    created_at: datetime
