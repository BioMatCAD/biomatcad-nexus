"""GET /api/v1/system/status — estado operacional (Prompt Mestre §3.2, Incremento 1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.operational_state import OperationalState, OperationalStateKind
from biomatcad_api.schemas.system import OperationalStateItem, SystemStatusResponse

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> SystemStatusResponse:
    states_in_db = {s.kind: s.enabled for s in db.query(OperationalState).all()}

    items = []
    clinical_kinds = {
        OperationalStateKind.LABORATORY.value,
        OperationalStateKind.CLINICAL_PILOT.value,
        OperationalStateKind.CLINICAL_PRODUCTION.value,
    }
    clinical_suite_enabled = False
    for kind in OperationalStateKind:
        enabled = states_in_db.get(kind.value, OperationalState.default_enabled(kind))
        items.append(OperationalStateItem(kind=kind.value, enabled=enabled))
        if kind.value in clinical_kinds and enabled:
            clinical_suite_enabled = True

    return SystemStatusResponse(
        environment=settings.environment.value,
        clinical_suite_enabled=clinical_suite_enabled,
        operational_states=items,
        demo_mode=False,
    )
