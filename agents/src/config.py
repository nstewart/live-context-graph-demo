"""Agent configuration."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Agent settings loaded from environment variables."""

    # API
    agent_api_base: str = "http://api:8080"

    # PostgreSQL (for agent checkpointing)
    pg_host: str = "db"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_database: str = "freshmart"

    # Materialize
    mz_host: str = "mz"
    mz_port: int = 5432
    mz_user: str = "materialize"
    mz_password: str = "materialize"
    mz_database: str = "materialize"

    # OpenSearch
    agent_os_base: str = "http://opensearch:9200"

    # LLM
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_model: str = "claude-sonnet-4-20250514"  # Default for Anthropic; use "gpt-4-turbo" for OpenAI

    # Logging
    log_level: str = "INFO"

    @property
    def mz_dsn(self) -> str:
        """Get Materialize connection string."""
        return f"postgresql+asyncpg://{self.mz_user}:{self.mz_password}@{self.mz_host}:{self.mz_port}/{self.mz_database}"

    @property
    def pg_dsn(self) -> str:
        """Get PostgreSQL connection string for checkpointing."""
        return f"postgresql://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
