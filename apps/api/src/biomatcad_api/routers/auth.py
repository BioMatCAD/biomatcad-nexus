"""POST /api/v1/auth/login, GET /api/v1/auth/me, POST /api/v1/auth/logout.

Classificação explícita (Incremento 1.1, Prompt Mestre §9): este é o modo `DEV_AUTH`
(`AUTH_MODE` em config.py) — e-mail/senha com bcrypt, JWT stateless de curta duração, sessão
mantida em memória no frontend. NÃO equivale à arquitetura final exigida (OIDC/OAuth 2.1,
Authorization Code + PKCE, MFA por TOTP e WebAuthn/passkeys, step-up authentication). Esses
requisitos permanecem pendentes e rastreados em REQUIREMENTS_MATRIX.md (PM-ONLY-04). DEV_AUTH
não deve ser usado com dados clínicos reais em nenhuma circunstância.

`/logout` é simbólico: como o JWT é stateless e não há blocklist de tokens nesta fase, o
endpoint apenas registra o evento de auditoria — o token em si continua criptograficamente
válido até expirar. Revogação real de sessão é backlog (PM-ONLY-04).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from biomatcad_api.db import get_db
from biomatcad_api.models.audit_event import AuditEvent
from biomatcad_api.models.user import User
from biomatcad_api.schemas.auth import LoginRequest, LoginResponse, LogoutResponse, UserResponse
from biomatcad_api.security import create_access_token, decode_access_token, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)

# Papéis considerados administrativos para fins deste incremento. Não é o RBAC/ABAC completo do
# Prompt Mestre §9 (17 perfis institucionais) — é um controle mínimo suficiente para não deixar
# a ativação da suíte clínica sem nenhuma checagem de autorização. Ver PM-ONLY-04.
ADMIN_ROLES = frozenset({"admin", "superadmin"})


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


def require_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Autorização mínima para ações administrativas (ex.: suíte clínica). Ver ADMIN_ROLES.
    Toda tentativa negada é auditada — "tentativa de alteração da suíte" inclui tentativas de
    usuários sem permissão, não só chave mestra incorreta."""
    if current_user.role not in ADMIN_ROLES:
        db.add(
            AuditEvent(
                actor_user_id=current_user.id,
                organization_id=current_user.organization_id,
                event_type="admin_action_denied",
                description=f"{current_user.email} (role={current_user.role}) tentou ação administrativa sem permissão.",
            )
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta ação requer um usuário administrador autorizado.",
        )
    return current_user


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        organization_id=current_user.organization_id,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> LogoutResponse:
    db.add(
        AuditEvent(
            actor_user_id=current_user.id,
            organization_id=current_user.organization_id,
            event_type="logout",
            description=f"Logout registrado para {current_user.email} (DEV_AUTH: sem revogação real de token).",
        )
    )
    db.commit()
    return LogoutResponse(status="logged_out_client_side_only")
