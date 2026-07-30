#!/usr/bin/env python3
"""Preflight do gate final real (apps/api/scripts/verify_full_pipeline_sha256.py): confirma,
ANTES de rodar `alembic upgrade head` ou iniciar a API, que o ambiente realmente consegue falar
com o PostgreSQL indicado em DATABASE_URL -- driver DBAPI instalado, porta acessível, conexão e
autenticação reais.

Bug real que motivou este script (2026-07-29): o gate rodou no Windows do usuário e morreu com
"ModuleNotFoundError: No module named 'psycopg'" DEPOIS de já ter tentado `alembic upgrade
head`, sem nenhum relatório estruturado -- só um traceback cru no console, e nenhum arquivo
correspondia ao "gate-final-report.json" que o usuário precisava devolver. Este script existe
para pegar esse tipo de problema ANTES, com uma mensagem clara e um relatório estruturado
sempre gravado (chamado por scripts/Run-FinalGate.ps1).

NUNCA usa SQLite como alternativa/fallback -- se a DATABASE_URL informada for Postgres (o único
caso suportado por este preflight) e a conexão falhar, o preflight reporta a falha real; ele
nunca troca silenciosamente para outro banco para "fazer o gate passar".

Uso:
    python scripts/gate_preflight_check.py --database-url "postgresql+psycopg://user:pass@host:5432/db"

Imprime um relatório JSON em stdout (mesmo formato de GATE_FULL_PIPELINE_REPORT.json:
gate/steps/result/failure_reason/overall_ok, com "stage": "preflight" adicional) e termina com
exit code 0 se tudo passou, ou 1 se qualquer etapa falhou.
"""
from __future__ import annotations

import argparse
import importlib
import json
import socket
import sys
from urllib.parse import urlsplit


def _expected_driver_module(database_url: str) -> str:
    """Deriva o módulo Python que o SQLAlchemy vai tentar importar para este dialeto -- mesma
    resolução usada pelo teste apps/api/tests/test_database_driver_contract.py.
    """
    scheme = urlsplit(database_url).scheme  # ex.: "postgresql", "postgresql+psycopg"
    if "+" in scheme:
        _, driver = scheme.split("+", 1)
    else:
        # "postgresql://" sem sufixo -- o SQLAlchemy resolve para psycopg2 por padrão.
        driver = "psycopg2"
    # psycopg2 é importado como "psycopg2"; psycopg (v3) como "psycopg". Ambos coincidem com o
    # nome do driver na URL neste projeto, então nenhum mapeamento adicional é necessário.
    return driver


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--connect-timeout-seconds", type=float, default=5.0)
    args = parser.parse_args()

    report: dict = {
        "gate": "full_pipeline_real_worker",
        "stage": "preflight",
        "steps": [],
        "result": None,
        "failure_reason": None,
        "overall_ok": None,
    }

    def step(name: str, ok: bool, detail: str) -> None:
        report["steps"].append({"step": name, "ok": ok, "detail": detail})

    def fail(name: str, detail: str) -> int:
        step(name, False, detail)
        report["result"] = "FAILED"
        report["failure_reason"] = f"{name}: {detail}"
        report["overall_ok"] = False
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    database_url = args.database_url
    if database_url.startswith("sqlite"):
        # Nunca aceito como substituto do gate real -- ver docstring do módulo.
        return fail(
            "database_url_nao_e_sqlite",
            "DATABASE_URL aponta para SQLite. O gate final real exige PostgreSQL de verdade "
            "(o worker/dispatcher/API de produção não suportam SQLite para este fluxo); "
            "SQLite nunca é aceito como fallback para aprovar este gate.",
        )
    step("database_url_nao_e_sqlite", True, "DATABASE_URL não é SQLite (ok).")

    driver_module = _expected_driver_module(database_url)
    try:
        importlib.import_module(driver_module)
    except ModuleNotFoundError as exc:
        return fail(
            "driver_importavel",
            f"Módulo '{driver_module}' (exigido pela URL '{database_url.split('://')[0]}://...') "
            f"não está instalado: {exc}. Rode 'pip install -e \".[dev]\"' no venv da API "
            "(pyproject.toml já declara tanto psycopg2-binary quanto psycopg[binary]).",
        )
    step("driver_importavel", True, f"Módulo '{driver_module}' importado com sucesso.")

    parsed = urlsplit(database_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=args.connect_timeout_seconds):
            pass
    except OSError as exc:
        return fail(
            "porta_postgres_acessivel",
            f"Não foi possível abrir uma conexão TCP para {host}:{port}: {exc}. Verifique se o "
            "PostgreSQL está rodando e acessível nessa porta antes de rodar o gate.",
        )
    step("porta_postgres_acessivel", True, f"Conexão TCP para {host}:{port} bem-sucedida.")

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
    except ModuleNotFoundError as exc:
        return fail(
            "conexao_e_autenticacao_reais",
            f"Driver importável isoladamente, mas SQLAlchemy não conseguiu carregá-lo: {exc}.",
        )
    except Exception as exc:  # noqa: BLE001 -- preflight deve capturar qualquer erro de conexão real
        return fail(
            "conexao_e_autenticacao_reais",
            f"Falha real ao conectar/autenticar em {host}:{port}: {exc!r}. Confirme usuário, "
            "senha e nome do banco em DATABASE_URL.",
        )
    step("conexao_e_autenticacao_reais", True, f"Conexão real e 'SELECT 1' bem-sucedidos em {host}:{port}.")

    report["result"] = "APPROVED"
    report["overall_ok"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
