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
    """A single timeseries data point for system-wide metrics."""
    id: str
    window_end: int  # epoch milliseconds
    total_queue_depth: int
    total_in_progress: int
    total_orders: int
    avg_wait_minutes: Optional[float]
    max_wait_minutes: Optional[float]
    total_orders_picked_up: int


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
    # Wrap both queries in a transaction to ensure consistent snapshot
    async with session.begin():
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

        # Query system-level timeseries
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

        system_timeseries = [
            SystemTimeseriesPoint(
                id=row.id,
                window_end=int(row.window_end) if row.window_end else 0,
                total_queue_depth=int(row.total_queue_depth) if row.total_queue_depth else 0,
                total_in_progress=int(row.total_in_progress) if row.total_in_progress else 0,
                total_orders=int(row.total_orders) if row.total_orders else 0,
                avg_wait_minutes=float(row.avg_wait_minutes) if row.avg_wait_minutes else None,
                max_wait_minutes=float(row.max_wait_minutes) if row.max_wait_minutes else None,
                total_orders_picked_up=int(row.total_orders_picked_up) if row.total_orders_picked_up else 0,
            )
            for row in system_rows
        ]

    return TimeseriesResponse(
        store_timeseries=store_timeseries,
        system_timeseries=system_timeseries,
    )
