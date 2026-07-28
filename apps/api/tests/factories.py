"""Fábricas de dados sintéticos compartilhadas entre arquivos de teste."""
from __future__ import annotations

from biomatcad_api.models.organization import Organization
from biomatcad_api.models.user import User
from biomatcad_api.security import hash_password

RESEARCHER_PASSWORD = "senha-sintetica-123"  # apenas testes
ADMIN_PASSWORD = "senha-admin-sintetica-456"  # apenas testes


def create_org(db_session, slug: str = "org-teste") -> Organization:
    org = Organization(name="Org Sintética de Teste", slug=slug)
    db_session.add(org)
    db_session.flush()
    return org


def create_researcher(db_session, *, email: str = "teste@biomatcad.example", org: Organization | None = None) -> User:
    org = org or create_org(db_session, slug=f"org-{email}")
    user = User(
        organization_id=org.id,
        email=email,
        full_name="Usuário de Teste",
        hashed_password=hash_password(RESEARCHER_PASSWORD),
        role="researcher",
    )
    db_session.add(user)
    db_session.commit()
    return user


def create_admin(db_session, *, email: str = "admin@biomatcad.example", org: Organization | None = None) -> User:
    org = org or create_org(db_session, slug=f"org-{email}")
    user = User(
        organization_id=org.id,
        email=email,
        full_name="Administrador de Teste",
        hashed_password=hash_password(ADMIN_PASSWORD),
        role="admin",
    )
    db_session.add(user)
    db_session.commit()
    return user


def login(client, email: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]
