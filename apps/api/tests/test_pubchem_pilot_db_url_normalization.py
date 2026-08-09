"""Testes de scripts/db_url_normalization.py (Incremento 2.3, Rodada 2, Fase I -- correção do
preflight do piloto PubChem Windows, Run 1).

Bug real corrigido nesta rodada: `final_status: FAILED_PREFLIGHT`, `PilotExitCode=1`, com
PostgreSQL real acessível (serviços `postgresql-x64-14`/`postgresql-x64-18` `Running`, porta
5432 aberta) e PubChem sequer consultado. Causa confirmada:
`scripts/Run-PubChemPilotWindows.ps1` fazia `psycopg2.connect()` normalizando a URL só com
`.replace('postgresql+psycopg2://', 'postgresql://')` -- a URL oficial da Run 1
(`postgresql+psycopg://...`) não batia com esse `.replace()` e passava intacta para
`psycopg2.connect()`, que falhou com `invalid dsn: missing "=" after
"postgresql+psycopg://..."`. Este arquivo prova que a normalização explícita
(`to_psycopg2_dsn`) cobre os três prefixos exigidos e preserva o restante da URL -- e que
`mask_database_url` nunca deixa uma senha vazar para um log/relatório, mesmo dentro de uma
mensagem de erro maior."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from db_url_normalization import (
    UnsupportedDatabaseUrlDialectError,
    mask_database_url,
    to_psycopg2_dsn,
)


class TestToPsycopg2Dsn:
    @pytest.mark.parametrize(
        "input_url",
        [
            pytest.param(
                "postgresql://biomatcad:biomatcad@localhost:5432/biomatcad",
                id="postgresql (sem sufixo)",
            ),
            pytest.param(
                "postgresql+psycopg2://biomatcad:biomatcad@localhost:5432/biomatcad",
                id="postgresql+psycopg2 (dialeto pre-existente, ja funcionava)",
            ),
            pytest.param(
                "postgresql+psycopg://biomatcad:biomatcad@localhost:5432/biomatcad",
                id="postgresql+psycopg (dialeto oficial da Run 1 -- o que faltava)",
            ),
        ],
    )
    def test_normaliza_para_esquema_sem_sufixo(self, input_url: str) -> None:
        """Os três prefixos exigidos pela tarefa devem normalizar para o mesmo DSN
        "postgresql://..." que psycopg2.connect() entende nativamente."""
        result = to_psycopg2_dsn(input_url)
        assert result == "postgresql://biomatcad:biomatcad@localhost:5432/biomatcad"

    @pytest.mark.parametrize(
        "scheme",
        ["postgresql", "postgresql+psycopg2", "postgresql+psycopg"],
    )
    def test_preserva_usuario_senha_host_porta_banco_query(self, scheme: str) -> None:
        """Prova de preservação do restante da URL (instrução 5): usuário, senha (inclusive
        com caractere especial escapado), host, porta, nome do banco e query string devem
        sobreviver exatamente iguais -- só o esquema muda. Usa urlsplit/urlunsplit
        internamente (nunca substituição textual de prefixo), então isto não é um acidente de
        implementação, é o comportamento garantido pela função."""
        input_url = f"{scheme}://biomatcad:sec%40ret@db.example.internal:5433/biomatcad_db?sslmode=require"
        result = to_psycopg2_dsn(input_url)
        assert result == (
            "postgresql://biomatcad:sec%40ret@db.example.internal:5433/biomatcad_db?sslmode=require"
        )

    def test_preserva_url_sem_credenciais(self) -> None:
        """Também deve funcionar (sem levantar exceção) para uma URL sem usuário/senha
        explícitos -- não deve presumir que sempre há credenciais para preservar."""
        result = to_psycopg2_dsn("postgresql+psycopg://localhost:5432/biomatcad")
        assert result == "postgresql://localhost:5432/biomatcad"

    @pytest.mark.parametrize(
        "input_url",
        [
            pytest.param("postgresql+asyncpg://u:p@host:5432/db", id="dialeto assíncrono não suportado"),
            pytest.param("postgresql+pg8000://u:p@host:5432/db", id="outro driver não suportado"),
        ],
    )
    def test_rejeita_dialeto_driver_desconhecido(self, input_url: str) -> None:
        """Nunca produz silenciosamente um DSN inválido para um driver que este normalizador
        não conhece -- levanta um erro explícito em vez disso (instrução 4: função explícita e
        testável, não substituição textual frágil que deixaria passar qualquer coisa)."""
        with pytest.raises(UnsupportedDatabaseUrlDialectError):
            to_psycopg2_dsn(input_url)

    def test_rejeita_esquema_base_nao_postgres(self) -> None:
        """Nunca aceita silenciosamente uma URL de outro banco de dados como se fosse
        Postgres."""
        with pytest.raises(UnsupportedDatabaseUrlDialectError):
            to_psycopg2_dsn("mysql://u:p@host:3306/db")

    def test_mensagem_de_erro_de_dialeto_rejeitado_nao_expoe_senha(self) -> None:
        """A própria mensagem de erro de rejeição nunca deve conter a senha da URL rejeitada
        (instrução 3) -- mesmo sem passar por mask_database_url, a mensagem de erro desta
        função já é construída sem interpolar a URL inteira."""
        with pytest.raises(UnsupportedDatabaseUrlDialectError) as exc_info:
            to_psycopg2_dsn("postgresql+asyncpg://biomatcad:supersecret123@host:5432/db")
        assert "supersecret123" not in str(exc_info.value)


class TestMaskDatabaseUrl:
    def test_mascara_credenciais_em_url_isolada(self) -> None:
        assert (
            mask_database_url("postgresql+psycopg://biomatcad:supersecret@localhost:5432/biomatcad")
            == "postgresql+psycopg://biomatcad:***@localhost:5432/biomatcad"
        )

    def test_mascara_dsn_embutido_dentro_de_mensagem_de_erro_maior(self) -> None:
        """Reproduz o formato real observado do psycopg2 ao rejeitar um DSN inválido (a
        mensagem de exceção real da Run 1 incluía o começo da URL) -- a senha nunca pode
        sobreviver a essa sanitização, mesmo dentro de um texto maior."""
        raw_error = (
            'invalid dsn: missing "=" after '
            '"postgresql+psycopg://biomatcad:supersecret@localhost:5432/biomatcad..."'
        )
        masked = mask_database_url(raw_error)
        assert "supersecret" not in masked
        assert "biomatcad:***@localhost:5432/biomatcad" in masked

    def test_preserva_texto_sem_nenhuma_credencial(self) -> None:
        """Não deve alterar texto que não contenha nenhum padrão de credencial."""
        text = "conexão recusada: timeout ao alcançar localhost:5432"
        assert mask_database_url(text) == text

    def test_mascara_todas_as_ocorrencias_quando_ha_mais_de_uma(self) -> None:
        text = (
            "tentativa 1: postgresql://a:senha1@h1:5432/d -- "
            "tentativa 2: postgresql://a:senha2@h2:5432/d"
        )
        masked = mask_database_url(text)
        assert "senha1" not in masked
        assert "senha2" not in masked
        assert masked.count(":***@") == 2
