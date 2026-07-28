"""Ativação de estados operacionais (Incremento 1.1 — correção da semântica da chave mestra).

Dois mecanismos distintos, deliberadamente não intercambiáveis:

1. `POST /operational-state/activate` — contextos INDEPENDENTES (hoje: apenas Laboratório).
   Pesquisa é rejeitada (já habilitada por padrão). Os três flags clínicos são rejeitados aqui
   e devem usar os endpoints de suíte clínica abaixo — impede que alguém ative
   CLINICAL_PRODUCTION isoladamente por engano, contornando a exigência de atomicidade.

2. `POST /clinical-suite/activate` e `POST /clinical-suite/deactivate` — suíte clínica
   (CLINICAL_TEST + CLINICAL_PILOT + CLINICAL_PRODUCTION), sempre em conjunto, mesma
   transação, mesma chave mestra (nunca uma segunda chave), com rollback integral em falha.

Ambos exigem administrador autorizado (`require_admin`) e a chave mestra configurada em
`OPERATIONAL_STATE_MASTER_KEY`. Sem essa variável configurada, toda ativação é recusada (403).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from biomatcad_api.config import Settings, get_settings
from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.operational_state import OperationalStateKind
from biomatcad_api.models.user import User
from biomatcad_api.routers.auth import require_admin
from biomatcad_api.schemas.operational_state import (
    ActivateClinicalSuiteRequest,
    ActivateIndependentStateRequest,
    ActivateIndependentStateResponse,
    ClinicalSuiteChangeResponse,
    DeactivateClinicalSuiteRequest,
)
from biomatcad_api.services.operational_state_service import (
    ClinicalSuiteTransactionError,
    get_or_create_state,
    set_clinical_suite,
)

router = APIRouter(prefix="/api/v1/system", tags=["system"])


def _require_master_key_configured(settings: Settings) -> None:
    if not settings.operational_state_master_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Ativação recusada: nenhuma chave mestra configurada neste ambiente "
                "(OPERATIONAL_STATE_MASTER_KEY). Estados clínicos/laboratoriais permanecem "
                "bloqueados por padrão (Prompt Mestre §3.2)."
            ),
        )


def _check_master_key(settings: Settings, provided: str, *, db: Session, admin: User, target: str) -> None:
    if provided != settings.operational_state_master_key:
        db.add(
            AuditEvent(
                actor_user_id=admin.id,
                organization_id=admin.organization_id,
                event_type="operational_state_activation_denied",
                description=f"Chave mestra inválida ao tentar alterar {target}",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chave mestra inválida.")


@router.post("/operational-state/activate", response_model=ActivateIndependentStateResponse)
def activate_independent_state(
    payload: ActivateIndependentStateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: User = Depends(require_admin),
) -> ActivateIndependentStateResponse:
    if payload.kind == OperationalStateKind.RESEARCH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O estado de Pesquisa já é habilitado por padrão e não requer ativação.",
        )
    if payload.kind != OperationalStateKind.LABORATORY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'{payload.kind.value}' faz parte da suíte clínica e não pode ser ativado "
                "individualmente. Use POST /api/v1/system/clinical-suite/activate, que ativa "
                "CLINICAL_TEST, CLINICAL_PILOT e CLINICAL_PRODUCTION atomicamente."
            ),
        )

    _require_master_key_configured(settings)
    _check_master_key(settings, payload.master_key, db=db, admin=admin, target=payload.kind.value)

    state = get_or_create_state(db, payload.kind)
    state.enabled = True
    state.activated_by = admin.email
    state.justification = payload.justification
    db.add(state)
    db.add(
        AuditEvent(
            actor_user_id=admin.id,
            organization_id=admin.organization_id,
            event_type="operational_state_activated",
            description=f"Estado {payload.kind.value} ativado por {admin.email}",
            event_metadata={"justification": payload.justification},
        )
    )
    db.commit()

    return ActivateIndependentStateResponse(kind=payload.kind.value, enabled=True)


@router.post("/clinical-suite/activate", response_model=ClinicalSuiteChangeResponse)
def activate_clinical_suite(
    payload: ActivateClinicalSuiteRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: User = Depends(require_admin),
) -> ClinicalSuiteChangeResponse:
    _require_master_key_configured(settings)
    _check_master_key(settings, payload.master_key, db=db, admin=admin, target="clinical_suite")

    try:
        result = set_clinical_suite(
            db,
            enabled=True,
            admin_user=admin,
            justification=payload.justification,
            expires_at=payload.expires_at,
        )
    except ClinicalSuiteTransactionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao ativar a suíte clínica; nenhum dos três estados foi alterado (rollback integral).",
        ) from exc

    return ClinicalSuiteChangeResponse(
        clinical_test_enabled=True,
        clinical_pilot_enabled=True,
        clinical_production_enabled=True,
        previous_state=result.previous_state,
        expires_at=payload.expires_at,
    )


@router.post("/clinical-suite/deactivate", response_model=ClinicalSuiteChangeResponse)
def deactivate_clinical_suite(
    payload: DeactivateClinicalSuiteRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    admin: User = Depends(require_admin),
) -> ClinicalSuiteChangeResponse:
    _require_master_key_configured(settings)
    _check_master_key(settings, payload.master_key, db=db, admin=admin, target="clinical_suite")

    try:
        result = set_clinical_suite(
            db,
            enabled=False,
            admin_user=admin,
            justification=payload.justification,
            expires_at=None,
        )
    except ClinicalSuiteTransactionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao desativar a suíte clínica; nenhum dos três estados foi alterado (rollback integral).",
        ) from exc

    return ClinicalSuiteChangeResponse(
        clinical_test_enabled=False,
        clinical_pilot_enabled=False,
        clinical_production_enabled=False,
        previous_state=result.previous_state,
        expires_at=None,
    )
