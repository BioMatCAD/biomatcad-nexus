"""Testes dedicados de segurança do ambiente de pesquisa (Incremento 2.2, rodada de
fechamento -- Fase C). Cobre 5 propriedades de segurança que já existiam no código, mas sem
NENHUM teste de regressão dedicado até esta rodada (auditoria da Fase A/C): defesa contra
path traversal no armazenamento de artefatos, ausência estrutural de command injection na
invocação do worker, sanitização de logs sensíveis, comportamento seguro (sem vazamento de
stack trace) em falha não tratada, e a restrição real de CORS (`*` fora de development/test).

Não cobre RBAC/ABAC completo (17 perfis, OIDC, MFA) -- isso é `PM-ONLY-04e/f/g/h`, deliberada e
explicitamente fora do escopo de pesquisa deste incremento (ver `REQUIREMENTS_MATRIX.md`).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from biomatcad_api.config import Environment, Settings
from biomatcad_api.logging_config import RedactSensitiveFilter
from biomatcad_api.services.storage import LocalStorageAdapter
from biomatcad_api.services.worker_client import DotnetPicoGkWorkerClient

# ---------------------------------------------------------------------------
# 1) Validação de caminhos -- defesa contra path traversal em LocalStorageAdapter
# ---------------------------------------------------------------------------


def test_storage_adapter_rejeita_chave_com_path_traversal(tmp_path):
    base_dir = tmp_path / "artifacts"
    adapter = LocalStorageAdapter(base_dir)

    # Um artefato malicioso tentaria escapar de base_dir para ler/sobrescrever um arquivo
    # arbitrário do sistema (ex.: outra organização, ou um arquivo fora da árvore de
    # armazenamento). Isso deve ser rejeitado sempre, para put/get/exists.
    malicious_keys = [
        "../secret.txt",
        "../../etc/passwd",
        "sub/../../escape.bin",
        "/etc/passwd",  # caminho absoluto também não pode escapar da resolução
    ]
    for key in malicious_keys:
        with pytest.raises(ValueError, match="fora de base_dir"):
            adapter.put(key, b"dados maliciosos")
        with pytest.raises(ValueError, match="fora de base_dir"):
            adapter.get(key)
        with pytest.raises(ValueError, match="fora de base_dir"):
            adapter.exists(key)

    # Confirma que nenhum arquivo foi de fato escrito fora de base_dir.
    assert not (tmp_path / "secret.txt").exists()
    assert not (tmp_path / "escape.bin").exists()


def test_storage_adapter_aceita_chaves_legitimas_dentro_de_subpastas(tmp_path):
    base_dir = tmp_path / "artifacts"
    adapter = LocalStorageAdapter(base_dir)

    # Chaves reais usadas em produção incluem subpastas (ex.: "<job_id>/model.stl") -- a defesa
    # contra traversal não pode bloquear isso, só o escape de base_dir.
    adapter.put("job-123/model.stl", b"conteudo-real")
    assert adapter.exists("job-123/model.stl")
    assert adapter.get("job-123/model.stl") == b"conteudo-real"


# ---------------------------------------------------------------------------
# 2) Prevenção de command injection na invocação do worker
# ---------------------------------------------------------------------------


def _make_fake_worker_repo(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "apps" / "geometry-worker" / "bin" / "Release" / "net9.0"
    bin_dir.mkdir(parents=True)
    dll_path = bin_dir / "BioMatCadGeometryWorker.dll"
    dll_path.write_text(
        "import json, sys\n"
        "job = json.load(open(sys.argv[1], encoding='utf-8'))\n"
        "print(json.dumps({\n"
        "    'stl_path': 'nao-usado.stl', 'thumbnail_path': None, 'vdb_path': None,\n"
        "    'metrics': {}, 'worker_version': '0.0.0-test', 'dotnet_version': '0.0.0-test',\n"
        "    'picogk_version': '0.0.0-test', 'duration_seconds': 0.01,\n"
        "}))\n",
        encoding="utf-8",
    )
    return tmp_path


def test_worker_client_invoca_subprocesso_sem_shell_e_com_argumentos_em_lista(tmp_path, monkeypatch):
    # Defesa estrutural contra command injection: o worker é SEMPRE invocado com uma LISTA de
    # argumentos (nunca uma string montada por concatenação) e SEM shell=True -- mesmo que o
    # conteúdo da receita contenha metacaracteres de shell (';', '&&', '$(...)', backticks),
    # eles nunca alcançam uma shell, porque a receita é gravada em um ARQUIVO JSON e apenas o
    # CAMINHO desse arquivo (nunca seu conteúdo) é passado na linha de comando.
    captured_calls = []
    real_popen = subprocess.Popen

    def _spy_popen(args, **kwargs):
        captured_calls.append((args, kwargs))
        return real_popen(args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", _spy_popen)

    repo_root = _make_fake_worker_repo(tmp_path / "fake-repo")
    client = DotnetPicoGkWorkerClient(repo_root=repo_root, dotnet_bin=sys.executable)

    malicious_recipe = {
        "domain": {"shape": "block; rm -rf / #"},
        "topology": {"kind": "gyroid", "notes": "$(whoami) `id` && echo pwned"},
        "compute_limits": {"max_duration_seconds": 5},
    }
    result = client.execute(recipe_canonical=malicious_recipe, job_id="job-injection-test", output_dir=tmp_path / "out")

    assert result.worker_version == "0.0.0-test"
    assert len(captured_calls) == 1
    args, kwargs = captured_calls[0]

    # Args é uma lista real (não uma string montada) -- pré-requisito para nunca invocar uma
    # shell implicitamente.
    assert isinstance(args, list)
    assert kwargs.get("shell") is not True

    # Nenhum metacaractere/malicious payload da receita aparece em NENHUM token da linha de
    # comando -- só chegam dotnet_bin, o caminho do "dll" e o caminho do job.json (nunca o
    # conteúdo da receita).
    for token in args:
        assert "rm -rf" not in token
        assert "whoami" not in token
        assert "pwned" not in token
    assert len(args) == 3
    assert args[0] == sys.executable
    assert str(args[2]).endswith("job.json")

    # O conteúdo malicioso só existe DENTRO do arquivo JSON gravado em disco -- nunca na linha
    # de comando -- e mesmo assim nunca é interpretado como comando (é lido como texto/JSON).
    job_json_content = (tmp_path / "out" / "job.json").read_text(encoding="utf-8")
    assert "rm -rf" in job_json_content  # confirma que o dado malicioso realmente chegou até aqui...
    # ...mas só como STRING dentro de um JSON, nunca executado (o processo "worker" fake acima
    # só leu o arquivo com json.load e nunca invocou uma shell com esse conteúdo).


# ---------------------------------------------------------------------------
# 3) Sanitização de logs -- RedactSensitiveFilter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "login attempt password=hunter2 for user x",
        "Authorization: Bearer eyJhbGciOi...",
        "operational_state_master_key=super-secreto-123",
        "CPF do paciente: 000.000.000-00",
    ],
)
def test_redact_sensitive_filter_suprime_mensagens_com_chave_sensivel(message):
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1, msg=message, args=(), exc_info=None
    )
    filt = RedactSensitiveFilter()
    keep = filt.filter(record)

    assert keep is True  # o filtro nunca descarta o log inteiro, só redige o conteúdo
    assert record.getMessage() == "[mensagem de log suprimida: possível dado sensível]"
    assert "hunter2" not in record.getMessage()


def test_redact_sensitive_filter_preserva_mensagens_sem_dado_sensivel():
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job_dispatched job_id=abc123 status=queued",
        args=(),
        exc_info=None,
    )
    filt = RedactSensitiveFilter()
    filt.filter(record)
    assert record.getMessage() == "job_dispatched job_id=abc123 status=queued"


# ---------------------------------------------------------------------------
# 4) Comportamento seguro em falha -- erro não tratado nunca vaza detalhe interno
# ---------------------------------------------------------------------------


def test_erro_nao_tratado_nunca_vaza_mensagem_interna_ao_cliente(db_session):
    # Usa um TestClient PROPRIO (raise_server_exceptions=False) em vez da fixture 'client'
    # compartilhada: por padrao o TestClient (httpx/Starlette) RE-LEVANTA a excecao original no
    # processo de teste (para facilitar depuracao durante testes), mesmo quando o
    # exception_handler da aplicacao ja produziu uma resposta segura -- isso e um
    # comportamento do proprio harness de teste, nao da aplicacao real (em producao, atras de
    # uvicorn, o handler sempre responde; nao ha reraise). Para provar o que o CLIENTE REAL
    # recebe (a resposta HTTP, nao uma excecao Python), raise_server_exceptions precisa ser
    # False aqui.
    from fastapi.testclient import TestClient

    from biomatcad_api.db import get_db
    from biomatcad_api.main import app

    segredo_interno = "SENHA_DO_BANCO_INTERNA=super-secreta-nao-deveria-vazar-jamais"

    def _broken_get_db():
        raise RuntimeError(segredo_interno)
        yield  # pragma: no cover -- nunca alcancado; mantem a forma de gerador esperada por Depends()

    app.dependency_overrides[get_db] = _broken_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as broken_client:
            response = broken_client.get("/api/v1/materials")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    body = response.json()
    assert segredo_interno not in response.text
    assert "SENHA_DO_BANCO_INTERNA" not in response.text
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "Erro interno. Consulte os logs do servidor pelo identificador informado."
    assert body["error"]["id"]
    assert "RuntimeError" not in response.text


# ---------------------------------------------------------------------------
# 5) CORS restritivo -- "*" nunca permitido fora de development/test
# ---------------------------------------------------------------------------


def test_cors_rejeita_wildcard_fora_de_development_e_test():
    for env in (Environment.LOCAL_NETWORK, Environment.STAGING, Environment.PRODUCTION):
        with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
            Settings(
                environment=env,
                cors_allowed_origins=["*"],
                api_secret_key="x" * 40,
                database_url="postgresql://user:pass@localhost/db",
            )


def test_cors_aceita_wildcard_em_development_e_test_apenas():
    for env in (Environment.DEVELOPMENT, Environment.TEST):
        settings = Settings(environment=env, cors_allowed_origins=["*"])
        assert settings.cors_allowed_origins == ["*"]


def test_cors_aceita_lista_explicita_em_qualquer_ambiente():
    # database_url explicito (Postgres) para nao depender de nenhum DATABASE_URL setado
    # externamente pelo ambiente de execucao dos testes (conftest.py define esse env var
    # globalmente quando a suite completa roda contra Postgres real via pgserver, mas este
    # teste precisa ser deterministico mesmo quando executado isoladamente).
    settings = Settings(
        environment=Environment.PRODUCTION,
        cors_allowed_origins=["https://pesquisa.biomatcad.example"],
        api_secret_key="x" * 40,
        database_url="postgresql://user:pass@localhost/db",
    )
    assert settings.cors_allowed_origins == ["https://pesquisa.biomatcad.example"]
