from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from biomatcad_api.models.geometry_job import JobStatus


class DesignRunCreate(BaseModel):
    project_id: str
    recipe_id: str
    material_id: str | None = None
    idempotency_key: str


class GeometryJobResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    design_run_id: str
    attempt_number: int
    status: JobStatus
    progress_pct: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    worker_version: str | None
    dotnet_version: str | None
    picogk_version: str | None
    metrics: dict[str, Any] | None
    duration_seconds: float | None


class DesignRunResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    organization_id: str
    project_id: str
    recipe_id: str
    material_id: str | None
    idempotency_key: str
    created_at: datetime
    created: bool
    latest_job: GeometryJobResponse
