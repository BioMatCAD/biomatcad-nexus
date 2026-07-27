"""Hash de senha e emissão/validação de JWT de sessão (Incremento 1 — auth mínima real).

Limitações declaradas: sem refresh token, sem MFA, sem step-up auth, sem revogação de sessão.
Esses itens são PM-ONLY-04 (Prompt Mestre §9) e permanecem backlog.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from biomatcad_api.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def create_access_token(*, subject: str, extra_claims: dict | None = None) -> tuple[str, int]:
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.jwt_expires_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire, "iat": datetime.now(timezone.utc)}
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.api_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.api_secret_key, algorithms=[settings.jwt_algorithm])
