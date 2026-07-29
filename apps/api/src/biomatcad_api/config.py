"""Configuração tipada por ambiente (Prompt Mestre: nenhum segredo hardcoded)."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Classificação explícita do modo de autenticação atual (Incremento 1.1, Prompt Mestre §9).
# DEV_AUTH = e-mail/senha + JWT stateless, adequado a desenvolvimento/demonstração sintética.
# NÃO equivale a OIDC/OAuth 2.1 + PKCE + MFA + WebAuthn + step-up auth, que permanecem
# requisitos pendentes rastreados em REQUIREMENTS_MATRIX.md (PM-ONLY-04).
AUTH_MODE = "DEV_AUTH"

# Valor padrão inseguro, aceitável apenas em ENVIRONMENT=test (ver validate_api_secret_key
# abaixo). Fora de testes, este valor (ou qualquer segredo curto) faz o app recusar iniciar.
_INSECURE_DEFAULT_SECRET = "dev-only-insecure-key-change-me"
_MIN_SECRET_LENGTH = 32


class Environment(str, Enum):
    DEVELOPMENT = "development"
    LOCAL_NETWORK = "local-network"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class InsecureConfigurationError(RuntimeError):
    """Levantado no startup quando a configuração é insegura para o ambiente declarado."""


class Settings(BaseSettings):
    """Todas as configurações vêm de variáveis de ambiente (.env em dev). Ver .env.example."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = Field(default=_INSECURE_DEFAULT_SECRET)

    database_url: str = Field(
        default="sqlite:///./biomatcad_dev.db",
        description=(
            "URL de conexão SQLAlchemy. SQLite só é aceitável em development/test "
            "(Prompt Mestre §6.2). PostgreSQL é obrigatório em local-network/staging/production."
        ),
    )

    # CORS restritivo por padrão — lista explícita, nunca '*' fora de development.
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Chave mestra ÚNICA para ativação/desativação atômica da suíte clínica (CLINICAL_TEST +
    # CLINICAL_PILOT + CLINICAL_PRODUCTION — Incremento 1.1). Nunca tem valor padrão utilizável;
    # sem ela configurada, a suíte clínica nunca pode ser ativada (ver operational_state_service.py).
    operational_state_master_key: str | None = Field(default=None)

    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 30

    # Diretório do adaptador de armazenamento local de artefatos (Incremento 2.1, item 7).
    # Mantém o mesmo contrato (services/storage.py::StorageAdapter) que um adaptador MinIO/S3
    # implementaria -- trocar de adaptador não deve exigir mudança nos routers/serviços.
    artifact_storage_dir: str = Field(default="./data/artifacts")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str, info) -> str:  # type: ignore[no-untyped-def]
        env = info.data.get("environment")
        if v.startswith("sqlite") and env in (Environment.LOCAL_NETWORK, Environment.STAGING, Environment.PRODUCTION):
            raise ValueError(
                "SQLite não é permitido em local-network/staging/production (Prompt Mestre §6.2). "
                "Configure DATABASE_URL para PostgreSQL."
            )
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def auth_mode(self) -> str:
        return AUTH_MODE

    def assert_secure_for_environment(self) -> None:
        """Falha alto e cedo (startup) se o segredo JWT estiver ausente/inseguro fora de
        ENVIRONMENT=test. Chamado explicitamente por create_app() — Incremento 1.1."""
        if self.environment == Environment.TEST:
            return
        insecure = (
            not self.api_secret_key
            or self.api_secret_key == _INSECURE_DEFAULT_SECRET
            or len(self.api_secret_key) < _MIN_SECRET_LENGTH
        )
        if insecure:
            raise InsecureConfigurationError(
                f"API_SECRET_KEY ausente ou insegura para ENVIRONMENT={self.environment.value}. "
                f"Defina um segredo real (>= {_MIN_SECRET_LENGTH} caracteres, gerado com "
                "ferramenta criptográfica) via variável de ambiente antes de iniciar fora de "
                "development/test. Este app não inicia com o valor padrão de desenvolvimento "
                "fora de ENVIRONMENT=test (Prompt Mestre §25/§26: nenhum segredo hardcoded)."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
