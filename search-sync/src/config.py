"""Search sync worker configuration."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Worker settings loaded from environment variables."""

    # Materialize Emulator
    mz_host: str = "mz"
    mz_port: int = 5432
    mz_user: str = "materialize"
    mz_password: str = "materialize"
    mz_database: str = "materialize"
    mz_external_url: Optional[str] = None

    # OpenSearch
    os_host: str = "opensearch"
    os_port: int = 9200
    os_user: Optional[str] = None
    os_password: Optional[str] = None

    # Worker settings
    poll_interval: int = 5  # seconds
    batch_size: int = 100
    max_retries: int = 3
    log_level: str = "INFO"

    @property
    def mz_dsn(self) -> str:
        """Get Materialize connection string for SQLAlchemy."""
        if self.mz_external_url:
            return self.mz_external_url
        return f"postgresql+asyncpg://{self.mz_user}:{self.mz_password}@{self.mz_host}:{self.mz_port}/{self.mz_database}"

    @property
    def mz_conninfo(self) -> str:
        """Get Materialize connection string for psycopg."""
        if self.mz_external_url:
            return self.mz_external_url
        return f"host={self.mz_host} port={self.mz_port} user={self.mz_user} password={self.mz_password} dbname={self.mz_database}"

    @property
    def os_url(self) -> str:
        """Get OpenSearch URL."""
        return f"http://{self.os_host}:{self.os_port}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
