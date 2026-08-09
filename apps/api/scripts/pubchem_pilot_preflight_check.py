#!/usr/bin/env python3
"""Passo 1 (postgres_connectivity) de scripts/Run-PubChemPilotWindows.ps1: confirma que o
PostgreSQL indicado em DATABASE_URL está acessível via psycopg2.connect(), aceitando qualquer um
dos dialetos SQLAlchemy usados neste projeto -- postgresql://, postgresql+psycopg2://,
postgresql+psycopg:// -- via scripts/db_url_normalization.py.

Bug real corrigido nesta rodada (Run 1, `final_status: FAILED_PREFLIGHT`, `PilotExitCode=1`):
este passo antes vivia embutido como uma linha `python -c "...replace(...)..."` dentro do
próprio .ps1, cuja normalização só cobria `postgresql+psycopg2://`, deixando
`postgresql+psycopg://` (a URL oficial da Run 1) passar intacta para `psycopg2.connect()` e
falhar com "invalid dsn". Extraído para este script isolado e testável, usando a normalização
explícita de scripts/db_url_normalization.py em vez de substituição de texto embutida.

NUNCA imprime a DATABASE_URL (nem em sucesso, nem em erro) sem mascarar a senha -- mesmo que a
exceção do psycopg2 inclua o DSN completo na mensagem (comportamento real observado nesta
rodada).

Uso:
    DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db python scripts/pubchem_pilot_preflight_check.py

Imprime "OK" em stdout e sai 0 em sucesso. Em falha, imprime uma mensagem sanitizada em stderr
e sai 1 -- nunca lança uma exceção não tratada (o chamador em PowerShell decide como reportar).
"""
from __future__ import annotations

import os
import sys

# Import de módulo irmão em scripts/ (nunca "scripts.db_url_normalization"): este script é
# sempre invocado como arquivo (`python scripts/pubchem_pilot_preflight_check.py`), e nesse
# modo o Python coloca o próprio diretório do script em sys.path[0] -- mesma convenção de
# invocação de todos os outros scripts deste diretório (ver Run-PubChemPilotWindows.ps1). O
# mypy, por outro lado, enxerga scripts/ como um pacote (por causa de scripts/__init__.py) e
# esperaria um import qualificado -- ignorado explicitamente aqui, documentado, em vez de
# reestruturar a convenção de execução de todo o diretório só por causa do type checker.
from db_url_normalization import (  # type: ignore[import-not-found]
    UnsupportedDatabaseUrlDialectError,
    mask_database_url,
    to_psycopg2_dsn,
)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        print("DATABASE_URL não está definida no ambiente.", file=sys.stderr)
        return 1

    try:
        dsn = to_psycopg2_dsn(database_url)
    except UnsupportedDatabaseUrlDialectError as exc:
        print(mask_database_url(str(exc)), file=sys.stderr)
        return 1

    try:
        import psycopg2

        psycopg2.connect(dsn).close()
    except Exception as exc:  # noqa: BLE001 -- preflight deve capturar qualquer erro de conexão real
        print(mask_database_url(str(exc)), file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
