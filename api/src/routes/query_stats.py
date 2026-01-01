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
MAX_SAMPLES = 500000  # Keep 3 min of history even at high QPS (~2700 QPS * 180s). Memory: ~12MB per source.
BATCH_REFRESH_INTERVAL = 60  # seconds
HEARTBEAT_INTERVAL = 0.5  # 500ms
QPS_WINDOW_SIZE = 1.0  # 1 second rolling window for QPS calculation

# Concurrency limits per source (Freshmart approach)
# PostgreSQL VIEW is slow, so limit to 1 concurrent query
# Batch cache and Materialize are fast, allow more concurrency
#
# NOTE: Connection Pool Management
# Total concurrent connections = sum of concurrency limits across all sources
# PostgreSQL (1) + Batch queries (5) + Materialize (5) + Batch refresh (1) + Heartbeat (1) = 13 connections
# Ensure your database connection pools are sized accordingly (e.g., pg_pool_size >= 15, mz_pool_size >= 10)
CONCURRENCY_LIMITS = {
    "postgresql_view": 1,   # Slow query - 1 at a time
    "batch_cache": 5,       # Memory read - up to 5 concurrent
    "materialize": 5,       # Fast query - up to 5 concurrent
}

# Throttle rates per source (seconds between query batches)
# This controls how often we record metrics, not actual query capability
THROTTLE_RATES = {
    "postgresql_view": 0.0,  # No throttle - already slow
    "batch_cache": 0.0,      # No throttle - show actual throughput
    "materialize": 0.0,      # No throttle - show actual throughput
}


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

# Lock for protecting global state access
state_lock: Optional[asyncio.Lock] = None


def get_state_lock() -> asyncio.Lock:
    """Get or create the state lock (lazy initialization for async context)."""
    global state_lock
    if state_lock is None:
        state_lock = asyncio.Lock()
    return state_lock


@dataclass
class SourceMetrics:
    """Metrics for a single data source with QPS tracking (Freshmart approach)."""

    response_times: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    reaction_times: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    # Timestamps for each sample (for time-based chart display)
    sample_timestamps: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    # Timestamps for QPS calculation (rolling window) - use deque for O(1) popleft
    query_timestamps: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    query_count: int = 0
    last_query_time: float = 0

    def record(self, response_ms: float, reaction_ms: float):
        """Record a query measurement."""
        now = time.time()
        self.response_times.append(response_ms)
        self.reaction_times.append(reaction_ms)
        self.sample_timestamps.append(now * 1000)  # Store as milliseconds for JS
        self.query_count += 1
        self.last_query_time = now
        # Record timestamp for QPS calculation
        self.query_timestamps.append(now)

    def calculate_qps(self) -> float:
        """Calculate queries per second using a rolling window (Freshmart approach).

        Uses a 1-second sliding window to count how many queries were executed.
        This measures throughput - how many queries/second each source can handle.
        """
        current_time = time.time()
        cutoff_time = current_time - QPS_WINDOW_SIZE

        # Remove old timestamps outside the window (O(1) with deque)
        while self.query_timestamps and self.query_timestamps[0] < cutoff_time:
            self.query_timestamps.popleft()

        # Calculate QPS
        if len(self.query_timestamps) < 2:
            return len(self.query_timestamps) / QPS_WINDOW_SIZE

        # Time span of measurements in the window
        time_span = current_time - self.query_timestamps[0]
        if time_span <= 0:
            return 0.0

        return len(self.query_timestamps) / time_span

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
            "qps": round(self.calculate_qps(), 1),
        }

    def clear(self):
        """Clear all recorded samples."""
        self.response_times.clear()
        self.reaction_times.clear()
        self.sample_timestamps.clear()
        self.query_timestamps.clear()
        self.query_count = 0


# Global metrics store
metrics_store = {
    "postgresql_view": SourceMetrics(),
    "batch_cache": SourceMetrics(),
    "materialize": SourceMetrics(),
}


def parse_effective_updated_at(effective_updated: Any) -> datetime:
    """Parse effective_updated_at into a timezone-aware datetime.

    Handles both string ISO format and datetime objects.
    Returns a UTC datetime object.
    """
    if isinstance(effective_updated, str):
        updated_at = datetime.fromisoformat(effective_updated.replace('Z', '+00:00'))
    else:
        updated_at = effective_updated
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return updated_at


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
                        await session.commit()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"Heartbeat update failed: {e}", exc_info=True)
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Heartbeat loop stopped")
        raise


# In-memory batch cache for the selected order (refreshed every 20 seconds)
batch_cache_data: dict[str, Any] = {
    "order": None,
    "pricing": [],
    "last_refresh": None,
}


async def batch_refresh_loop():
    """Refresh PostgreSQL MATERIALIZED VIEWs every 20 seconds.

    This demonstrates the traditional batch/ETL approach:
    - REFRESH MATERIALIZED VIEW recomputes the entire view (SLOW)
    - Queries against the MV are fast (pre-computed, indexed)
    - Data is stale between refreshes (up to 20 seconds old)

    We refresh two materialized views:
    1. orders_with_lines_batch - order data with line items
    2. inventory_items_with_dynamic_pricing_batch - live pricing calculations
    """
    global batch_cache_data
    logger.info("Starting batch refresh loop (PostgreSQL MATERIALIZED VIEW)")
    first_run = True
    try:
        while True:
            # Wait for interval (skip on first run to get immediate data)
            if not first_run:
                await asyncio.sleep(BATCH_REFRESH_INTERVAL)
            first_run = False

            try:
                start = time.perf_counter()
                async with get_pg_session() as session:
                    # Refresh the orders batch materialized view
                    await session.execute(text("REFRESH MATERIALIZED VIEW orders_with_lines_batch"))

                    # Refresh the pricing batch materialized view
                    await session.execute(text("REFRESH MATERIALIZED VIEW inventory_items_with_dynamic_pricing_batch"))

                    # Update the refresh log
                    await session.execute(
                        text("""
                            UPDATE materialized_view_refresh_log
                            SET last_refresh = NOW()
                            WHERE view_name IN ('orders_with_lines_batch', 'inventory_items_with_dynamic_pricing_batch')
                        """)
                    )
                    await session.commit()

                # Track last refresh time for metrics
                async with get_state_lock():
                    batch_cache_data["last_refresh"] = datetime.now(timezone.utc)

                duration_ms = (time.perf_counter() - start) * 1000
                logger.info(f"Batch MATERIALIZED VIEWs refreshed in {duration_ms:.1f}ms")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Batch refresh failed: {e}", exc_info=True)
    except asyncio.CancelledError:
        logger.info("Batch refresh loop stopped")
        raise


# Semaphores for concurrency control (Freshmart approach)
source_semaphores: dict[str, asyncio.Semaphore] = {}


async def continuous_load_generator(source: str, query_func):
    """Generate continuous query load for a single source (Freshmart approach).

    This fires queries up to the concurrency limit with optional throttling.
    Throttle rates control how often metrics are recorded for chart readability.
    """
    global current_order_id, current_store_id, source_semaphores

    # Create semaphore for this source's concurrency limit
    concurrency_limit = CONCURRENCY_LIMITS.get(source, 1)
    throttle_rate = THROTTLE_RATES.get(source, 0.0)
    semaphore = asyncio.Semaphore(concurrency_limit)
    source_semaphores[source] = semaphore

    logger.info(f"Starting load generator for {source} (concurrency: {concurrency_limit}, throttle: {throttle_rate}s)")

    async def run_query():
        """Execute a single query with semaphore control."""
        async with semaphore:
            if current_order_id:
                await query_func(current_order_id, current_store_id)

    try:
        while True:
            # Check if we should continue (with lock protection)
            async with get_state_lock():
                should_continue = current_order_id is not None

            if not should_continue:
                break

            # Fire queries up to concurrency limit
            tasks = [asyncio.create_task(run_query()) for _ in range(concurrency_limit)]
            await asyncio.gather(*tasks, return_exceptions=True)
            # Apply throttle rate (or minimal yield if no throttle)
            await asyncio.sleep(max(throttle_rate, 0.001))
    except asyncio.CancelledError:
        logger.info(f"Load generator stopped for {source}")
        raise


async def continuous_query_loop():
    """Background task that generates continuous query load (Freshmart approach).

    Instead of polling at fixed intervals, this fires queries as fast as possible
    with per-source concurrency limits. This measures actual throughput:
    - PostgreSQL VIEW: Limited to 1 concurrent (slow queries)
    - Batch Cache: Up to 5 concurrent (fast queries)
    - Materialize: Up to 5 concurrent (fast queries)

    The QPS metric shows how many queries/second each source can sustain.
    """
    global current_order_id, current_store_id
    logger.info(f"Starting continuous load generation for order {current_order_id}")
    try:
        # Run load generators for all three sources concurrently
        await asyncio.gather(
            continuous_load_generator("postgresql_view", measure_pg_view_query),
            continuous_load_generator("batch_cache", measure_batch_query),
            continuous_load_generator("materialize", measure_mz_query),
            return_exceptions=True,
        )
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

            # Update global state with lock protection
            async with get_state_lock():
                latest_order_data["postgresql_view"] = merged

            # Reaction time = now - effective_updated_at
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                try:
                    updated_at = parse_effective_updated_at(effective_updated)
                    reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to parse timestamp for reaction time: {e}")
                    reaction_ms = response_ms
            else:
                reaction_ms = response_ms
        else:
            reaction_ms = response_ms

        metrics_store["postgresql_view"].record(response_ms, reaction_ms)
    except asyncio.CancelledError:
        # Re-raise cancellation to properly stop the task
        raise
    except Exception as e:
        logger.warning(f"PostgreSQL view query failed: {e}", exc_info=True)


async def measure_batch_query(order_id: str, store_id: Optional[str]):
    """Query PostgreSQL MATERIALIZED VIEWs and record metrics.

    This queries the batch materialized views which are refreshed every 20 seconds:
    1. orders_with_lines_batch - pre-computed order with line items
    2. inventory_items_with_dynamic_pricing_batch - pre-computed pricing

    The query is FAST (reads from pre-computed, indexed materialized view).
    But the data is STALE (up to 20 seconds old between REFRESH operations).
    """
    start = time.perf_counter()

    try:
        async with get_pg_session() as session:
            # Query the batch materialized view for the order
            order_result = await session.execute(
                text("""
                    SELECT *
                    FROM orders_with_lines_batch
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )
            order_row = order_result.mappings().fetchone()

            # Query the batch materialized view for pricing
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

            # Update global state with lock protection
            async with get_state_lock():
                latest_order_data["batch_cache"] = merged

            # Reaction time = now - effective_updated_at
            # This shows how stale the data is (up to 20 seconds between refreshes)
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                try:
                    updated_at = parse_effective_updated_at(effective_updated)
                    reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to parse timestamp for reaction time: {e}")
                    reaction_ms = BATCH_REFRESH_INTERVAL * 1000
            else:
                reaction_ms = BATCH_REFRESH_INTERVAL * 1000  # Fallback if no timestamp
        else:
            reaction_ms = BATCH_REFRESH_INTERVAL * 1000  # No data yet

        metrics_store["batch_cache"].record(response_ms, reaction_ms)
    except asyncio.CancelledError:
        # Re-raise cancellation to properly stop the task
        raise
    except Exception as e:
        logger.warning(f"Batch query failed: {e}", exc_info=True)


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

            # Update global state with lock protection
            async with get_state_lock():
                latest_order_data["materialize"] = merged

            # Reaction time = now - effective_updated_at (includes replication lag)
            effective_updated = merged.get("effective_updated_at")
            if effective_updated:
                try:
                    updated_at = parse_effective_updated_at(effective_updated)
                    reaction_ms = (datetime.now(timezone.utc) - updated_at).total_seconds() * 1000
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"Failed to parse timestamp for reaction time: {e}")
                    reaction_ms = response_ms
            else:
                reaction_ms = response_ms
        else:
            reaction_ms = response_ms

        metrics_store["materialize"].record(response_ms, reaction_ms)
    except asyncio.CancelledError:
        # Re-raise cancellation to properly stop the task
        raise
    except Exception as e:
        logger.warning(f"Materialize query failed: {e}", exc_info=True)


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
    store_id = None
    try:
        async with get_mz_session() as session:
            await session.execute(text("SET CLUSTER = serving"))
            result = await session.execute(
                text("SELECT store_id FROM orders_with_lines_mv WHERE order_id = :order_id"),
                {"order_id": order_id}
            )
            row = result.mappings().fetchone()
            store_id = row["store_id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to get store_id: {e}")

    # Update global state with lock protection
    async with get_state_lock():
        current_order_id = order_id
        current_store_id = store_id
        is_polling = True

        # Reset metrics and order data
        for m in metrics_store.values():
            m.clear()
        for key in latest_order_data:
            latest_order_data[key] = None

        # Reset batch cache
        batch_cache_data["order"] = None
        batch_cache_data["pricing"] = []
        batch_cache_data["last_refresh"] = None

    # Start background tasks
    heartbeat_task = asyncio.create_task(heartbeat_loop())
    polling_task = asyncio.create_task(continuous_query_loop())
    batch_refresh_task = asyncio.create_task(batch_refresh_loop())

    logger.info(f"Started polling for order {order_id} (store: {store_id})")
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics/history")
async def get_metrics_history():
    """Get raw metrics history for charting with timestamps."""
    return {
        "order_id": current_order_id,
        "postgresql_view": {
            "reaction_times": list(metrics_store["postgresql_view"].reaction_times),
            "response_times": list(metrics_store["postgresql_view"].response_times),
            "timestamps": list(metrics_store["postgresql_view"].sample_timestamps),
        },
        "batch_cache": {
            "reaction_times": list(metrics_store["batch_cache"].reaction_times),
            "response_times": list(metrics_store["batch_cache"].response_times),
            "timestamps": list(metrics_store["batch_cache"].sample_timestamps),
        },
        "materialize": {
            "reaction_times": list(metrics_store["materialize"].reaction_times),
            "response_times": list(metrics_store["materialize"].response_times),
            "timestamps": list(metrics_store["materialize"].sample_timestamps),
        },
    }


@router.get("/order-data")
async def get_order_data():
    """Get latest order data from all three sources.

    Returns the most recent query results from each data source,
    allowing the UI to display three order cards side-by-side.
    Each order includes line items enriched with live pricing data.
    """
    # Read global state with lock protection
    async with get_state_lock():
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
            await session.commit()

        return {"status": "written", "timestamp": datetime.now(timezone.utc).isoformat()}
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
