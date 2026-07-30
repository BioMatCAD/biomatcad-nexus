"""Testes de regressão para as correções de contrato de dependências e do script
scripts/Run-FinalGate.ps1 feitas em 2026-07-29 (ver TEST_EVIDENCE.md, seção do gate final
aprovado no Windows + correções pós-aprovação).

Usa análise textual direta de pyproject.toml e do script PowerShell (não requer parser TOML
extra nem PowerShell instalado) -- mesmo padrão de "guarda textual" já usado em
apps/web/tests/e2eGlobalSetup.test.ts e verticalSpecGuard.test.ts.
"""
from __future__ import annotations

import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = API_DIR.parent.parent
PYPROJECT = API_DIR / "pyproject.toml"
RUN_FINAL_GATE_PS1 = REPO_ROOT / "scripts" / "Run-FinalGate.ps1"


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def _ps1_text() -> str:
    return RUN_FINAL_GATE_PS1.read_text(encoding="utf-8")


# --- pyproject.toml: drivers Postgres com bounds de versão --------------------------------

def test_psycopg2_binary_has_upper_bound():
    text = _pyproject_text()
    match = re.search(r'"psycopg2-binary([^"]*)"', text)
    assert match, "psycopg2-binary não encontrado em pyproject.toml"
    spec = match.group(1)
    assert "<3.0" in spec or "<3" in spec, (
        f"psycopg2-binary sem limite superior de versão (spec atual: {spec!r}) -- um major "
        "futuro poderia quebrar silenciosamente."
    )


def test_psycopg_v3_binary_has_lower_and_upper_bound():
    text = _pyproject_text()
    match = re.search(r'"psycopg\[binary\]([^"]*)"', text)
    assert match, "psycopg[binary] não encontrado em pyproject.toml (regressão do bug real corrigido)"
    spec = match.group(1)
    assert ">=3.1" in spec, f"psycopg[binary] sem limite inferior explícito (spec atual: {spec!r})"
    assert "<4.0" in spec or "<4" in spec, f"psycopg[binary] sem limite superior de versão (spec atual: {spec!r})"


# --- pyproject.toml: extra "gate" dedicado -------------------------------------------------

def test_gate_extra_exists_and_contains_httpx():
    text = _pyproject_text()
    gate_section = re.search(r"gate\s*=\s*\[(.*?)\]", text, re.DOTALL)
    assert gate_section, "extra opcional 'gate' não encontrado em pyproject.toml"
    assert "httpx" in gate_section.group(1), "extra 'gate' não declara httpx"


def test_gate_extra_is_minimal_does_not_pull_dev_tooling():
    text = _pyproject_text()
    gate_section = re.search(r"gate\s*=\s*\[(.*?)\]", text, re.DOTALL)
    assert gate_section
    gate_content = gate_section.group(1)
    for heavy_dev_tool in ("pytest", "ruff", "mypy", "pgserver"):
        assert heavy_dev_tool not in gate_content, (
            f"extra 'gate' inclui '{heavy_dev_tool}', que deveria ficar só em 'dev' -- "
            "'gate' existe justamente para ser instalável sem as ferramentas de lint/teste."
        )


# --- pyproject.toml: pgserver condicionado à versão do Python ------------------------------

def test_pgserver_has_python_version_marker():
    text = _pyproject_text()
    match = re.search(r'"pgserver([^"]*)"', text)
    assert match, "pgserver não encontrado em pyproject.toml"
    spec = match.group(1)
    assert "python_version" in spec, (
        f"pgserver sem marcador de ambiente 'python_version' (spec atual: {spec!r}) -- "
        "confirmado em 2026-07-29 que pgserver 0.1.4 não publica wheel para Python 3.13+ em "
        "nenhuma plataforma (manylinux2014_x86_64, win_amd64, macosx_11_0_arm64), então "
        "'pip install -e \".[dev]\"' falharia por inteiro em Python 3.13+ sem este marcador."
    )
    assert "3.13" in spec, f"marcador de pgserver não referencia o limite real conhecido (3.13): {spec!r}"


# --- scripts/Run-FinalGate.ps1: correções pós-aprovação do gate no Windows -----------------

def test_run_final_gate_disables_native_command_error_action_preference():
    text = _ps1_text()
    assert "$PSNativeCommandUseErrorActionPreference = $false" in text, (
        "Run-FinalGate.ps1 não desliga $PSNativeCommandUseErrorActionPreference -- regressão "
        "do bug real: alembic upgrade head (exit code 0) era tratado como falha terminante "
        "por causa de linhas INFO em stderr."
    )


def test_run_final_gate_forces_utf8_encoding():
    text = _ps1_text()
    assert "[Console]::OutputEncoding" in text and "UTF8" in text, (
        "Run-FinalGate.ps1 não força [Console]::OutputEncoding para UTF-8 -- regressão do bug "
        "real de mojibake nos relatórios/logs gerados no Windows."
    )
    assert "PYTHONUTF8" in text, "Run-FinalGate.ps1 não define $env:PYTHONUTF8"
    assert "PYTHONIOENCODING" in text, "Run-FinalGate.ps1 não define $env:PYTHONIOENCODING"


def test_run_final_gate_alembic_invocation_does_not_merge_stderr_into_pipeline():
    """A causa raiz do NativeCommandError cosmético era "2>&1" misturando stderr no pipeline
    de sucesso do PowerShell, onde $ErrorActionPreference=Stop aborta ao primeiro ErrorRecord.
    A invocação do alembic deve redirecionar para ARQUIVOS (1>arquivo 2>arquivo), nunca "2>&1".
    """
    text = _ps1_text()
    # Isola apenas o bloco de invocação do alembic (entre o comentário da seção 2 e o início da
    # seção 3), para não acusar falso-positivo por causa de "2>&1" usado deliberadamente em
    # OUTRAS chamadas (preflight, gate real) que precisam de streaming ao vivo.
    section_match = re.search(
        r"---- 2\. Alembic ----(.*?)---- 3\. Iniciar a API",
        text,
        re.DOTALL,
    )
    assert section_match, "Não encontrei a seção do Alembic em Run-FinalGate.ps1"
    alembic_section = section_match.group(1)

    invocation_lines = [
        line for line in alembic_section.split("\n")
        if "venvPython -m alembic upgrade head" in line
    ]
    assert invocation_lines, "Não encontrei a linha de invocação real do alembic"
    assert not any("2>&1" in line for line in invocation_lines), (
        "A invocação do alembic ainda usa '2>&1' (mistura stderr no pipeline de sucesso) -- "
        "isso é exatamente a causa raiz do NativeCommandError cosmético corrigido nesta rodada."
    )
    assert any(re.search(r"1>\$\w+\s+2>\$\w+", line) for line in invocation_lines), (
        "A invocação do alembic não redireciona stdout/stderr para arquivos separados "
        "(esperado: '1>$arquivo 2>$arquivo')."
    )
