"""Teste de migração: garante que 'alembic upgrade head' roda sem erro do zero e cria as
tabelas esperadas, em um banco PostgreSQL dedicado e vazio (não o mesmo banco usado pelos
testes de API, que já tem as tabelas criadas via Base.metadata.create_all para velocidade).

Requer PG_ADMIN_URL (conexão administrativa ao Postgres real usada para CREATE/DROP DATABASE).
Pulado automaticamente se ausente ou se o driver psycopg2 não estiver disponível.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytest.importorskip("psycopg2")

ADMIN_URL = os.environ.get("PG_ADMIN_URL")
MIGRATION_TEST_DB = "biomatcad_migration_test"


@pytest.mark.skipif(not ADMIN_URL, reason="Requer PG_ADMIN_URL (conexão administrativa ao PostgreSQL real).")
def test_alembic_upgrade_head_runs_cleanly_on_empty_database():
    import psycopg2

    admin_conn = psycopg2.connect(ADMIN_URL)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB}")
    cur.execute(f"CREATE DATABASE {MIGRATION_TEST_DB}")
    admin_conn.close()

    base_url = ADMIN_URL.rsplit("/", 1)[0]
    migration_db_url = f"{base_url}/{MIGRATION_TEST_DB}"

    env = os.environ.copy()
    env["DATABASE_URL"] = migration_db_url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    check_conn = psycopg2.connect(migration_db_url)
    check_cur = check_conn.cursor()
    check_cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
    )
    tables = {row[0] for row in check_cur.fetchall()}
    check_conn.close()

    assert {"organizations", "users", "operational_states", "audit_events", "alembic_version"} <= tables

    admin_conn = psycopg2.connect(ADMIN_URL)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB}")
    admin_conn.close()
