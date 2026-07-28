"""Seed exclusivamente sintético para desenvolvimento (Prompt Mestre §3.1: nunca dados reais).

Uso: python -m biomatcad_api.seed

Cria dois usuários sintéticos deliberadamente com papéis diferentes, para que os fluxos de
autorização (ex.: ativação da suíte clínica, restrita a administrador) sejam demonstráveis e
testáveis manualmente sem precisar de RBAC completo (PM-ONLY-04, backlog):

- demo@biomatcad.example       — role "researcher" (sem permissão administrativa)
- admin@biomatcad.example      — role "admin" (pode ativar/desativar a suíte clínica)
"""
from __future__ import annotations

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.operational_state import OperationalState, OperationalStateKind
from biomatcad_api.models.organization import Organization
from biomatcad_api.models.user import User
from biomatcad_api.security import hash_password

SYNTHETIC_ORG_NAME = "Instituto Sintético de Demonstração BioMatCAD"
SYNTHETIC_ORG_SLUG = "demo-biomatcad"

SYNTHETIC_USER_EMAIL = "demo@biomatcad.example"
SYNTHETIC_USER_PASSWORD = "demo-synthetic-password-123"  # apenas ambiente de desenvolvimento

SYNTHETIC_ADMIN_EMAIL = "admin@biomatcad.example"
SYNTHETIC_ADMIN_PASSWORD = "admin-synthetic-password-456"  # apenas ambiente de desenvolvimento


def _ensure_user(db, *, org_id: str, email: str, full_name: str, password: str, role: str) -> None:
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        db.add(
            User(
                organization_id=org_id,
                email=email,
                full_name=full_name,
                hashed_password=hash_password(password),
                role=role,
            )
        )


def run_seed() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == SYNTHETIC_ORG_SLUG).first()
        if org is None:
            org = Organization(name=SYNTHETIC_ORG_NAME, slug=SYNTHETIC_ORG_SLUG)
            db.add(org)
            db.flush()

        _ensure_user(
            db,
            org_id=org.id,
            email=SYNTHETIC_USER_EMAIL,
            full_name="Usuário Sintético de Demonstração",
            password=SYNTHETIC_USER_PASSWORD,
            role="researcher",
        )
        _ensure_user(
            db,
            org_id=org.id,
            email=SYNTHETIC_ADMIN_EMAIL,
            full_name="Administrador Sintético de Demonstração",
            password=SYNTHETIC_ADMIN_PASSWORD,
            role="admin",
        )

        for kind in OperationalStateKind:
            existing = db.query(OperationalState).filter(OperationalState.kind == kind.value).first()
            if existing is None:
                db.add(OperationalState(kind=kind.value, enabled=OperationalState.default_enabled(kind)))

        db.commit()
        print(
            f"Seed sintético aplicado: organização='{SYNTHETIC_ORG_SLUG}', "
            f"usuário='{SYNTHETIC_USER_EMAIL}' (researcher), admin='{SYNTHETIC_ADMIN_EMAIL}' (admin)"
        )
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
