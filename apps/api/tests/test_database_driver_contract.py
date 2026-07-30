"""Contrato de driver de banco de dados: garante que TODO dialeto Postgres realmente usado em
algum lugar do repositório (CI, docs, scripts de execução Windows) tem seu driver DBAPI
correspondente de fato instalado como dependência declarada em pyproject.toml.

Bug real corrigido em 2026-07-29: o kit de execução Windows
(docs/examples/WINDOWS_EXECUTION_KIT.md) e scripts/Run-FinalGate.ps1 usam
"postgresql+psycopg://..." (dialeto psycopg 3), mas pyproject.toml só declarava
"psycopg2-binary" -- ao rodar o gate final de verdade no Windows do usuário, o processo
morreu com "ModuleNotFoundError: No module named 'psycopg'" antes mesmo de chegar em
`alembic upgrade head`. Corrigido adicionando "psycopg[binary]" a pyproject.toml.

IMPORTANTE: estes testes NÃO precisam de um Postgres real rodando. SQLAlchemy resolve e
importa o módulo do driver DBAPI no momento de `create_engine(...)` (para escolher a classe de
dialeto correta), MESMO sem nunca abrir uma conexão de rede -- por isso um host inexistente
("db-host-que-nao-existe.invalid") é suficiente para testar "o driver está instalado e
importável", sem depender de infraestrutura externa.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import NoSuchModuleError

# Mesmo host fictício (nunca resolvido/conectado) para todos os dialetos testados -- o objetivo
# é só forçar a resolução/import do driver DBAPI, não uma conexão real.
_FAKE_HOST_URL_SUFFIX = "user:pass@db-host-que-nao-existe.invalid:5432/dbname"


@pytest.mark.parametrize(
    "dialect_url",
    [
        # Usado em .github/workflows/ci-api.yml e .env.example (sem driver explícito --
        # SQLAlchemy resolve "postgresql://" para o driver psycopg2 por padrão).
        pytest.param(f"postgresql://{_FAKE_HOST_URL_SUFFIX}", id="postgresql (default=psycopg2)"),
        # Usado em docs/examples/WINDOWS_EXECUTION_KIT.md e scripts/Run-FinalGate.ps1 -- o
        # dialeto real do gate final do worker PicoGK no Windows do usuário.
        pytest.param(f"postgresql+psycopg://{_FAKE_HOST_URL_SUFFIX}", id="postgresql+psycopg (psycopg 3)"),
    ],
)
def test_engine_creation_with_real_dialect_urls_does_not_raise_missing_driver(dialect_url: str) -> None:
    """Para cada dialeto Postgres genuinamente usado em algum lugar do repositório, criar um
    Engine (sem conectar) não deve levantar ModuleNotFoundError/NoSuchModuleError -- se levantar,
    significa que pyproject.toml não declara o driver DBAPI correspondente, exatamente o bug
    real corrigido nesta rodada.
    """
    try:
        engine = create_engine(dialect_url)
    except (ModuleNotFoundError, NoSuchModuleError) as exc:
        pytest.fail(
            f"create_engine('{dialect_url}') falhou por driver ausente: {exc}. "
            "Isso significa que pyproject.toml não declara o pacote DBAPI necessário para "
            "este dialeto -- adicione o driver correspondente (psycopg2-binary para "
            "'postgresql://', psycopg[binary] para 'postgresql+psycopg://')."
        )
    else:
        # Não conecta de propósito (host fictício) -- só confirma que o dialeto+driver foram
        # resolvidos e importados com sucesso.
        assert engine.dialect is not None
        engine.dispose()


def test_default_postgres_dialect_driver_name_is_psycopg2() -> None:
    """Documenta explicitamente qual driver o SQLAlchemy escolhe para "postgresql://" sem
    sufixo -- se isso mudar em uma versão futura do SQLAlchemy, este teste falha e chama
    atenção para revisar o contrato de dependências antes que vire um bug de produção.
    """
    engine = create_engine(f"postgresql://{_FAKE_HOST_URL_SUFFIX}")
    try:
        assert engine.dialect.driver == "psycopg2"
    finally:
        engine.dispose()


def test_psycopg_v3_dialect_driver_name_is_psycopg() -> None:
    engine = create_engine(f"postgresql+psycopg://{_FAKE_HOST_URL_SUFFIX}")
    try:
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()
