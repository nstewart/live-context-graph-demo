"""Query Statistics API for comparing data access patterns.

This module provides endpoints for measuring and comparing:
1. PostgreSQL View (orders + inventory_items_with_dynamic_pricing) - On-demand computed (fresh but SLOW)
2. Batch MATERIALIZED VIEW (orders + inventory_items_with_dynamic_pricing_batch) - Refreshed every 60s (fast but stale)
3. Materialize (orders_with_lines_mv + inventory_items_with_dynamic_pricing_mv) - Incrementally maintained (fast AND fresh)

The comparison queries:
- Order details (number, status, customer, store, line items)
- Dynamic pricing for each line item's product (7 pricing factors)

Key metrics:
- Response Time: Query latency (time to execute the query)
- Reaction Time: End-to-end latency = NOW() - effective_updated_at (freshness)
"""

import asyncio
import json
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from src.db.client import get_mz_session, get_pg_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/query-stats", tags=["Query Statistics"])

# Configuration
MAX_SAMPLES = 1800  # Keep last 1800 samples (3 minutes at 100ms intervals)
BATCH_REFRESH_INTERVAL = 60  # seconds
POLLING_INTERVAL = 0.1  # 100ms
HEARTBEAT_INTERVAL = 1.0  # 1 second


# Global state
current_order_id: Optional[str] = None
current_store_id: Optional[str] = None  # Cache store_id for the selected order
polling_task: Optional[asyncio.Task] = None
batch_refresh_task: Optional[asyncio.Task] = None
heartbeat_task: Optional[asyncio.Task] = None
is_polling: bool = False

# Store latest order data from each source
latest_order_data: dict[str, Optional[dict]] = {
    "postgresql_view": None,
    "batch_cache": None,
    "materialize": None,
}


@dataclass
class SourceMetrics:
    """Metrics for a single data source."""

    response_times: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    reaction_times: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    query_count: int = 0
    last_query_time: float = 0

    def record(self, response_ms: float, reaction_ms: float):
        """Record a query measurement."""
        self.response_times.append(response_ms)
        self.reaction_times.append(reaction_ms)
        self.query_count += 1
        self.last_query_time = time.time()

    def stats(self) -> dict:
        """Calculate statistics from recorded samples."""

        def calc_stats(samples):
            if not samples:
                return {"median": 0, "max": 0, "p99": 0}
            sorted_samples = sorted(samples)
            p99_idx = min(int(len(sorted_samples) * 0.99), len(sorted_samples) - 1)
            return {
                "median": round(statistics.median(samples), 2),
                "max": round(max(samples), 2),
                "p99": round(sorted_samples[p99_idx], 2),
            }

        return {
            "response_time": calc_stats(list(self.response_times)),
            "reaction_time": calc_stats(list(self.reaction_times)),
            "sample_count": len(self.response_times),
        }

    def clear(self):
        """Clear all recorded samples."""
        self.response_times.clear()
        self.reaction_times.clear()
        self.query_count = 0


# Global metrics store
metrics_store = {
    "postgresql_view": SourceMetrics(),
    "batch_cache": SourceMetrics(),
    "materialize": SourceMetrics(),
}


def serialize_value(value: Any) -> Any:
    """Convert a database value to JSON-serializable format."""
    if isinstance(value, Decimal):
        return float(value)
    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, str):
        # Try to parse as JSON if it looks like JSON
        if value.startswith('[') or value.startswith('{'):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
    return value


def serialize_row(row: dict) -> dict:
    """Convert a database row to JSON-serializable dict."""
    return {key: serialize_value(value) for key, value in row.items()}


def merge_order_with_pricing(order_row: dict, pricing_rows: list[dict]) -> dict:
    """Merge order data with live pricing for line items."""
    order = serialize_row(order_row)

    # Build pricing lookup by product_id
    pricing_by_product = {}
    max_pricing_updated_at = None
    for row in pricing_rows:
        product_id = row.get("product_id")
        if product_id:
            pricing_by_product[product_id] = {
                "live_price": float(row["live_price"]) if row.get("live_price") else None,
                "base_price": float(row["base_price"]) if row.get("base_price") else None,
                "price_change": float(row["price_change"]) if row.get("price_change") else None,
                "stock_level": row.get("stock_level"),
            }
            # Track the most recent pricing update
            if row.get("effective_updated_at"):
                updated_at = row["effective_updated_at"]
                if max_pricing_updated_at is None or updated_at > max_pricing_updated_at:
                    max_pricing_updated_at = updated_at

    # Enrich line items with live pricing
    line_items = order.get("line_items", [])
    if isinstance(line_items, str):
        try:
            line_items = json.loads(line_items)
        except (json.JSONDecodeError, TypeError):
            line_items = []

    enriched_items = []
    for item in line_items:
        product_id = item.get("product_id")
        pricing = pricing_by_product.get(product_id, {})
        enriched_item = {
            **item,
            "live_price": pricing.get("live_price"),
            "base_price": pricing.get("base_price"),
            "price_change": pricing.get("price_change"),
            "current_stock": pricing.get("stock_level"),
        }
        enriched_items.append(enriched_item)

    order["line_items"] = enriched_items
    order["pricing_data"] = pricing_by_product

    # Use the most recent timestamp between order and pricing for effective_updated_at
    order_updated = order.get("effective_updated_at")
    if isinstance(order_updated, str):
        try:
            order_updated = datetime.fromisoformat(order_updated.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            order_updated = None

    if max_pricing_updated_at and order_updated:
        if max_pricing_updated_at.tzinfo is None:
            max_pricing_updated_at = max_pricing_updated_at.replace(tzinfo=timezone.utc)
        if order_updated.tzinfo is None:
            order_updated = order_updated.replace(tzinfo=timezone.utc)
        order["effective_updated_at"] = max(max_pricing_updated_at, order_updated).isoformat()
    elif max_pricing_updated_at:
        order["effective_updated_at"] = max_pricing_updated_at.isoformat() if isinstance(max_pricing_updated_at, datetime) else max_pricing_updated_at

    return order


# --- Background Tasks ---


async def heartbeat_loop():
    """Update the selected order's store inventory timestamp every second.

    This continuously updates the `updated_at` on an inventory item's stock_level triple,
    which propagates to `effective_updated_at` in the dynamic pricing views. This allows us
    to measure how fresh each data source is:
    - PostgreSQL View: sees update immediately (but query is SLOW due to complex pricing calc)
    - Batch MATERIALIZED VIEW: sees update after next refresh (up to 60s stale)
    - Materialize: sees update within ~100ms via CDC (AND query is fast)
    """
    global current_order_id, current_store_id
    logger.info("Starting heartbeat loop for order's store inventory")
    try:
        while True:
            if current_store_id:
                try:
                    async with get_pg_session() as session:
                        # Update an inventory item's stock_level triple timestamp for this store
                        # This triggers the effective_updated_at to change in the pricing view
                        await session.execute(
                            text("""
                                UPDATE triples
                                SET updated_at = NOW()
                                WHERE subject_id IN (
                                    SELECT subject_id FROM triples
                                    WHERE predicate = 'inventory_store'
                                    AND object_value = :store_id
                                    LIMIT 1
                                )
                                AND predicate = 'stock_level'
                            """),
                            {"store_id": current_store_id},
                        )
                except Exception as e:
                    logger.warning(f"Heartbeat update failed: {e}")
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Heartbeat loop stopped")
        raise


async def batch_refresh_loop():
    """Refresh the inventory_items_with_dynamic_pricing_batch MATERIALIZED VIEW every 60 seconds."""
    logger.info("Starting batch refresh loop")
    try:
        while True:
            await asyncio.sleep(BATCH_REFRESH_INTERVAL)
            try:
                start = time.perf_counter()
                async with get_pg_session() as session:
                    await session.execute(
                        text("REFRESH MATERIALIZED VIEW inventory_items_with_dynamic_pricing_batch")
                    )
                    # Update the refresh log
                    duration_ms = (time.perf_counter() - start) * 1000
                    await session.execute(
                        text("""
                            UPDATE materialized_view_refresh_log
                            SET last_refresh = NOW(), refresh_duration_ms = :duration
                            WHERE view_name = 'inventory_items_with_dynamic_pricing_batch'
                        """),
                        {"duration": duration_ms},
                    )
                logger.info(f"Batch MATERIALIZED VIEW refreshed in {duration_ms:.1f}ms")
            except Exception as e:
                logger.warning(f"Batch refresh failed: {e}")
    except asyncio.CancelledError:
        logger.info("Batch refresh loop stopped")
        raise


async def continuous_query_loop():
    """Background task that continuously queries all three sources."""
    global current_order_id, current_store_id
    logger.info(f"Starting continuous query loop for order {current_order_id}")
    try:
        while current_order_id:
            order_id = current_order_id
            store_id = current_store_id
            await asyncio.gather(
                measure_pg_view_query(order_id, store_id),
                measure_batch_query(order_id, store_id),
                measure_mz_query(order_id, store_id),
                return_exceptions=True,
            )
            await asyncio.sleep(POLLING_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Continuous query loop stopped")
        raise


async def measure_pg_view_query(order_id: str, store_id: Optional[str]):
    """Query PostgreSQL VIEWs and record metrics.

    This queries:
    1. orders_with_lines_full VIEW (order + line items)
    2. inventory_items_with_dynamic_pricing VIEW (live pricing with 7 factors)

    The dynamic pricing VIEW is SLOW because it computes complex pricing logic:
    - Sales velocity calculations
    - Popularity scoring with window functions
    - Inventory scarcity rankings
    - 7 pricing adjustment factors
    """
    start = time.perf_counter()

    try:
        async with get_pg_session() as session:
            # Query order with line items
            order_result = await session.execute(
                text("""
                    SELECT *
                    FROM orders_with_lines_full
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )
            order_row = order_result.mappings().fetchone()

            # Query dynamic pricing for the store (THIS IS THE SLOW QUERY)
            pricing_rows = []
            if store_id:
                pricing_result = await session.execute(
                    text("""
                        SELECT product_id, live_price, base_price, price_change,
                               stock_level, effective_updated_at
                        FROM inventory_items_with_dynamic_pricing
                        WHERE store_id = :store_id
                    """),
                    {"store_id": store_id},
                )
                pricing_rows = [dict(row) for row in pricing_result.mappings().fetchall()]

        response_ms = (time.perf_counter() - start) * 1000

        # Merge order with live pricing
        if order_row:
            merged = merge_order_with_pricing(dict(order_row), pricing_rows)
            latest_order_data["postgresql_view"] = merged

            # Reaction time = now - effective_updated_at
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                if isinstance(effective_updated, str):
                    updated_at = datetime.fromisoformat(effective_updated.replace('Z', '+00:00'))
                else:
                    updated_at = effective_updated
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
            else:
                reaction_ms = response_ms
        else:
            reaction_ms = response_ms

        metrics_store["postgresql_view"].record(response_ms, reaction_ms)
    except Exception as e:
        logger.warning(f"PostgreSQL view query failed: {e}")


async def measure_batch_query(order_id: str, store_id: Optional[str]):
    """Query batch MATERIALIZED VIEWs and record metrics.

    This queries:
    1. orders_with_lines_batch MATERIALIZED VIEW (order + line items)
    2. inventory_items_with_dynamic_pricing_batch MATERIALIZED VIEW (pre-computed pricing)

    Both MATERIALIZED VIEWs are pre-computed and refreshed every 60 seconds.
    The query is FAST because it reads pre-computed results.
    But the data is STALE (up to 60 seconds old).
    """
    start = time.perf_counter()

    try:
        async with get_pg_session() as session:
            # Query order with line items from batch cache
            order_result = await session.execute(
                text("""
                    SELECT *
                    FROM orders_with_lines_batch
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )
            order_row = order_result.mappings().fetchone()

            # Query pre-computed pricing from batch cache
            pricing_rows = []
            if store_id:
                pricing_result = await session.execute(
                    text("""
                        SELECT product_id, live_price, base_price, price_change,
                               stock_level, effective_updated_at
                        FROM inventory_items_with_dynamic_pricing_batch
                        WHERE store_id = :store_id
                    """),
                    {"store_id": store_id},
                )
                pricing_rows = [dict(row) for row in pricing_result.mappings().fetchall()]

        response_ms = (time.perf_counter() - start) * 1000

        # Merge order with pricing
        if order_row:
            merged = merge_order_with_pricing(dict(order_row), pricing_rows)
            latest_order_data["batch_cache"] = merged

            # Reaction time = now - effective_updated_at (shows staleness)
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                if isinstance(effective_updated, str):
                    updated_at = datetime.fromisoformat(effective_updated.replace('Z', '+00:00'))
                else:
                    updated_at = effective_updated
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
            else:
                reaction_ms = 60000  # Assume max staleness if no data
        else:
            reaction_ms = 60000

        metrics_store["batch_cache"].record(response_ms, reaction_ms)
    except Exception as e:
        logger.warning(f"Batch query failed: {e}")


async def measure_mz_query(order_id: str, store_id: Optional[str]):
    """Query Materialize and record metrics.

    This queries:
    1. orders_with_lines_mv (order + line items)
    2. inventory_items_with_dynamic_pricing_mv (live pricing)

    Both are INCREMENTALLY MAINTAINED by Materialize via CDC.
    The query is FAST (reads pre-computed results from indexed views).
    The data is FRESH (typically ~100ms lag via streaming replication).

    This is the best of both worlds: fast queries AND fresh data.
    """
    start = time.perf_counter()

    try:
        async with get_mz_session() as session:
            await session.execute(text("SET CLUSTER = serving"))

            # Query order with line items
            order_result = await session.execute(
                text("""
                    SELECT *
                    FROM orders_with_lines_mv
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )
            order_row = order_result.mappings().fetchone()

            # Query live pricing from Materialize
            pricing_rows = []
            if store_id:
                pricing_result = await session.execute(
                    text("""
                        SELECT product_id, live_price, base_price, price_change,
                               stock_level, effective_updated_at
                        FROM inventory_items_with_dynamic_pricing_mv
                        WHERE store_id = :store_id
                    """),
                    {"store_id": store_id},
                )
                pricing_rows = [dict(row) for row in pricing_result.mappings().fetchall()]

        response_ms = (time.perf_counter() - start) * 1000

        # Merge order with pricing
        if order_row:
            merged = merge_order_with_pricing(dict(order_row), pricing_rows)
            latest_order_data["materialize"] = merged

            # Reaction time = now - effective_updated_at (includes replication lag)
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                if isinstance(effective_updated, str):
                    updated_at = datetime.fromisoformat(effective_updated.replace('Z', '+00:00'))
                else:
                    updated_at = effective_updated
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
            else:
                reaction_ms = response_ms
        else:
            reaction_ms = response_ms

        metrics_store["materialize"].record(response_ms, reaction_ms)
    except Exception as e:
        logger.warning(f"Materialize query failed: {e}")


# --- Pydantic Models ---


class TripleWrite(BaseModel):
    """Request body for writing a triple."""

    subject_id: str
    predicate: str
    object_value: str


class StartPollingResponse(BaseModel):
    """Response for starting polling."""

    status: str
    order_id: str


class StopPollingResponse(BaseModel):
    """Response for stopping polling."""

    status: str


class OrderInfo(BaseModel):
    """Order information for dropdown."""

    order_id: str
    order_number: Optional[str]
    order_status: Optional[str]
    customer_name: Optional[str]
    store_name: Optional[str]
    store_id: Optional[str]


class OrderPredicate(BaseModel):
    """Predicate information for the write triple form."""

    predicate: str
    description: Optional[str]


# --- Endpoints ---


@router.get("/orders", response_model=list[OrderInfo])
async def list_orders():
    """Get available orders for dropdown selection."""
    try:
        async with get_mz_session() as session:
            await session.execute(text("SET CLUSTER = serving"))
            result = await session.execute(
                text("""
                    SELECT order_id, order_number, order_status, customer_name, store_name, store_id
                    FROM orders_with_lines_mv
                    ORDER BY effective_updated_at DESC
                    LIMIT 50
                """)
            )
            rows = result.mappings().fetchall()
            return [
                OrderInfo(
                    order_id=row["order_id"],
                    order_number=row.get("order_number"),
                    order_status=row.get("order_status"),
                    customer_name=row.get("customer_name"),
                    store_name=row.get("store_name"),
                    store_id=row.get("store_id"),
                )
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Failed to list orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order-predicates", response_model=list[OrderPredicate])
async def list_order_predicates():
    """Get available predicates for orders from the ontology."""
    try:
        async with get_pg_session() as session:
            result = await session.execute(
                text("""
                    SELECT p.prop_name, p.description
                    FROM ontology_properties p
                    JOIN ontology_classes c ON c.id = p.domain_class_id
                    WHERE c.class_name = 'Order'
                    ORDER BY p.prop_name
                """)
            )
            rows = result.mappings().fetchall()
            return [
                OrderPredicate(
                    predicate=row["prop_name"],
                    description=row.get("description"),
                )
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Failed to list order predicates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start/{order_id}", response_model=StartPollingResponse)
async def start_polling(order_id: str):
    """Start continuous polling for an order."""
    global current_order_id, current_store_id, polling_task, batch_refresh_task, heartbeat_task, is_polling

    # Stop any existing tasks
    await stop_all_tasks()

    # Get the store_id for this order
    try:
        async with get_mz_session() as session:
            await session.execute(text("SET CLUSTER = serving"))
            result = await session.execute(
                text("SELECT store_id FROM orders_with_lines_mv WHERE order_id = :order_id"),
                {"order_id": order_id}
            )
            row = result.mappings().fetchone()
            current_store_id = row["store_id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to get store_id: {e}")
        current_store_id = None

    # Set current order
    current_order_id = order_id
    is_polling = True

    # Reset metrics and order data
    for m in metrics_store.values():
        m.clear()
    for key in latest_order_data:
        latest_order_data[key] = None

    # Start background tasks
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    polling_task = asyncio.create_task(continuous_query_loop())
    batch_refresh_task = asyncio.create_task(batch_refresh_loop())

    logger.info(f"Started polling for order {order_id} (store: {current_store_id})")
    return StartPollingResponse(status="started", order_id=order_id)


@router.post("/stop", response_model=StopPollingResponse)
async def stop_polling():
    """Stop continuous polling."""
    global is_polling
    is_polling = False
    await stop_all_tasks()
    logger.info("Stopped polling")
    return StopPollingResponse(status="stopped")


async def stop_all_tasks():
    """Stop all background tasks."""
    global current_order_id, current_store_id, polling_task, batch_refresh_task, heartbeat_task

    current_order_id = None
    current_store_id = None

    for task in [polling_task, batch_refresh_task, heartbeat_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    polling_task = None
    batch_refresh_task = None
    heartbeat_task = None


@router.get("/metrics")
async def get_metrics():
    """Get current aggregated metrics for all sources."""
    return {
        "order_id": current_order_id,
        "is_polling": is_polling,
        "postgresql_view": metrics_store["postgresql_view"].stats(),
        "batch_cache": metrics_store["batch_cache"].stats(),
        "materialize": metrics_store["materialize"].stats(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/metrics/history")
async def get_metrics_history():
    """Get raw metrics history for charting."""
    return {
        "order_id": current_order_id,
        "postgresql_view": {
            "reaction_times": list(metrics_store["postgresql_view"].reaction_times)
        },
        "batch_cache": {"reaction_times": list(metrics_store["batch_cache"].reaction_times)},
        "materialize": {"reaction_times": list(metrics_store["materialize"].reaction_times)},
    }


@router.get("/order-data")
async def get_order_data():
    """Get latest order data from all three sources.

    Returns the most recent query results from each data source,
    allowing the UI to display three order cards side-by-side.
    Each order includes line items enriched with live pricing data.
    """
    return {
        "order_id": current_order_id,
        "is_polling": is_polling,
        "postgresql_view": latest_order_data["postgresql_view"],
        "batch_cache": latest_order_data["batch_cache"],
        "materialize": latest_order_data["materialize"],
    }


@router.post("/write-triple")
async def write_triple(data: TripleWrite):
    """Write a triple to observe propagation.

    This updates an existing triple's value and timestamp,
    allowing you to observe how the change propagates through
    each data access pattern.
    """
    try:
        async with get_pg_session() as session:
            result = await session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :subject_id AND predicate = :predicate
                    RETURNING id
                """),
                {
                    "subject_id": data.subject_id,
                    "predicate": data.predicate,
                    "value": data.object_value,
                },
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail=f"Triple not found: {data.subject_id} / {data.predicate}",
                )

        return {"status": "written", "timestamp": datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to write triple: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Startup/shutdown functions removed - heartbeat now starts with polling
def start_heartbeat_generator():
    """No-op for backwards compatibility with main.py."""
    pass


def stop_heartbeat_generator():
    """No-op for backwards compatibility with main.py."""
    pass
