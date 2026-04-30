"""Client for the query-stats API used by web/src/pages/QueryStatisticsPage.tsx.

Endpoints (api/src/routes/query_stats.py):
- GET  /api/query-stats/orders                -> list of orders to pick from
- POST /api/query-stats/start/{order_id}      -> kicks off server-side polling
- POST /api/query-stats/stop                  -> stops it
- GET  /api/query-stats/metrics               -> latest p50/p99/max/qps for all 3 sources

The TUI is a thin client of these endpoints, exactly mirroring the React page:
heavy lifting (PG view query, batch refresh, MZ query, heartbeat) runs server-side;
we just trigger and poll.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 1.0
ERROR_BACKOFF_SEC = 3.0
HTTP_TIMEOUT_SEC = 5.0

MetricsEmit = Callable[[dict[str, Any]], Awaitable[None]] | Callable[[dict[str, Any]], None]


@dataclass
class OrderChoice:
    order_id: str
    order_number: str
    order_status: str
    store_id: str | None
    store_name: str | None
    customer_name: str | None


async def list_orders(api_url: str, *, prefer_status: str = "DELIVERED") -> list[OrderChoice]:
    """Get orders eligible for query-stats polling.

    Filters for the preferred status (default DELIVERED -- those have line items
    so the heartbeat can land on a real product). Falls back to any order if
    nothing matches.
    """
    url = f"{api_url.rstrip('/')}/api/query-stats/orders"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        items = resp.json() or []
    parsed = [
        OrderChoice(
            order_id=o["order_id"],
            order_number=o["order_number"],
            order_status=o["order_status"],
            store_id=o.get("store_id"),
            store_name=o.get("store_name"),
            customer_name=o.get("customer_name"),
        )
        for o in items
    ]
    preferred = [p for p in parsed if p.order_status == prefer_status]
    return preferred or parsed


async def start_polling(api_url: str, order_id: str) -> dict[str, Any]:
    """POST /api/query-stats/start/{order_id} -- triggers server tasks.

    The server starts heartbeat_loop + continuous_query_loop + batch_refresh_loop.
    Idempotent: if already polling, the server stops the old session and starts new.
    """
    url = f"{api_url.rstrip('/')}/api/query-stats/start/{order_id}"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        resp = await client.post(url)
        resp.raise_for_status()
        return resp.json() or {}


async def stop_polling(api_url: str) -> None:
    """POST /api/query-stats/stop -- best-effort, ignores errors on shutdown."""
    url = f"{api_url.rstrip('/')}/api/query-stats/stop"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
            await client.post(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stop_polling failed: %s (ignored)", exc)


async def poll_metrics(
    api_url: str,
    emit: MetricsEmit,
    *,
    interval_sec: float = POLL_INTERVAL_SEC,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Poll /api/query-stats/metrics every interval; emit each response."""
    url = f"{api_url.rstrip('/')}/api/query-stats/metrics"
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
        logger.info("query-stats metrics poller starting -> %s", url)
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            try:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    logger.warning(
                        "metrics HTTP %d: %s", resp.status_code, resp.text[:200]
                    )
                    await _backoff(stop_event)
                    continue
                payload = resp.json() or {}
                await _maybe_await(emit(payload))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("metrics poll error: %s", exc)
                await _backoff(stop_event)
                continue
            try:
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                raise


async def _backoff(stop_event: asyncio.Event | None) -> None:
    try:
        if stop_event is not None:
            await asyncio.wait_for(stop_event.wait(), timeout=ERROR_BACKOFF_SEC)
        else:
            await asyncio.sleep(ERROR_BACKOFF_SEC)
    except asyncio.TimeoutError:
        pass
    except asyncio.CancelledError:
        raise


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        await value
