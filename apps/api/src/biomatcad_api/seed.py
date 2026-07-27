"""Seed exclusivamente sintético para desenvolvimento (Prompt Mestre §3.1: nunca dados reais).

Uso: python -m biomatcad_api.seed
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


def run_seed() -> None:
    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.slug == SYNTHETIC_ORG_SLUG).first()
        if org is None:
            org = Organization(name=SYNTHETIC_ORG_NAME, slug=SYNTHETIC_ORG_SLUG)
            db.add(org)
            db.flush()

        user = db.query(User).filter(User.email == SYNTHETIC_USER_EMAIL).first()
        if user is None:
            user = User(
                organization_id=org.id,
                email=SYNTHETIC_USER_EMAIL,
                full_name="Usuário Sintético de Demonstração",
                hashed_password=hash_password(SYNTHETIC_USER_PASSWORD),
                role="researcher",
            )
            db.add(user)

        for kind in OperationalStateKind:
            existing = db.query(OperationalState).filter(OperationalState.kind == kind.value).first()
            if existing is None:
                db.add(OperationalState(kind=kind.value, enabled=OperationalState.default_enabled(kind)))

        db.commit()
        print(f"Seed sintético aplicado: organização='{SYNTHETIC_ORG_SLUG}', usuário='{SYNTHETIC_USER_EMAIL}'")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
