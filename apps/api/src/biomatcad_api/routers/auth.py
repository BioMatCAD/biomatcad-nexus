"""POST /api/v1/auth/login, GET /api/v1/auth/me — autenticação mínima real (Incremento 1).

Limitações: sem MFA/WebAuthn, sem revogação de sessão, sem RBAC completo — ver security.py e
REQUIREMENTS_MATRIX.md (PM-ONLY-04, backlog).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.user import User
from biomatcad_api.schemas.auth import LoginRequest, LoginResponse, UserResponse
from biomatcad_api.security import create_access_token, decode_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email, User.is_active.is_(True)).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        db.add(
            AuditEvent(
                event_type="login_failed",
                description=f"Tentativa de login malsucedida para {payload.email}",
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")

    token, expires_in = create_access_token(subject=user.id, extra_claims={"org": user.organization_id})
    db.add(
        AuditEvent(
            actor_user_id=user.id,
            organization_id=user.organization_id,
            event_type="login_succeeded",
            description=f"Login bem-sucedido para {user.email}",
        )
    )
    db.commit()
    return LoginResponse(access_token=token, expires_in=expires_in)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente.")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido ou expirado.") from exc

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inválido.")
    return user


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organization_id=current_user.organization_id,
    )
