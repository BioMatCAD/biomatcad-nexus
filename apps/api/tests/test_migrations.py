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

    # ADMIN_URL pode ser uma URI baseada em socket unix (pgserver), ex.:
    # "postgresql://postgres:@/postgres?host=/tmp/pgdata2" -- um rsplit("/", 1) ingênuo corta
    # dentro do valor da query string "host=". Particiona primeiro em "?" para preservar a
    # query string, e só então troca o nome do banco na parte de path.
    base_no_query, _, query = ADMIN_URL.partition("?")
    base_url = base_no_query.rsplit("/", 1)[0]
    migration_db_url = f"{base_url}/{MIGRATION_TEST_DB}"
    if query:
        migration_db_url = f"{migration_db_url}?{query}"

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

    assert {
        "organizations", "users", "operational_states", "audit_events", "alembic_version",
        "material_records", "material_properties", "scientific_references", "biomat_projects",
        "geometry_recipes", "design_runs", "geometry_jobs", "artifacts", "artifact_manifests",
        # Incremento 2.3, Rodada 1 (Fase C): fundação do banco de dados científico.
        "scientific_entities", "scientific_identifiers", "scientific_sources",
        "bibliographic_references", "property_definitions", "property_observations",
        "biological_evidence", "suppliers", "supplier_products",
        "crystal_structure_references", "ingestion_runs", "review_decisions",
    } <= tables

    admin_conn = psycopg2.connect(ADMIN_URL)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB}")
    admin_conn.close()


@pytest.mark.skipif(not ADMIN_URL, reason="Requer PG_ADMIN_URL (conexão administrativa ao PostgreSQL real).")
def test_scientific_data_migration_preserves_populated_materials_and_downgrade_is_reversible():
    """Incremento 2.3, Rodada 1 (Fase C/F): a migração 4920cd8fd160 deve (1) rodar sobre um
    banco JÁ POPULADO com um MaterialRecord do Incremento 2.1 sem alterar essa linha; (2) deixar
    `scientific_entity_id` NULL para o registro pré-existente (nenhum backfill); (3) ser
    reversível via downgrade, removendo exatamente as 12 tabelas novas + a coluna adicionada,
    sem tocar no MaterialRecord original."""
    import psycopg2

    admin_conn = psycopg2.connect(ADMIN_URL)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB}_roundtrip")
    cur.execute(f"CREATE DATABASE {MIGRATION_TEST_DB}_roundtrip")
    admin_conn.close()

    base_no_query, _, query = ADMIN_URL.partition("?")
    base_url = base_no_query.rsplit("/", 1)[0]
    db_url = f"{base_url}/{MIGRATION_TEST_DB}_roundtrip"
    if query:
        db_url = f"{db_url}?{query}"

    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    repo_api_root = os.path.dirname(os.path.dirname(__file__))

    def _run_alembic(*args: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=repo_api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    # 1) Upgrade só até a revisão ANTERIOR à do Incremento 2.3 (estado real do Incremento 2.1.1).
    _run_alembic("upgrade", "c32e9b0f0f3c")

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO organizations (id, name, slug, created_at) "
        "VALUES ('11111111-1111-1111-1111-111111111111', 'Org Teste Migração', "
        "'org-teste-migracao', now())"
    )
    cur.execute(
        "INSERT INTO material_records "
        "(id, organization_id, name, category, source_type, description, review_status, created_at) "
        "VALUES ('22222222-2222-2222-2222-222222222222', "
        "'11111111-1111-1111-1111-111111111111', "
        "'Material pré-existente de teste', 'ceramic', 'synthetic', "
        "'Registro inserido antes da migração 2.3 para provar preservação.', 'draft', now())"
    )
    conn.close()

    # 2) Upgrade até head (aplica a migração do Incremento 2.3).
    _run_alembic("upgrade", "head")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(
        "SELECT name, scientific_entity_id FROM material_records "
        "WHERE id = '22222222-2222-2222-2222-222222222222'"
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None, "MaterialRecord pré-existente foi perdido pela migração."
    assert row[0] == "Material pré-existente de teste"
    assert row[1] is None, "scientific_entity_id deveria ser NULL (sem backfill) para registro pré-existente."

    # 3) Downgrade de volta à revisão anterior -- deve remover exatamente o que 2.3 adicionou.
    _run_alembic("downgrade", "c32e9b0f0f3c")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name;"
    )
    tables_after_downgrade = {r[0] for r in cur.fetchall()}
    cur.execute(
        "SELECT name FROM material_records WHERE id = '22222222-2222-2222-2222-222222222222'"
    )
    row_after_downgrade = cur.fetchone()
    conn.close()

    scientific_tables = {
        "scientific_entities", "scientific_identifiers", "scientific_sources",
        "bibliographic_references", "property_definitions", "property_observations",
        "biological_evidence", "suppliers", "supplier_products",
        "crystal_structure_references", "ingestion_runs", "review_decisions",
    }
    assert not (scientific_tables & tables_after_downgrade), (
        "Downgrade deveria ter removido todas as 12 tabelas científicas do Incremento 2.3."
    )
    assert row_after_downgrade is not None, "Downgrade não deveria apagar o MaterialRecord pré-existente."
    assert row_after_downgrade[0] == "Material pré-existente de teste"

    admin_conn = psycopg2.connect(ADMIN_URL)
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS {MIGRATION_TEST_DB}_roundtrip")
    admin_conn.close()
