from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from biomatcad_api.models.material import MaterialSourceType, ReviewStatus


class MaterialPropertyCreate(BaseModel):
    property_name: str
    value: float
    unit: str
    source: str
    reference_id: str | None = None
    method: str | None = None
    uncertainty_low: float | None = None
    uncertainty_high: float | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT


class MaterialPropertyResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    property_name: str
    value: float
    unit: str
    source: str
    reference_id: str | None
    method: str | None
    uncertainty_low: float | None
    uncertainty_high: float | None
    version: int
    review_status: ReviewStatus
    created_at: datetime


class ScientificReferenceCreate(BaseModel):
    citation_text: str
    doi: str | None = None
    url: str | None = None
    source_document: str | None = None
    page_reference: str | None = None


class ScientificReferenceResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    citation_text: str
    doi: str | None
    url: str | None
    source_document: str | None
    page_reference: str | None
    created_at: datetime


class MaterialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str
    source_type: MaterialSourceType
    description: str | None = None
    properties: list[MaterialPropertyCreate] = Field(default_factory=list)
    references: list[ScientificReferenceCreate] = Field(default_factory=list)


class MaterialSummary(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    name: str
    category: str
    source_type: MaterialSourceType
    review_status: ReviewStatus
    created_at: datetime


class MaterialDetail(MaterialSummary):
    description: str | None
    properties: list[MaterialPropertyResponse]
    references: list[ScientificReferenceResponse]
