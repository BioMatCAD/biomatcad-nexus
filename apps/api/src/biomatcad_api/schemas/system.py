from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    database: str


class VersionResponse(BaseModel):
    version: str
    environment: str


class OperationalStateItem(BaseModel):
    kind: str
    enabled: bool


class SystemStatusResponse(BaseModel):
    environment: str
    clinical_suite_enabled: bool
    operational_states: list[OperationalStateItem]
    demo_mode: bool
