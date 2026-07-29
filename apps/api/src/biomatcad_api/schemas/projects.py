from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from biomatcad_api.models.project import ProjectStatus


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProjectResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    organization_id: str
    owner_user_id: str
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
