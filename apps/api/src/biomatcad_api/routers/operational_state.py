"""POST /api/v1/system/operational-state/activate — contrato de chave mestra.

Prompt Mestre: "não implementar a ativação apenas no frontend". Este endpoint é o único
mecanismo real de ativação de Laboratório/Piloto clínico/Produção clínica. Exige
OPERATIONAL_STATE_MASTER_KEY configurada no ambiente (nunca no cliente). Sem essa variável
configurada, a ativação é sempre recusada — inclusive em desenvolvimento — para que ninguém
dependa de um valor padrão inseguro.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.operational_state import OperationalState, OperationalStateKind
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1/system/operational-state", tags=["system"])


class ActivateOperationalStateRequest(BaseModel):
    kind: OperationalStateKind
    master_key: str
    justification: str = Field(min_length=10, max_length=1000)


class ActivateOperationalStateResponse(BaseModel):
    kind: str
    enabled: bool


@router.post("/activate", response_model=ActivateOperationalStateResponse)
def activate_operational_state(
    payload: ActivateOperationalStateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User = Depends(get_current_user),
) -> ActivateOperationalStateResponse:
    if payload.kind == OperationalStateKind.RESEARCH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O estado de Pesquisa já é habilitado por padrão e não requer ativação.",
        )

    if not settings.operational_state_master_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Ativação recusada: nenhuma chave mestra configurada neste ambiente "
                "(OPERATIONAL_STATE_MASTER_KEY). Estados clínicos/laboratoriais permanecem "
                "bloqueados por padrão (Prompt Mestre §3.2)."
            ),
        )

    if payload.master_key != settings.operational_state_master_key:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="operational_state_activation_denied",
                description=f"Chave mestra inválida ao tentar ativar {payload.kind.value}",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave mestra inválida.")

    state = db.query(OperationalState).filter(OperationalState.kind == payload.kind.value).first()
    if state is None:
        state = OperationalState(kind=payload.kind.value)
        db.add(state)

    state.enabled = True
    state.activated_by = current_user.email
    state.justification = payload.justification

    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="operational_state_activated",
            description=f"Estado {payload.kind.value} ativado por {current_user.email}",
            event_metadata={"justification": payload.justification},
        )
    )
    db.commit()

    return ActivateOperationalStateResponse(kind=payload.kind.value, enabled=True)
