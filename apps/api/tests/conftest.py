"""Fixtures compartilhadas.

Usa PostgreSQL real (via pgserver, sem Docker) apontado por TEST_DATABASE_URL. Cliente de teste
e código de teste compartilham a MESMA sessão/transação por teste (padrão simples de isolamento:
uma transação por teste, rollback ao final), para evitar problemas de visibilidade entre
conexões distintas do mesmo teste.

Isolamento de SCHEMA (correção real, rodada Voronoi 20260806-133141, itens 10-14): a validação
Windows real desta rodada rodou pytest apontando (via TEST_DATABASE_URL) para a MESMA instância
Postgres usada para a validação manual real (gate HTTP real, dispatcher real) -- e encontrou 3
falhas por contaminação genuína: um teste de cancelamento reivindicou um job antigo real
(8f572e95...), um teste de concorrência reivindicou 32 jobs em vez dos 24 que ele mesmo criou, e
um teste de observabilidade encontrou 10 jobs "processing" que ele não criou. A causa NÃO é uma
falha do padrão "uma transação por teste, rollback ao final" usado pela fixture `db_session`
abaixo -- esse padrão funciona perfeitamente para o que CADA teste escreve. A causa real é que
esse padrão só desfaz o que o PRÓPRIO teste escreve; linhas JÁ COMMITADAS por outra sessão (a
validação manual real, via HTTP, fora de qualquer transação de teste) continuam plenamente
visíveis a qualquer NOVA transação/conexão contra o mesmo banco -- e várias consultas
legitimamente amplas (ex.: claim_next_queued_job, que em produção PRECISA poder reivindicar
qualquer job da fila, de qualquer organização -- restringir isso seria quebrar o comportamento
real de um dispatcher) acabam capturando essas linhas reais.

Correção (item 12: "banco/schema exclusivo para testes... inclusive para testes
multiconexão"): quando TEST_DATABASE_URL aponta para Postgres real, a suíte inteira roda dentro
de um SCHEMA Postgres exclusivo e efêmero (nunca "public"), injetado via `options=-c
search_path=...` diretamente na própria connection string -- isso é um parâmetro de conexão do
libpq (psycopg2 e psycopg 3 o repassam da mesma forma), então vale automaticamente para
QUALQUER engine/conexão aberta a partir de DATABASE_URL, sem exigir nenhuma mudança em
biomatcad_api/db.py nem nos testes existentes. Em particular, cobre o caso de
test_geometry_job_concurrency.py, que deliberadamente usa `biomatcad_api.db.SessionLocal`
diretamente (conexões verdadeiramente independentes, não a fixture `db_session`) para provar
exclusão mútua real entre duas conexões distintas -- SessionLocal é criado no import de
biomatcad_api.db, então o schema precisa estar em DATABASE_URL ANTES desse import (garantido
pela ordem deste arquivo: a variável de ambiente é calculada e setada, o schema é criado via uma
conexão de bootstrap à parte, e só ENTÃO `from biomatcad_api import models` roda).

O schema é DROPADO e CRIADO do zero no início da sessão de testes, e DROPADO de novo ao final --
nunca toca no schema "public" nem em qualquer tabela/linha real do banco de pesquisa do usuário
(item 13: nunca resolver apagando indiscriminadamente esse banco). O nome do schema inclui o PID
do processo pytest para que execuções sobrepostas não colidam entre si.

SQLite (o default local, um arquivo efêmero sem nenhum risco de conter dados reais de pesquisa)
continua funcionando exatamente como antes -- este mecanismo de schema só se aplica a Postgres.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_SECRET_KEY", "test-secret-key-not-for-production")

_RAW_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///./test_biomatcad.db")
_IS_POSTGRES_TEST_DB = _RAW_TEST_DATABASE_URL.startswith("postgresql")
_TEST_SCHEMA_NAME = f"pytest_biomatcad_{os.getpid()}"


def _database_url_with_isolated_schema() -> str:
    """Injeta `options=-c search_path=<schema exclusivo>` na connection string -- um parâmetro
    de conexão libpq padrão, repassado por psycopg2 e psycopg 3 sem nenhuma mudança de código
    em quem consome DATABASE_URL. Nunca usado para SQLite (não há conceito de schema/search_path
    -- e um arquivo .db local não compartilha dados reais entre execuções por padrão)."""
    if not _IS_POSTGRES_TEST_DB:
        return _RAW_TEST_DATABASE_URL
    separator = "&" if "?" in _RAW_TEST_DATABASE_URL else "?"
    return f"{_RAW_TEST_DATABASE_URL}{separator}options=-c search_path%3D{_TEST_SCHEMA_NAME}"


if _IS_POSTGRES_TEST_DB:
    # Bootstrap do schema exclusivo -- conexão à parte, SEM o search_path customizado (o
    # schema ainda não existe neste ponto), só para o DDL de criação do próprio schema.
    _bootstrap_engine = create_engine(_RAW_TEST_DATABASE_URL)
    with _bootstrap_engine.connect() as _bootstrap_conn:
        _bootstrap_conn.execute(text(f'DROP SCHEMA IF EXISTS "{_TEST_SCHEMA_NAME}" CASCADE'))
        _bootstrap_conn.execute(text(f'CREATE SCHEMA "{_TEST_SCHEMA_NAME}"'))
        _bootstrap_conn.commit()
    _bootstrap_engine.dispose()

os.environ["DATABASE_URL"] = _database_url_with_isolated_schema()

from biomatcad_api import models  # noqa: F401,E402
from biomatcad_api.db import Base  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()
    if _IS_POSTGRES_TEST_DB:
        # Destrói o schema exclusivo inteiro ao final da sessão de testes -- nunca o schema
        # "public" real, e nunca por meio de um DROP DATABASE/TRUNCATE amplo que pudesse
        # alcançar dados fora deste schema.
        _teardown_engine = create_engine(_RAW_TEST_DATABASE_URL)
        with _teardown_engine.connect() as _teardown_conn:
            _teardown_conn.execute(text(f'DROP SCHEMA IF EXISTS "{_TEST_SCHEMA_NAME}" CASCADE'))
            _teardown_conn.commit()
        _teardown_engine.dispose()


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
    """Carrega uma golden recipe de schemas/biomatcem/golden-recipes/.

    Desde o Incremento 2.1.1, os arquivos golden-recipes/*.json sao corpos JSON diretamente
    validos contra geometry-recipe-v1.schema.json -- nao ha mais campos de metadado (_golden_recipe_id,
    _description) misturados no corpo nem remocao de campos por esta funcao. Metadados descritivos
    ficam em schemas/biomatcem/golden-recipes/METADATA.json (arquivo separado, fora do corpo validado).
    """
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    path_json = repo_root / "schemas" / "biomatcem" / "golden-recipes" / f"{name}.json"
    with open(path_json, encoding="utf-8") as f:
        data: dict = json.load(f)
    return data


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
