"""Metrics API routes for real-time timeseries data.

These endpoints query Materialize directly for time-bucketed metrics
that cannot be synced through Zero due to its UNIQUE index requirement.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.client import get_mz_session_factory

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


class StoreTimeseriesPoint(BaseModel):
    """A single timeseries data point for a store."""
    id: str
    store_id: str
    window_end: int  # epoch milliseconds
    queue_depth: int
    in_progress: int
    total_orders: int
    avg_wait_minutes: Optional[float]
    max_wait_minutes: Optional[float]
    orders_picked_up: int


class SystemTimeseriesPoint(BaseModel):
    """A single point-in-time snapshot of system-wide order state."""
    id: str
    window_end: int  # epoch milliseconds (snapshot time)
    total_queue_depth: int  # orders waiting (CREATED status)
    total_in_progress: int  # orders being worked (PICKING/OUT_FOR_DELIVERY)
    total_orders: int  # queue_depth + in_progress
    avg_wait_minutes: Optional[float]  # wait time for COMPLETED pickups in this window
    max_wait_minutes: Optional[float]  # max wait time for COMPLETED pickups in this window
    total_orders_picked_up: int  # throughput: orders delivered this minute
    # Current queue wait: wait time for orders STILL waiting (created in this window)
    queue_orders_waiting: Optional[int] = None
    queue_avg_wait_minutes: Optional[float] = None
    queue_max_wait_minutes: Optional[float] = None


class TimeseriesResponse(BaseModel):
    """Combined timeseries response for the metrics dashboard."""
    store_timeseries: list[StoreTimeseriesPoint]
    system_timeseries: list[SystemTimeseriesPoint]


async def get_mz_session() -> AsyncSession:
    """Dependency to get Materialize session for timeseries queries."""
    factory = get_mz_session_factory()
    async with factory() as session:
        await session.execute(text("SET CLUSTER = serving"))
        yield session


@router.get("/timeseries", response_model=TimeseriesResponse)
async def get_timeseries(
    store_id: Optional[str] = Query(default=None, description="Filter by store ID"),
    limit: int = Query(default=10, ge=1, le=60, description="Number of time windows to return"),
    session: AsyncSession = Depends(get_mz_session),
):
    """
    Get time-bucketed metrics for sparkline visualization.

    Returns the most recent N time windows (1-minute buckets) of metrics data.
    This endpoint queries Materialize directly because the timeseries views
    cannot be synced through Zero (Zero requires UNIQUE indexes which
    Materialize doesn't support).

    The data includes:
    - Store-level metrics: queue depth, orders in progress, wait times per store
    - System-level metrics: aggregated totals across all stores

    Use this data for:
    - Sparkline charts showing trends over time
    - Delta indicators comparing current vs previous windows
    """
    # Session already has a transaction from the dependency (SET CLUSTER = serving)
    # Query store-level timeseries
    store_query = text("""
            SELECT
                id,
                store_id,
                window_end,
                COALESCE(queue_depth, 0) as queue_depth,
                COALESCE(in_progress, 0) as in_progress,
                COALESCE(total_orders, 0) as total_orders,
                avg_wait_minutes,
                max_wait_minutes,
                COALESCE(orders_picked_up, 0) as orders_picked_up
            FROM store_metrics_timeseries_mv
            WHERE (:store_id IS NULL OR store_id = :store_id)
            ORDER BY window_end DESC
            LIMIT :limit
    """)

    store_result = await session.execute(
        store_query,
        {"store_id": store_id, "limit": limit * 10 if store_id is None else limit}
    )
    store_rows = store_result.fetchall()

    store_timeseries = [
        StoreTimeseriesPoint(
            id=row.id,
            store_id=row.store_id,
            window_end=int(row.window_end) if row.window_end else 0,
            queue_depth=int(row.queue_depth) if row.queue_depth else 0,
            in_progress=int(row.in_progress) if row.in_progress else 0,
            total_orders=int(row.total_orders) if row.total_orders else 0,
            avg_wait_minutes=float(row.avg_wait_minutes) if row.avg_wait_minutes else None,
            max_wait_minutes=float(row.max_wait_minutes) if row.max_wait_minutes else None,
            orders_picked_up=int(row.orders_picked_up) if row.orders_picked_up else 0,
        )
        for row in store_rows
    ]

    # Query system-level point-in-time snapshots
    # This view shows actual queue depth and in-progress counts at each minute
    system_query = text("""
        SELECT
            id,
            window_end,
            COALESCE(total_queue_depth, 0) as total_queue_depth,
            COALESCE(total_in_progress, 0) as total_in_progress,
            COALESCE(total_orders, 0) as total_orders,
            avg_wait_minutes,
            max_wait_minutes,
            COALESCE(total_orders_picked_up, 0) as total_orders_picked_up
        FROM system_metrics_timeseries_mv
        ORDER BY window_end DESC
        LIMIT :limit
    """)

    system_result = await session.execute(system_query, {"limit": limit})
    system_rows = system_result.fetchall()

    # Query current queue wait timeseries (orders still waiting, bucketed by creation time)
    queue_wait_query = text("""
        SELECT
            window_end_ms,
            orders_waiting,
            queue_avg_wait_minutes,
            queue_max_wait_minutes
        FROM current_queue_wait_timeseries
        ORDER BY window_end_ms DESC
    """)

    queue_wait_result = await session.execute(queue_wait_query)
    queue_wait_rows = queue_wait_result.fetchall()

    # Build a lookup map of queue wait data by window_end
    queue_wait_by_window = {
        int(row.window_end_ms): {
            "orders_waiting": int(row.orders_waiting) if row.orders_waiting else 0,
            "avg_wait": float(row.queue_avg_wait_minutes) if row.queue_avg_wait_minutes else None,
            "max_wait": float(row.queue_max_wait_minutes) if row.queue_max_wait_minutes else None,
        }
        for row in queue_wait_rows
    }

    # Merge system timeseries with queue wait data
    system_timeseries = []
    for row in system_rows:
        window_end = int(row.window_end) if row.window_end else 0
        queue_data = queue_wait_by_window.get(window_end, {})

        system_timeseries.append(
            SystemTimeseriesPoint(
                id=row.id,
                window_end=window_end,
                total_queue_depth=int(row.total_queue_depth) if row.total_queue_depth else 0,
                total_in_progress=int(row.total_in_progress) if row.total_in_progress else 0,
                total_orders=int(row.total_orders) if row.total_orders else 0,
                avg_wait_minutes=float(row.avg_wait_minutes) if row.avg_wait_minutes else None,
                max_wait_minutes=float(row.max_wait_minutes) if row.max_wait_minutes else None,
                total_orders_picked_up=int(row.total_orders_picked_up) if row.total_orders_picked_up else 0,
                queue_orders_waiting=queue_data.get("orders_waiting"),
                queue_avg_wait_minutes=queue_data.get("avg_wait"),
                queue_max_wait_minutes=queue_data.get("max_wait"),
            )
        )

    return TimeseriesResponse(
        store_timeseries=store_timeseries,
        system_timeseries=system_timeseries,
    )


class StoreQueueWait(BaseModel):
    """Current queue wait time for a single store."""
    store_id: str
    orders_waiting: int
    avg_wait_minutes: Optional[float]
    max_wait_minutes: Optional[float]
    min_wait_minutes: Optional[float]


class SystemQueueWait(BaseModel):
    """System-wide current queue wait time."""
    orders_waiting: int
    avg_wait_minutes: Optional[float]
    max_wait_minutes: Optional[float]
    min_wait_minutes: Optional[float]


class CurrentQueueWaitResponse(BaseModel):
    """Current wait times for orders still in queue (not yet picked up)."""
    system: SystemQueueWait
    by_store: list[StoreQueueWait]


@router.get("/queue-wait", response_model=CurrentQueueWaitResponse)
async def get_current_queue_wait(
    session: AsyncSession = Depends(get_mz_session),
):
    """
    Get real-time wait times for orders currently in queue.

    Unlike the historical wait time metrics which only show completed pickups,
    this endpoint shows how long orders have been waiting RIGHT NOW.

    This is useful for monitoring queue buildup when couriers are unavailable.
    The wait times will grow continuously until orders are picked up.
    """
    # Query system-wide current queue wait
    system_query = text("""
        SELECT
            COALESCE(orders_waiting, 0) AS orders_waiting,
            avg_wait_minutes,
            max_wait_minutes,
            min_wait_minutes
        FROM current_queue_wait_system
    """)

    system_result = await session.execute(system_query)
    system_row = system_result.fetchone()

    if system_row:
        system_wait = SystemQueueWait(
            orders_waiting=int(system_row.orders_waiting),
            avg_wait_minutes=float(system_row.avg_wait_minutes) if system_row.avg_wait_minutes else None,
            max_wait_minutes=float(system_row.max_wait_minutes) if system_row.max_wait_minutes else None,
            min_wait_minutes=float(system_row.min_wait_minutes) if system_row.min_wait_minutes else None,
        )
    else:
        system_wait = SystemQueueWait(
            orders_waiting=0,
            avg_wait_minutes=None,
            max_wait_minutes=None,
            min_wait_minutes=None,
        )

    # Query per-store current queue wait
    store_query = text("""
        SELECT
            store_id,
            orders_waiting,
            avg_wait_minutes,
            max_wait_minutes,
            min_wait_minutes
        FROM current_queue_wait_by_store
        ORDER BY orders_waiting DESC
    """)

    store_result = await session.execute(store_query)
    store_rows = store_result.fetchall()

    store_waits = [
        StoreQueueWait(
            store_id=row.store_id,
            orders_waiting=int(row.orders_waiting),
            avg_wait_minutes=float(row.avg_wait_minutes) if row.avg_wait_minutes else None,
            max_wait_minutes=float(row.max_wait_minutes) if row.max_wait_minutes else None,
            min_wait_minutes=float(row.min_wait_minutes) if row.min_wait_minutes else None,
        )
        for row in store_rows
    ]

    return CurrentQueueWaitResponse(
        system=system_wait,
        by_store=store_waits,
    )
