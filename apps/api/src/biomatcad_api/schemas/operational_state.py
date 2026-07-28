from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from biomatcad_api.models.operational_state import OperationalStateKind


class ActivateIndependentStateRequest(BaseModel):
    """Para contextos independentes (hoje: apenas Laboratório — Pesquisa já vem habilitada e
    os três flags clínicos usam os endpoints dedicados de suíte clínica, não este)."""

    kind: OperationalStateKind
    master_key: str
    justification: str = Field(min_length=10, max_length=1000)


class ActivateIndependentStateResponse(BaseModel):
    kind: str
    enabled: bool


class ActivateClinicalSuiteRequest(BaseModel):
    master_key: str
    justification: str = Field(min_length=10, max_length=1000)
    expires_at: datetime | None = Field(
        default=None,
        description="Expiração opcional. Após esse instante, os três flags passam a ser lidos como desabilitados.",
    )


class DeactivateClinicalSuiteRequest(BaseModel):
    master_key: str
    justification: str = Field(min_length=10, max_length=1000)


class ClinicalSuiteChangeResponse(BaseModel):
    clinical_test_enabled: bool
    clinical_pilot_enabled: bool
    clinical_production_enabled: bool
    previous_state: dict[str, bool]
    expires_at: datetime | None
