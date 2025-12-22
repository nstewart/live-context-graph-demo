"""Database client and connection management."""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings

logger = logging.getLogger(__name__)

# Slow query threshold in milliseconds
SLOW_QUERY_THRESHOLD_MS = 100

# Create engines
_pg_engine = None
_mz_engine = None
_pg_session_factory = None
_mz_session_factory = None


@dataclass
class QueryStats:
    """Track query statistics for a database."""
    total_queries: int = 0
    total_time_ms: float = 0.0
    slow_queries: int = 0
    by_operation: dict = field(default_factory=lambda: defaultdict(lambda: {"count": 0, "total_ms": 0.0}))
    slowest_query_ms: float = 0.0
    slowest_query_stmt: str = ""

    def record(self, op_type: str, elapsed_ms: float, statement: str):
        """Record a query execution."""
        self.total_queries += 1
        self.total_time_ms += elapsed_ms
        self.by_operation[op_type]["count"] += 1
        self.by_operation[op_type]["total_ms"] += elapsed_ms
        if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
            self.slow_queries += 1
        if elapsed_ms > self.slowest_query_ms:
            self.slowest_query_ms = elapsed_ms
            self.slowest_query_stmt = statement[:100] if len(statement) > 100 else statement

    @property
    def avg_time_ms(self) -> float:
        """Average query time in milliseconds."""
        return self.total_time_ms / self.total_queries if self.total_queries > 0 else 0.0


# Query statistics by database
_query_stats: dict[str, QueryStats] = {}


def get_query_stats(db_name: str) -> QueryStats:
    """Get query statistics for a database."""
    if db_name not in _query_stats:
        _query_stats[db_name] = QueryStats()
    return _query_stats[db_name]


def _get_operation_type(statement: str) -> str:
    """Determine the operation type from a SQL statement."""
    stmt_upper = statement.strip().upper()
    if stmt_upper.startswith("SELECT"):
        return "SELECT"
    elif stmt_upper.startswith("INSERT"):
        return "INSERT"
    elif stmt_upper.startswith("UPDATE"):
        return "UPDATE"
    elif stmt_upper.startswith("DELETE"):
        return "DELETE"
    elif stmt_upper.startswith("SET"):
        return "SET"
    else:
        return "QUERY"


def _setup_query_logging(engine, db_name: str):
    """Set up query logging with execution time for an engine."""
    sync_engine = engine.sync_engine
    stats = get_query_stats(db_name)

    @event.listens_for(sync_engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start_times = conn.info.get("query_start_time", [])
        if start_times:
            elapsed = (time.perf_counter() - start_times.pop()) * 1000  # Convert to ms
            # Truncate long queries for readability
            stmt_display = statement.replace("\n", " ").strip()
            if len(stmt_display) > 200:
                stmt_display = stmt_display[:200] + "..."
            op_type = _get_operation_type(statement)

            # Record statistics
            stats.record(op_type, elapsed, statement)

            # Log with slow query warning
            if elapsed > SLOW_QUERY_THRESHOLD_MS:
                logger.warning(
                    "[%s] [%s] SLOW QUERY %.2fms (threshold: %dms): %s | params=%s",
                    db_name,
                    op_type,
                    elapsed,
                    SLOW_QUERY_THRESHOLD_MS,
                    stmt_display,
                    parameters,
                )
            else:
                logger.debug(
                    "[%s] [%s] %.2fms: %s | params=%s",
                    db_name,
                    op_type,
                    elapsed,
                    stmt_display,
                    parameters,
                )


def get_pg_engine():
    """Get or create PostgreSQL engine."""
    global _pg_engine
    if _pg_engine is None:
        settings = get_settings()
        _pg_engine = create_async_engine(
            settings.pg_dsn,
            echo=settings.log_level == "DEBUG",
            pool_size=5,
            max_overflow=10,
        )
        _setup_query_logging(_pg_engine, "PostgreSQL")
    return _pg_engine


def get_mz_engine():
    """Get or create Materialize engine."""
    global _mz_engine
    if _mz_engine is None:
        settings = get_settings()

        # Patch the asyncpg dialect to skip JSON codec setup for Materialize
        from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

        original_setup_json = PGDialect_asyncpg.setup_asyncpg_json_codec
        original_setup_jsonb = PGDialect_asyncpg.setup_asyncpg_jsonb_codec

        async def noop_setup_json(self, conn):
            pass

        async def noop_setup_jsonb(self, conn):
            pass

        # Temporarily patch the dialect
        PGDialect_asyncpg.setup_asyncpg_json_codec = noop_setup_json
        PGDialect_asyncpg.setup_asyncpg_jsonb_codec = noop_setup_jsonb

        _mz_engine = create_async_engine(
            settings.mz_dsn,
            echo=settings.log_level == "DEBUG",
            pool_size=5,
            max_overflow=10,
            connect_args={
                # Disable asyncpg's prepared statement cache (Materialize compatibility)
                "prepared_statement_cache_size": 0,
            },
        )
        _setup_query_logging(_mz_engine, "Materialize")

        # Note: We keep the patch in place since this engine will be used throughout
        # the application lifetime. The PG engine is created separately so it won't be affected.
    return _mz_engine


def get_pg_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get PostgreSQL session factory."""
    global _pg_session_factory
    if _pg_session_factory is None:
        _pg_session_factory = async_sessionmaker(
            get_pg_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _pg_session_factory


def get_mz_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get Materialize session factory."""
    global _mz_session_factory
    if _mz_session_factory is None:
        _mz_session_factory = async_sessionmaker(
            get_mz_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _mz_session_factory


@asynccontextmanager
async def get_pg_session() -> AsyncGenerator[AsyncSession, None]:
    """Get PostgreSQL session context manager."""
    factory = get_pg_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_mz_session() -> AsyncGenerator[AsyncSession, None]:
    """Get Materialize session context manager."""
    factory = get_mz_session_factory()
    async with factory() as session:
        yield session


async def close_connections():
    """Close all database connections."""
    global _pg_engine, _mz_engine
    if _pg_engine:
        await _pg_engine.dispose()
        _pg_engine = None
    if _mz_engine:
        await _mz_engine.dispose()
        _mz_engine = None
