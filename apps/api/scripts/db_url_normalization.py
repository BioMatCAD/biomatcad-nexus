#!/usr/bin/env python3
"""Normalização explícita e testável de DATABASE_URL para psycopg2.connect() (Incremento 2.3,
Rodada 2, Fase I -- correção do preflight do piloto PubChem Windows, Run 1).

Bug real que motivou este módulo (Run 1, `final_status: FAILED_PREFLIGHT`, `PilotExitCode=1`):
`scripts/Run-PubChemPilotWindows.ps1` fazia `psycopg2.connect()` depois de só substituir
textualmente o prefixo `"postgresql+psycopg2://"` por `"postgresql://"`. A URL oficial usada na
Run 1 era `postgresql+psycopg://...` (psycopg 3 -- o dialeto recomendado no restante do
projeto, ver `apps/api/tests/test_database_driver_contract.py`), que não batia com esse
`.replace()` e passava intacta para `psycopg2.connect()`. O psycopg2 não reconhece `+psycopg`
como parte de um DSN libpq e falhou com `invalid dsn: missing "=" after
"postgresql+psycopg://..."`. O PostgreSQL real estava perfeitamente acessível (confirmado:
serviços `postgresql-x64-14`/`postgresql-x64-18` `Running`, porta 5432 aberta) -- o defeito era
inteiramente da normalização de string deste roteiro, nunca do PostgreSQL nem do PubChem (que
sequer chegou a ser consultado).

Este módulo existe para que a normalização seja uma função pura, testável isoladamente (nunca
substituição de texto embutida numa linha `python -c`), explícita sobre quais dialetos aceita
-- rejeitando qualquer outro em vez de silenciosamente produzir um DSN inválido -- e para que
qualquer mensagem de erro que acabe incluindo o DSN completo (comportamento real observado do
psycopg2 em DSNs inválidos) seja mascarada antes de chegar a um log ou relatório.

NUNCA usado para normalizar a DATABASE_URL usada pelo restante da aplicação/roteiro (SQLAlchemy
resolve `postgresql+psycopg://` e `postgresql+psycopg2://` nativamente por si só -- ver
`scripts/gate_preflight_check.py::_expected_driver_module` e
`tests/test_database_driver_contract.py`) -- só a cópia isolada passada a `psycopg2.connect()`
por este preflight específico precisa do dialeto normalizado para `postgresql://`.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

#: Esquemas base aceitos (antes de qualquer sufixo "+driver"). Qualquer outro é rejeitado
#: explicitamente -- este normalizador nunca "adivinha" um DSN para um banco diferente.
_SUPPORTED_BASE_SCHEMES: tuple[str, ...] = ("postgresql", "postgres")

#: Sufixos de driver que resolvem para uma conexão libpq compatível com `psycopg2.connect()`
#: (psycopg2 é o próprio driver; psycopg -- versão 3 -- usa o mesmo protocolo/DSN libpq, só o
#: nome do dialeto SQLAlchemy muda). Qualquer outro sufixo é rejeitado explicitamente.
_PSYCOPG2_COMPATIBLE_DRIVER_SUFFIXES: tuple[str, ...] = ("psycopg2", "psycopg")

#: Mesma regex de mascaramento usada em `Get-MaskedDatabaseUrl` (Run-PubChemPilotWindows.ps1) --
#: casa "esquema://usuario:senha@" em qualquer lugar de um texto (não apenas uma URL isolada),
#: para que também sirva para sanitizar mensagens de exceção que incluam um DSN embutido.
_CREDENTIALS_PATTERN = re.compile(r"://([^:@/]+):([^@]*)@")


class UnsupportedDatabaseUrlDialectError(ValueError):
    """Levantado quando a URL usa um esquema/dialeto que este normalizador não sabe converter
    com segurança -- nunca produz silenciosamente um DSN que psycopg2 não entenderia."""


def to_psycopg2_dsn(database_url: str) -> str:
    """Devolve uma cópia de `database_url` com o esquema normalizado para o esquema base (sem
    sufixo de driver, ex.: `"postgresql://"`), pronta para `psycopg2.connect()`.

    Aceita, no mínimo: `"postgresql://"` (sem sufixo), `"postgresql+psycopg2://"` e
    `"postgresql+psycopg://"` (e os equivalentes com o esquema base `"postgres"`). Rejeita
    explicitamente qualquer outro sufixo de driver ou esquema base, levantando
    `UnsupportedDatabaseUrlDialectError` -- nunca deixa passar um DSN que psycopg2 rejeitaria de
    forma confusa mais adiante.

    Usa `urllib.parse.urlsplit`/`urlunsplit` (nunca substituição textual de prefixo) para que o
    restante da URL -- usuário, senha, host, porta, nome do banco, query string -- seja
    preservado exatamente como veio, inclusive caracteres especiais escapados na senha.
    """
    parsed = urlsplit(database_url)
    scheme = parsed.scheme
    if "+" in scheme:
        base_scheme, driver_suffix = scheme.split("+", 1)
    else:
        base_scheme, driver_suffix = scheme, None

    if base_scheme not in _SUPPORTED_BASE_SCHEMES:
        raise UnsupportedDatabaseUrlDialectError(
            f"Esquema '{base_scheme}' não é um esquema Postgres suportado por este "
            f"normalizador (aceitos: {', '.join(_SUPPORTED_BASE_SCHEMES)})."
        )
    if driver_suffix is not None and driver_suffix not in _PSYCOPG2_COMPATIBLE_DRIVER_SUFFIXES:
        accepted = [f"{base_scheme}://"] + [
            f"{base_scheme}+{driver}://" for driver in _PSYCOPG2_COMPATIBLE_DRIVER_SUFFIXES
        ]
        raise UnsupportedDatabaseUrlDialectError(
            f"Dialeto '{scheme}://' não é suportado por este normalizador "
            f"(aceitos: {', '.join(accepted)})."
        )

    return urlunsplit((base_scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))


def mask_database_url(text: str) -> str:
    """Mascara qualquer credencial `esquema://usuario:senha@` encontrada em `text`, preservando
    o restante do texto intacto. Funciona tanto para uma URL isolada quanto para uma mensagem de
    erro maior que contenha um DSN embutido (comportamento real observado: exceções de DSN
    inválido do psycopg2 podem ecoar a string de conexão completa) -- nunca deixa uma senha
    chegar a um log ou relatório, mesmo vinda de uma mensagem de exceção de terceiros.
    """
    return _CREDENTIALS_PATTERN.sub(r"://\1:***@", text)
