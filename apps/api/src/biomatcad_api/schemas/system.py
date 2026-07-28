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
    auth_mode: str
    # True somente quando os TRÊS flags da suíte clínica (CLINICAL_TEST, CLINICAL_PILOT,
    # CLINICAL_PRODUCTION) estão efetivamente habilitados. Pesquisa e Laboratório NUNCA entram
    # neste cálculo — são contextos independentes (Incremento 1.1).
    clinical_suite_enabled: bool
    operational_states: list[OperationalStateItem]
    demo_mode: bool
