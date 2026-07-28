"""Regra de negócio da suíte clínica (Incremento 1.1).

Isolado dos routers para poder ser testado diretamente e para deixar explícita a garantia de
atomicidade: `set_clinical_suite` altera os três flags (CLINICAL_TEST, CLINICAL_PILOT,
CLINICAL_PRODUCTION) em uma única transação — todos ou nenhum.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.operational_state import (
    CLINICAL_SUITE_KINDS,
    OperationalState,
    OperationalStateKind,
)
from biomatcad_api.models.user import User


class ClinicalSuiteTransactionError(RuntimeError):
    """Levantado quando a gravação atômica da suíte clínica falha. Nenhuma alteração persiste
    quando esta exceção é levantada — ver `set_clinical_suite`."""


@dataclass
class ClinicalSuiteChangeResult:
    previous_state: dict[str, bool]
    new_state: dict[str, bool]


def get_or_create_state(db: Session, kind: OperationalStateKind) -> OperationalState:
    state = db.query(OperationalState).filter(OperationalState.kind == kind.value).first()
    if state is None:
        state = OperationalState(kind=kind.value, enabled=OperationalState.default_enabled(kind))
        db.add(state)
        db.flush()
    return state


def get_effective_states(db: Session) -> dict[str, bool]:
    """Estado efetivo (considerando expiração) de todos os 5 `OperationalStateKind`."""
    existing = {s.kind: s for s in db.query(OperationalState).all()}
    result: dict[str, bool] = {}
    for kind in OperationalStateKind:
        state = existing.get(kind.value)
        if state is None:
            result[kind.value] = OperationalState.default_enabled(kind)
        else:
            result[kind.value] = state.is_effectively_enabled()
    return result


def set_clinical_suite(
    db: Session,
    *,
    enabled: bool,
    admin_user: User,
    justification: str,
    expires_at: datetime | None,
) -> ClinicalSuiteChangeResult:
    """Ativa ou desativa CLINICAL_TEST, CLINICAL_PILOT e CLINICAL_PRODUCTION simultaneamente,
    na mesma transação. Se qualquer etapa falhar, nenhuma alteração é persistida (rollback
    integral) — a exceção original é relançada como `ClinicalSuiteTransactionError`.

    Não bundla Pesquisa nem Laboratório: esses permanecem contextos independentes, geridos por
    `activate_independent_state` (ver routers/operational_state.py).
    """
    previous_state: dict[str, bool] = {}
    states: list[OperationalState] = []

    try:
        for kind in CLINICAL_SUITE_KINDS:
            state = get_or_create_state(db, kind)
            previous_state[kind.value] = state.is_effectively_enabled()
            states.append(state)

        for state in states:
            state.enabled = enabled
            state.activated_by = admin_user.email
            state.justification = justification
            state.expires_at = expires_at if enabled else None
            db.add(state)

        # flush primeiro: qualquer erro de integridade/constraint aparece aqui, antes do commit,
        # e ainda pode ser revertido sem deixar nenhum dos três estados parcialmente gravado.
        db.flush()

        new_state = {kind.value: enabled for kind in CLINICAL_SUITE_KINDS}

        db.add(
            AuditEvent(
                actor_user_id=admin_user.id,
                organization_id=admin_user.organization_id,
                event_type="clinical_suite_activated" if enabled else "clinical_suite_deactivated",
                description=(
                    f"Suíte clínica {'ativada' if enabled else 'desativada'} por {admin_user.email}"
                ),
                event_metadata={
                    "previous_state": previous_state,
                    "new_state": new_state,
                    "justification": justification,
                    "administrator": admin_user.email,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ClinicalSuiteTransactionError(
            "Falha ao aplicar a suíte clínica atomicamente; nenhuma alteração foi persistida."
        ) from exc

    return ClinicalSuiteChangeResult(previous_state=previous_state, new_state=new_state)
