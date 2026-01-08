"""Integration tests for view consistency across all three data access patterns.

This test ensures that all three views return the same answer when data is stable:
1. PostgreSQL VIEW (orders_with_lines_full + inventory_items_with_dynamic_pricing)
2. Batch MATERIALIZED VIEW (orders_with_lines_batch + inventory_items_with_dynamic_pricing_batch)
3. Materialize VIEW (orders_with_lines_mv + inventory_items_with_dynamic_pricing_mv)

Key design decisions:
- No constant load: We refresh batch views and wait for Materialize CDC to catch up
- Compare business-critical fields, not timestamps (effective_updated_at will differ)
- Sort line items for consistent comparison
"""

import asyncio
import pytest
import pytest_asyncio
from decimal import Decimal
from typing import Any

from sqlalchemy import text

import src.db.client as db_client
from src.db.client import get_mz_session, get_pg_session
from tests.conftest import requires_db


@pytest_asyncio.fixture(autouse=True)
async def reset_db_connections():
    """Reset database connections before each test to avoid event loop issues."""
    # Reset global database engines
    db_client._pg_engine = None
    db_client._mz_engine = None
    db_client._pg_session_factory = None
    db_client._mz_session_factory = None
    yield
    # Cleanup connections after test
    await db_client.close_connections()


def normalize_value(value: Any) -> Any:
    """Normalize values for comparison (handle Decimal, float precision, etc.)."""
    if isinstance(value, Decimal):
        return round(float(value), 2)
    if isinstance(value, float):
        return round(value, 2)
    return value


def normalize_line_item(item: dict) -> dict:
    """Normalize a line item dict for comparison."""
    return {
        "product_id": item.get("product_id"),
        "product_name": item.get("product_name"),
        "category": item.get("category"),
        "quantity": item.get("quantity"),
        "unit_price": normalize_value(item.get("unit_price")),
        "line_amount": normalize_value(item.get("line_amount")),
        "line_sequence": item.get("line_sequence"),
        "perishable_flag": item.get("perishable_flag"),
        "live_price": normalize_value(item.get("live_price")),
        "base_price": normalize_value(item.get("base_price")),
        "price_change": normalize_value(item.get("price_change")),
        "current_stock": item.get("current_stock"),
    }


def normalize_order_data(order: dict) -> dict:
    """Normalize order data for comparison, excluding timestamp fields.

    Note: We exclude total_weight_kg as it only exists in Materialize views,
    not in the PostgreSQL views.
    """
    # Parse line_items if it's a string (JSON)
    line_items = order.get("line_items", [])
    if isinstance(line_items, str):
        import json
        line_items = json.loads(line_items)

    # Normalize and sort line items by product_id for consistent comparison
    normalized_lines = [normalize_line_item(item) for item in line_items]
    normalized_lines.sort(key=lambda x: x.get("product_id") or "")

    return {
        "order_id": order.get("order_id"),
        "order_number": order.get("order_number"),
        "order_status": order.get("order_status"),
        "store_id": order.get("store_id"),
        "customer_id": order.get("customer_id"),
        "customer_name": order.get("customer_name"),
        "customer_email": order.get("customer_email"),
        "store_name": order.get("store_name"),
        "store_zone": order.get("store_zone"),
        "line_item_count": order.get("line_item_count"),
        "computed_total": normalize_value(order.get("computed_total")),
        "has_perishable_items": order.get("has_perishable_items"),
        # Note: total_weight_kg excluded - only in Materialize views
        "line_items": normalized_lines,
    }


# Common query structure for PostgreSQL views (orders_with_lines_full, orders_with_lines_batch)
# Note: PG views don't have order_created_at or total_weight_kg columns
PG_ORDER_QUERY_TEMPLATE = """
    WITH order_data AS (
        SELECT * FROM {orders_view} WHERE order_id = :order_id
    ),
    line_items_expanded AS (
        SELECT
            o.order_id, o.order_number, o.order_status, o.store_id, o.customer_id,
            o.delivery_window_start, o.delivery_window_end, o.order_total_amount,
            o.customer_name, o.customer_email, o.customer_address,
            o.store_name, o.store_zone, o.store_address,
            o.assigned_courier_id, o.delivery_task_status, o.delivery_eta,
            o.line_item_count, o.computed_total, o.has_perishable_items,
            o.effective_updated_at,
            li.value as line_item,
            li.value->>'product_id' as li_product_id
        FROM order_data o,
        LATERAL jsonb_array_elements(o.line_items) AS li(value)
    ),
    enriched AS (
        SELECT
            lie.*,
            p.live_price,
            p.base_price,
            p.price_change,
            p.stock_level as current_stock,
            p.effective_updated_at as pricing_updated_at
        FROM line_items_expanded lie
        LEFT JOIN {pricing_view} p
            ON p.product_id = lie.li_product_id
            AND p.store_id = lie.store_id
    )
    SELECT
        order_id, order_number, order_status, store_id, customer_id,
        delivery_window_start, delivery_window_end, order_total_amount,
        customer_name, customer_email, customer_address,
        store_name, store_zone, store_address,
        assigned_courier_id, delivery_task_status, delivery_eta,
        line_item_count, computed_total, has_perishable_items,
        GREATEST(effective_updated_at, MAX(pricing_updated_at)) as effective_updated_at,
        jsonb_agg(
            jsonb_build_object(
                'line_id', line_item->>'line_id',
                'product_id', line_item->>'product_id',
                'product_name', line_item->>'product_name',
                'category', line_item->>'category',
                'quantity', (line_item->>'quantity')::int,
                'unit_price', (line_item->>'unit_price')::numeric,
                'line_amount', (line_item->>'line_amount')::numeric,
                'line_sequence', (line_item->>'line_sequence')::int,
                'perishable_flag', (line_item->>'perishable_flag')::boolean,
                'live_price', live_price,
                'base_price', base_price,
                'price_change', price_change,
                'current_stock', current_stock
            )
        ) as line_items
    FROM enriched
    GROUP BY
        order_id, order_number, order_status, store_id, customer_id,
        delivery_window_start, delivery_window_end, order_total_amount,
        customer_name, customer_email, customer_address,
        store_name, store_zone, store_address,
        assigned_courier_id, delivery_task_status, delivery_eta,
        line_item_count, computed_total, has_perishable_items,
        effective_updated_at
"""

# Query structure for Materialize views (has additional columns but we select same as PG for consistency)
MZ_ORDER_QUERY_TEMPLATE = """
    WITH order_data AS (
        SELECT * FROM {orders_view} WHERE order_id = :order_id
    ),
    line_items_expanded AS (
        SELECT
            o.order_id, o.order_number, o.order_status, o.store_id, o.customer_id,
            o.delivery_window_start, o.delivery_window_end, o.order_total_amount,
            o.customer_name, o.customer_email, o.customer_address,
            o.store_name, o.store_zone, o.store_address,
            o.assigned_courier_id, o.delivery_task_status, o.delivery_eta,
            o.line_item_count, o.computed_total, o.has_perishable_items,
            o.effective_updated_at,
            li.value as line_item,
            li.value->>'product_id' as li_product_id
        FROM order_data o,
        LATERAL jsonb_array_elements(o.line_items) AS li(value)
    ),
    enriched AS (
        SELECT
            lie.*,
            p.live_price,
            p.base_price,
            p.price_change,
            p.stock_level as current_stock,
            p.effective_updated_at as pricing_updated_at
        FROM line_items_expanded lie
        LEFT JOIN {pricing_view} p
            ON p.product_id = lie.li_product_id
            AND p.store_id = lie.store_id
    )
    SELECT
        order_id, order_number, order_status, store_id, customer_id,
        delivery_window_start, delivery_window_end, order_total_amount,
        customer_name, customer_email, customer_address,
        store_name, store_zone, store_address,
        assigned_courier_id, delivery_task_status, delivery_eta,
        line_item_count, computed_total, has_perishable_items,
        GREATEST(effective_updated_at, MAX(pricing_updated_at)) as effective_updated_at,
        jsonb_agg(
            jsonb_build_object(
                'line_id', line_item->>'line_id',
                'product_id', line_item->>'product_id',
                'product_name', line_item->>'product_name',
                'category', line_item->>'category',
                'quantity', (line_item->>'quantity')::int,
                'unit_price', (line_item->>'unit_price')::numeric,
                'line_amount', (line_item->>'line_amount')::numeric,
                'line_sequence', (line_item->>'line_sequence')::int,
                'perishable_flag', (line_item->>'perishable_flag')::boolean,
                'live_price', live_price,
                'base_price', base_price,
                'price_change', price_change,
                'current_stock', current_stock
            )
        ) as line_items
    FROM enriched
    GROUP BY
        order_id, order_number, order_status, store_id, customer_id,
        delivery_window_start, delivery_window_end, order_total_amount,
        customer_name, customer_email, customer_address,
        store_name, store_zone, store_address,
        assigned_courier_id, delivery_task_status, delivery_eta,
        line_item_count, computed_total, has_perishable_items,
        effective_updated_at
"""


async def get_order_from_pg_view(order_id: str) -> dict | None:
    """Query order data from PostgreSQL VIEW (fresh, slow)."""
    query = PG_ORDER_QUERY_TEMPLATE.format(
        orders_view="orders_with_lines_full",
        pricing_view="inventory_items_with_dynamic_pricing",
    )
    async with get_pg_session() as session:
        result = await session.execute(text(query), {"order_id": order_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_order_from_batch_view(order_id: str) -> dict | None:
    """Query order data from Batch MATERIALIZED VIEW (fast, stale)."""
    query = PG_ORDER_QUERY_TEMPLATE.format(
        orders_view="orders_with_lines_batch",
        pricing_view="inventory_items_with_dynamic_pricing_batch",
    )
    async with get_pg_session() as session:
        result = await session.execute(text(query), {"order_id": order_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def get_order_from_materialize(order_id: str) -> dict | None:
    """Query order data from Materialize VIEW (fast, fresh)."""
    query = MZ_ORDER_QUERY_TEMPLATE.format(
        orders_view="orders_with_lines_mv",
        pricing_view="inventory_items_with_dynamic_pricing_mv",
    )
    async with get_mz_session() as session:
        await session.execute(text("SET CLUSTER = serving"))
        result = await session.execute(text(query), {"order_id": order_id})
        row = result.mappings().fetchone()
        return dict(row) if row else None


async def refresh_batch_materialized_views():
    """Refresh the PostgreSQL batch materialized views to get current data."""
    async with get_pg_session() as session:
        await session.execute(text("REFRESH MATERIALIZED VIEW orders_with_lines_batch"))
        await session.execute(text("REFRESH MATERIALIZED VIEW inventory_items_with_dynamic_pricing_batch"))
        await session.commit()


async def get_sample_order_id() -> str | None:
    """Get a sample order ID from the database for testing."""
    async with get_mz_session() as session:
        await session.execute(text("SET CLUSTER = serving"))
        result = await session.execute(
            text("""
                SELECT order_id
                FROM orders_with_lines_mv
                WHERE line_item_count > 0
                LIMIT 1
            """)
        )
        row = result.fetchone()
        return row[0] if row else None


@pytest.mark.asyncio
@pytest.mark.integration
@requires_db
async def test_all_three_views_return_same_data():
    """
    Test that all three views return the same order data when data is stable.

    This test:
    1. Refreshes batch materialized views to ensure they have current data
    2. Waits for Materialize CDC to catch up
    3. Queries all three views for the same order
    4. Compares the normalized results (excluding timestamps)
    """
    # Step 1: Get a sample order to test with
    order_id = await get_sample_order_id()
    assert order_id is not None, "No orders found in database - ensure test data exists"

    # Step 2: Refresh batch materialized views to get current data
    await refresh_batch_materialized_views()

    # Step 3: Wait for Materialize CDC to catch up (no constant load)
    # This ensures all three sources have consistent data
    await asyncio.sleep(2.0)

    # Step 4: Query all three views
    pg_view_data = await get_order_from_pg_view(order_id)
    batch_view_data = await get_order_from_batch_view(order_id)
    mz_view_data = await get_order_from_materialize(order_id)

    # Step 5: Verify all views returned data
    assert pg_view_data is not None, f"PostgreSQL VIEW returned no data for order {order_id}"
    assert batch_view_data is not None, f"Batch MATERIALIZED VIEW returned no data for order {order_id}"
    assert mz_view_data is not None, f"Materialize VIEW returned no data for order {order_id}"

    # Step 6: Normalize data for comparison (exclude timestamps)
    pg_normalized = normalize_order_data(pg_view_data)
    batch_normalized = normalize_order_data(batch_view_data)
    mz_normalized = normalize_order_data(mz_view_data)

    # Step 7: Compare PostgreSQL VIEW vs Batch MATERIALIZED VIEW
    assert pg_normalized == batch_normalized, (
        f"PostgreSQL VIEW and Batch MATERIALIZED VIEW returned different data for order {order_id}.\n"
        f"PostgreSQL VIEW: {pg_normalized}\n"
        f"Batch VIEW: {batch_normalized}"
    )

    # Step 8: Compare PostgreSQL VIEW vs Materialize VIEW
    assert pg_normalized == mz_normalized, (
        f"PostgreSQL VIEW and Materialize VIEW returned different data for order {order_id}.\n"
        f"PostgreSQL VIEW: {pg_normalized}\n"
        f"Materialize VIEW: {mz_normalized}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
@requires_db
async def test_line_items_pricing_consistency():
    """
    Test that dynamic pricing fields are consistent across all three views.

    This specifically checks the pricing-related fields that are computed
    by the inventory_items_with_dynamic_pricing views:
    - live_price
    - base_price
    - price_change
    - current_stock
    """
    # Get a sample order
    order_id = await get_sample_order_id()
    assert order_id is not None, "No orders found in database"

    # Refresh batch views and wait for sync
    await refresh_batch_materialized_views()
    await asyncio.sleep(2.0)

    # Query all three views
    pg_data = await get_order_from_pg_view(order_id)
    batch_data = await get_order_from_batch_view(order_id)
    mz_data = await get_order_from_materialize(order_id)

    assert pg_data and batch_data and mz_data, "Failed to get data from all views"

    # Parse line items
    import json
    pg_lines = pg_data.get("line_items", [])
    batch_lines = batch_data.get("line_items", [])
    mz_lines = mz_data.get("line_items", [])

    if isinstance(pg_lines, str):
        pg_lines = json.loads(pg_lines)
    if isinstance(batch_lines, str):
        batch_lines = json.loads(batch_lines)
    if isinstance(mz_lines, str):
        mz_lines = json.loads(mz_lines)

    # Sort by product_id for consistent comparison
    pg_lines.sort(key=lambda x: x.get("product_id") or "")
    batch_lines.sort(key=lambda x: x.get("product_id") or "")
    mz_lines.sort(key=lambda x: x.get("product_id") or "")

    assert len(pg_lines) == len(batch_lines) == len(mz_lines), (
        f"Line item counts differ: PG={len(pg_lines)}, Batch={len(batch_lines)}, MZ={len(mz_lines)}"
    )

    # Compare pricing fields for each line item
    for i, (pg_line, batch_line, mz_line) in enumerate(zip(pg_lines, batch_lines, mz_lines)):
        product_id = pg_line.get("product_id")

        # Check live_price
        pg_live = normalize_value(pg_line.get("live_price"))
        batch_live = normalize_value(batch_line.get("live_price"))
        mz_live = normalize_value(mz_line.get("live_price"))
        assert pg_live == batch_live == mz_live, (
            f"live_price mismatch for product {product_id}: PG={pg_live}, Batch={batch_live}, MZ={mz_live}"
        )

        # Check base_price
        pg_base = normalize_value(pg_line.get("base_price"))
        batch_base = normalize_value(batch_line.get("base_price"))
        mz_base = normalize_value(mz_line.get("base_price"))
        assert pg_base == batch_base == mz_base, (
            f"base_price mismatch for product {product_id}: PG={pg_base}, Batch={batch_base}, MZ={mz_base}"
        )

        # Check price_change
        pg_change = normalize_value(pg_line.get("price_change"))
        batch_change = normalize_value(batch_line.get("price_change"))
        mz_change = normalize_value(mz_line.get("price_change"))
        assert pg_change == batch_change == mz_change, (
            f"price_change mismatch for product {product_id}: PG={pg_change}, Batch={batch_change}, MZ={mz_change}"
        )

        # Check current_stock
        pg_stock = pg_line.get("current_stock")
        batch_stock = batch_line.get("current_stock")
        mz_stock = mz_line.get("current_stock")
        assert pg_stock == batch_stock == mz_stock, (
            f"current_stock mismatch for product {product_id}: PG={pg_stock}, Batch={batch_stock}, MZ={mz_stock}"
        )


@pytest.mark.asyncio
@pytest.mark.integration
@requires_db
async def test_order_level_fields_consistency():
    """
    Test that order-level fields are consistent across all three views.

    This checks the order metadata fields that come from the orders_with_lines views:
    - order_number, order_status
    - customer_name, customer_email
    - store_name, store_zone
    - line_item_count, computed_total
    - has_perishable_items

    Note: total_weight_kg is excluded as it only exists in Materialize views.
    """
    # Get a sample order
    order_id = await get_sample_order_id()
    assert order_id is not None, "No orders found in database"

    # Refresh batch views and wait for sync
    await refresh_batch_materialized_views()
    await asyncio.sleep(2.0)

    # Query all three views
    pg_data = await get_order_from_pg_view(order_id)
    batch_data = await get_order_from_batch_view(order_id)
    mz_data = await get_order_from_materialize(order_id)

    assert pg_data and batch_data and mz_data, "Failed to get data from all views"

    # Fields to compare at the order level
    order_fields = [
        "order_id",
        "order_number",
        "order_status",
        "customer_id",
        "store_id",
        "customer_name",
        "customer_email",
        "store_name",
        "store_zone",
        "line_item_count",
        "has_perishable_items",
    ]

    for field in order_fields:
        pg_val = pg_data.get(field)
        batch_val = batch_data.get(field)
        mz_val = mz_data.get(field)

        assert pg_val == batch_val, (
            f"Order field '{field}' mismatch between PG VIEW and Batch: PG={pg_val}, Batch={batch_val}"
        )
        assert pg_val == mz_val, (
            f"Order field '{field}' mismatch between PG VIEW and Materialize: PG={pg_val}, MZ={mz_val}"
        )

    # Numeric fields with tolerance (excluding total_weight_kg - only in Materialize)
    numeric_fields = ["computed_total"]
    for field in numeric_fields:
        pg_val = normalize_value(pg_data.get(field))
        batch_val = normalize_value(batch_data.get(field))
        mz_val = normalize_value(mz_data.get(field))

        assert pg_val == batch_val, (
            f"Order field '{field}' mismatch between PG VIEW and Batch: PG={pg_val}, Batch={batch_val}"
        )
        assert pg_val == mz_val, (
            f"Order field '{field}' mismatch between PG VIEW and Materialize: PG={pg_val}, MZ={mz_val}"
        )
