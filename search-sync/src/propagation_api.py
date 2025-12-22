"""Simple HTTP API for exposing propagation events."""

import json
import logging
from aiohttp import web

from src.propagation_events import get_propagation_store

logger = logging.getLogger(__name__)


async def handle_get_events(request: web.Request) -> web.Response:
    """Handle GET /propagation/events endpoint.

    Query params:
        since_mz_ts: Only return events with mz_ts greater than this value
        subject_ids: Comma-separated list of subject IDs to filter by
        limit: Maximum number of events to return (default: 100)
    """
    store = get_propagation_store()

    # Parse query params
    since_mz_ts = request.query.get("since_mz_ts")
    subject_ids_param = request.query.get("subject_ids")
    limit = int(request.query.get("limit", "100"))

    subject_ids = None
    if subject_ids_param:
        subject_ids = [s.strip() for s in subject_ids_param.split(",") if s.strip()]

    # Get events
    events = store.get_events(
        since_mz_ts=since_mz_ts,
        subject_ids=subject_ids,
        limit=limit,
    )

    return web.json_response({"events": events})


async def handle_get_all_events(request: web.Request) -> web.Response:
    """Handle GET /propagation/events/all endpoint - returns all recent events.

    Unlike /propagation/events, this endpoint does NOT filter by subject_id,
    so it returns ALL propagation events (showing cascading effects).

    Query params:
        since_mz_ts: Only return events with mz_ts greater than this value
        limit: Maximum number of events to return (default: 100)
    """
    store = get_propagation_store()
    since_mz_ts = request.query.get("since_mz_ts")
    limit = int(request.query.get("limit", "100"))

    # Get events without subject_id filtering (to show all cascading effects)
    events = store.get_events(since_mz_ts=since_mz_ts, limit=limit)
    return web.json_response({"events": events})


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    store = get_propagation_store()
    return web.json_response({
        "status": "healthy",
        "event_count": len(store),
    })


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()

    # Add CORS middleware
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    app.middlewares.append(cors_middleware)

    # Add routes
    app.router.add_get("/propagation/events", handle_get_events)
    app.router.add_get("/propagation/events/all", handle_get_all_events)
    app.router.add_get("/health", handle_health)

    return app


async def start_api_server(host: str = "0.0.0.0", port: int = 8081) -> web.AppRunner:
    """Start the HTTP API server.

    Args:
        host: Host to bind to
        port: Port to bind to

    Returns:
        The AppRunner instance (for cleanup)
    """
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Propagation API server started on http://{host}:{port}")
    return runner
