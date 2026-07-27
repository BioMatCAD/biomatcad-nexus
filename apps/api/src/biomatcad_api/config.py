"""Configuração tipada por ambiente (Prompt Mestre: nenhum segredo hardcoded)."""
from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    LOCAL_NETWORK = "local-network"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Todas as configurações vêm de variáveis de ambiente (.env em dev). Ver .env.example."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = Field(default="dev-only-insecure-key-change-me")

    database_url: str = Field(
        default="sqlite:///./biomatcad_dev.db",
        description=(
            "URL de conexão SQLAlchemy. SQLite só é aceitável em development/test "
            "(Prompt Mestre §6.2). PostgreSQL é obrigatório em local-network/staging/production."
        ),
    )

    # CORS restritivo por padrão — lista explícita, nunca '*' fora de development.
    cors_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Chave mestra para ativação de estados operacionais sensíveis (Teste/Piloto/Produção).
    # Nunca tem valor padrão utilizável — deve ser definida explicitamente fora de development.
    operational_state_master_key: str | None = Field(default=None)

    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 30

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
