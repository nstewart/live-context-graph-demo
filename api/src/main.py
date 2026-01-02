"""FreshMart Digital Twin API - Main Application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.db.client import close_connections, get_query_stats
from src.routes import audit_router, features_router, freshmart_router, loadgen_router, metrics_router, ontology_router, query_stats_router, search_router, triples_router
from src.routes.query_stats import start_heartbeat_generator, stop_heartbeat_generator

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# Suppress uvicorn access logs (they add noise without value)
class AccessLogFilter(logging.Filter):
    """Suppress all HTTP access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        return False


# Apply filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(AccessLogFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting FreshMart Digital Twin API...")
    start_heartbeat_generator()
    yield
    logger.info("Shutting down...")
    stop_heartbeat_generator()
    # Close HTTP client for load generator proxy
    from src.routes.loadgen import close_http_client
    await close_http_client()
    await close_connections()


# Create application
app = FastAPI(
    title="FreshMart Digital Twin API",
    description="""
    API for managing the FreshMart digital twin - a knowledge graph representing
    same-day delivery operations.

    ## Features

    - **Ontology Management**: Define and manage entity classes and their properties
    - **Triple Store**: Create, read, update, and delete knowledge graph triples
    - **FreshMart Operations**: Query flattened views for orders, inventory, and couriers

    ## Data Model

    The API uses a triple store (subject-predicate-object) backed by PostgreSQL,
    with an ontology schema for validation. Entity types include:

    - **Customer**: People who place orders
    - **Store**: FreshMart store locations
    - **Product**: Items available for sale
    - **Order**: Customer orders
    - **Courier**: Delivery couriers
    - **DeliveryTask**: Tasks assigned to couriers
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(audit_router)
app.include_router(features_router)
app.include_router(loadgen_router)
app.include_router(metrics_router)
app.include_router(ontology_router)
app.include_router(search_router)
app.include_router(triples_router)
app.include_router(freshmart_router)
app.include_router(query_stats_router)


# Health endpoints
@app.get("/health", tags=["Health"])
async def health():
    """Basic health check."""
    return {"status": "healthy"}


@app.get("/ready", tags=["Health"])
async def ready():
    """
    Readiness check - verifies database connectivity.

    Returns 200 if the API is ready to serve requests.
    """
    from sqlalchemy import text

    from src.db.client import get_pg_session

    try:
        async with get_pg_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "database": "disconnected", "error": str(e)},
        )


@app.get("/stats", tags=["Health"])
async def query_stats():
    """
    Query statistics for PostgreSQL and Materialize.

    Returns execution time statistics including:
    - Total queries executed
    - Total and average execution time
    - Breakdown by operation type (SELECT, INSERT, UPDATE, DELETE)
    - Slow query count and details
    """
    pg_stats = get_query_stats("PostgreSQL")
    mz_stats = get_query_stats("Materialize")

    def format_stats(stats):
        return {
            "total_queries": stats.total_queries,
            "total_time_ms": round(stats.total_time_ms, 2),
            "avg_time_ms": round(stats.avg_time_ms, 2),
            "slow_queries": stats.slow_queries,
            "slowest_query_ms": round(stats.slowest_query_ms, 2),
            "slowest_query": stats.slowest_query_stmt,
            "by_operation": {
                op: {
                    "count": data["count"],
                    "total_ms": round(data["total_ms"], 2),
                    "avg_ms": round(data["total_ms"] / data["count"], 2) if data["count"] > 0 else 0,
                }
                for op, data in stats.by_operation.items()
            },
        }

    return {
        "postgresql": format_stats(pg_stats),
        "materialize": format_stats(mz_stats),
    }


@app.get("/", tags=["Root"])
async def root():
    """API root - returns basic info."""
    return {
        "name": "FreshMart Digital Twin API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "stats": "/stats",
    }
