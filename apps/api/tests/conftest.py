"""Fixtures compartilhadas.

Usa PostgreSQL real (via pgserver, sem Docker) apontado por TEST_DATABASE_URL. Cliente de teste
e código de teste compartilham a MESMA sessão/transação por teste (padrão simples de isolamento:
uma transação por teste, rollback ao final), para evitar problemas de visibilidade entre
conexões distintas do mesmo teste.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("DATABASE_URL", os.environ.get("TEST_DATABASE_URL", "sqlite:///./test_biomatcad.db"))

from biomatcad_api import models  # noqa: F401
from biomatcad_api.db import Base


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionTest = sessionmaker(bind=connection, autoflush=False, autocommit=False, future=True)
    session = SessionTest()
    yield session
    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


def load_golden_recipe(name: str) -> dict:
    """Carrega uma golden recipe de schemas/biomatcem/golden-recipes/, removendo os campos de
    metadado (_golden_recipe_id, _description) que não fazem parte do schema geometry-recipe-v1
    -- ver schemas/biomatcem/golden-recipes/README.md."""
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    path_json = repo_root / "schemas" / "biomatcem" / "golden-recipes" / f"{name}.json"
    with open(path_json, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


@pytest.fixture()
def client(db_session):
    from fastapi.testclient import TestClient

    from biomatcad_api.db import get_db
    from biomatcad_api.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
