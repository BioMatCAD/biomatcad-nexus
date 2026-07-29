from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from biomatcad_api.models.geometry_recipe import RecipeStatus


class RecipeValidationErrorItem(BaseModel):
    path: str
    message: str
    validator: str


class RecipeValidateRequest(BaseModel):
    recipe_body: dict[str, Any]


class RecipeValidateResponse(BaseModel):
    valid: bool
    errors: list[RecipeValidationErrorItem]
    checksum_sha256: str | None = None
    schema_version: str


class RecipeCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    recipe_body: dict[str, Any]


class RecipeResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    organization_id: str
    project_id: str
    name: str
    schema_version: str
    canonical_json: dict[str, Any]
    checksum_sha256: str
    version: int
    parent_recipe_id: str | None
    status: RecipeStatus
    created_at: datetime
