"""GET /api/v1/system/status — estado operacional (Prompt Mestre §3.2, corrigido no Incremento 1.1).

Correção em relação ao Incremento 1: `clinical_suite_enabled` antes misturava Laboratório com a
suíte clínica e usava lógica "qualquer um habilitado" (OR) em vez de "os três simultaneamente"
(AND). Agora usa `services.operational_state_service.get_effective_states`, a mesma fonte de
verdade usada pelos endpoints de ativação, e respeita expiração (`is_effectively_enabled`).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.operational_state import CLINICAL_SUITE_KINDS
from biomatcad_api.schemas.system import OperationalStateItem, SystemStatusResponse
from biomatcad_api.services.operational_state_service import get_effective_states

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def system_status(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> SystemStatusResponse:
    effective = get_effective_states(db)

    items = [OperationalStateItem(kind=kind, enabled=enabled) for kind, enabled in effective.items()]
    clinical_suite_enabled = all(effective[kind.value] for kind in CLINICAL_SUITE_KINDS)

    return SystemStatusResponse(
        environment=settings.environment.value,
        auth_mode=settings.auth_mode,
        clinical_suite_enabled=clinical_suite_enabled,
        operational_states=items,
        demo_mode=False,
    )
