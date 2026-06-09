"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL (Primary Database)
    pg_host: str = "db"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = "postgres"
    pg_database: str = "freshmart"
    pg_external_url: Optional[str] = None

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

    # Jolokia agent on the Kafka Connect worker — exposes the embedding SMT's
    # JMX diff counters over HTTP, read by /api/search/embedding-metrics.
    jolokia_url: str = "http://connect:8778"

    # Application
    log_level: str = "INFO"
    api_port: int = 8080

    # Database connection pools.
    # The pool needs to be large enough that the heartbeat (50ms cadence) and
    # all polling loops (postgresql_view, batch_cache, materialize) can each
    # hold a connection without starving each other. With pool_size=5 the
    # heartbeat starves; pool_size=20 is comfortable.
    pg_pool_size: int = 20
    pg_max_overflow: int = 20
    mz_pool_size: int = 5
    mz_max_overflow: int = 10

    # Per-source concurrency for the query-stats polling loops.
    # Higher = more throughput per source; lower = lower per-query latency
    # because there's less contention on the optimizer / cluster. The demo's
    # latency story reads cleaner with concurrency=1, but increasing these
    # is fair game for throughput-focused demos.
    qs_concurrency_postgresql_view: int = 1
    qs_concurrency_batch_cache: int = 1
    qs_concurrency_materialize: int = 1

    # Heartbeat cadence (seconds). Drives `effective_updated_at` on the
    # polled order's pricing data. Lower is fresher but adds PG write load.
    qs_heartbeat_interval: float = 0.05

    # Feature flags
    # Use Materialize for FreshMart read queries
    use_materialize_for_reads: bool = True

    @property
    def pg_dsn(self) -> str:
        """Get PostgreSQL connection string."""
        if self.pg_external_url:
            return self.pg_external_url
        return f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"

    @property
    def mz_dsn(self) -> str:
        """Get Materialize connection string."""
        if self.mz_external_url:
            return self.mz_external_url
        return f"postgresql+asyncpg://{self.mz_user}:{self.mz_password}@{self.mz_host}:{self.mz_port}/{self.mz_database}"

    @property
    def os_url(self) -> str:
        """Get OpenSearch URL."""
        return f"http://{self.os_host}:{self.os_port}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra environment variables


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
