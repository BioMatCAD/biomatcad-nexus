"""DEV_AUTH — o app deve recusar iniciar com segredo ausente/inseguro fora de ENVIRONMENT=test
(Incremento 1.1). Testa a validação diretamente (sem subir um processo separado), simulando os
ambientes onde a checagem deve ocorrer."""
from __future__ import annotations

import pytest

from biomatcad_api.config import InsecureConfigurationError, Settings


def test_insecure_default_secret_is_rejected_outside_test_env():
    settings = Settings(
        environment="development",
        api_secret_key="dev-only-insecure-key-change-me",
        database_url="postgresql://user:pass@localhost:5432/db",
    )
    with pytest.raises(InsecureConfigurationError):
        settings.assert_secure_for_environment()


def test_short_secret_is_rejected_outside_test_env():
    settings = Settings(
        environment="production",
        api_secret_key="short",
        database_url="postgresql://user:pass@localhost:5432/db",
    )
    with pytest.raises(InsecureConfigurationError):
        settings.assert_secure_for_environment()


def test_missing_secret_is_rejected_outside_test_env():
    settings = Settings(
        environment="local-network",
        api_secret_key="",
        database_url="postgresql://user:pass@localhost:5432/db",
    )
    with pytest.raises(InsecureConfigurationError):
        settings.assert_secure_for_environment()


def test_real_secret_is_accepted_outside_test_env():
    settings = Settings(
        environment="production",
        api_secret_key="a" * 40,
        database_url="postgresql://user:pass@localhost:5432/db",
    )
    settings.assert_secure_for_environment()  # não deve levantar


def test_insecure_default_is_tolerated_in_test_env():
    settings = Settings(environment="test", api_secret_key="dev-only-insecure-key-change-me")
    settings.assert_secure_for_environment()  # não deve levantar em ambiente de teste
