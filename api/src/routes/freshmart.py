"""FreshMart API routes for operational data."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings

logger = logging.getLogger(__name__)

# Propagation API URL for setting focus context
# Uses Docker service name for inter-container communication
import os
PROPAGATION_API_URL = os.getenv("PROPAGATION_API_URL", "http://search-sync:8083")
from src.db.client import get_mz_session_factory, get_pg_session_factory
from src.freshmart.models import (
    CourierAvailable,
    CourierSchedule,
    CustomerInfo,
    OrderAtomicUpdate,
    OrderAwaitingCourier,
    OrderFieldsUpdate,
    OrderFilter,
    OrderFlat,
    OrderLineBatchCreate,
    OrderLineFlat,
    OrderLineUpdate,
    ProductInfo,
    StoreCourierMetrics,
    StoreInfo,
    StoreInventory,
    TaskReadyToAdvance,
)
from src.freshmart.order_line_service import OrderLineService
from src.freshmart.service import FreshMartService
from src.triples.service import TripleValidationError

router = APIRouter(prefix="/freshmart", tags=["FreshMart Operations"])


async def set_propagation_focus(
    order_id: str,
    store_id: str,
    product_ids: list[str],
) -> None:
    """Set focus context for propagation event prioritization.

    This tells the propagation system to prioritize events related to this order,
    so that inventory updates for products in the order appear first in the UI.

    Args:
        order_id: The order being updated
        store_id: The store the order belongs to
        product_ids: Product IDs in the order's line items
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                f"{PROPAGATION_API_URL}/propagation/focus",
                json={
                    "order_id": order_id,
                    "store_id": store_id,
                    "product_ids": product_ids,
                },
            )
            logger.debug(f"Set propagation focus: order={order_id}, store={store_id}, products={len(product_ids)}")
    except Exception as e:
        # Non-critical - don't fail the request if propagation API is unavailable
        logger.warning(f"Failed to set propagation focus: {e}")


async def get_session() -> AsyncSession:
    """Dependency to get database session for FreshMart queries.

    Uses Materialize for reads in production (configurable via USE_MATERIALIZE_FOR_READS).
    Falls back to PostgreSQL for testing or when Materialize is unavailable.
    """
    settings = get_settings()
    use_mz = settings.use_materialize_for_reads

    if use_mz:
        factory = get_mz_session_factory()
        async with factory() as session:
            # Use the serving cluster for low-latency indexed queries
            await session.execute(text("SET CLUSTER = serving"))
            yield session
    else:
        factory = get_pg_session_factory()
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


async def get_freshmart_service(session: AsyncSession = Depends(get_session)) -> FreshMartService:
    """Dependency to get FreshMart service."""
    settings = get_settings()
    return FreshMartService(session, use_materialize=settings.use_materialize_for_reads)


async def get_pg_write_session() -> AsyncSession:
    """Dependency to get PostgreSQL session for write operations."""
    import logging
    logger = logging.getLogger(__name__)

    factory = get_pg_session_factory()
    async with factory() as session:
        logger.debug("[TRANSACTION START] PostgreSQL write transaction started")
        try:
            yield session
            await session.commit()
            logger.debug("[TRANSACTION END] PostgreSQL transaction committed successfully")
        except Exception as e:
            logger.error(f"[TRANSACTION] PostgreSQL transaction failed, rolling back: {e}")
            await session.rollback()
            raise


async def get_order_line_service(session: AsyncSession = Depends(get_pg_write_session)) -> OrderLineService:
    """Dependency to get OrderLine service."""
    return OrderLineService(session)


# =============================================================================
# Orders
# =============================================================================


@router.get("/orders", response_model=list[OrderFlat])
async def list_orders(
    status: Optional[str] = Query(default=None, description="Filter by order status"),
    store_id: Optional[str] = Query(default=None, description="Filter by store ID"),
    customer_id: Optional[str] = Query(default=None, description="Filter by customer ID"),
    window_start_before: Optional[datetime] = Query(default=None, description="Delivery window starts before"),
    window_end_after: Optional[datetime] = Query(default=None, description="Delivery window ends after"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List orders with optional filtering.

    Filters:
    - status: CREATED, PICKING, OUT_FOR_DELIVERY, DELIVERED, CANCELLED
    - store_id: Filter by fulfilling store
    - customer_id: Filter by customer
    - window_start_before: Orders with delivery window starting before this time
    - window_end_after: Orders with delivery window ending after this time
    """
    filter_ = OrderFilter(
        status=status,
        store_id=store_id,
        customer_id=customer_id,
        window_start_before=window_start_before,
        window_end_after=window_end_after,
    )
    return await service.list_orders(filter_=filter_, limit=limit, offset=offset)


@router.get("/orders/{order_id}", response_model=OrderFlat)
async def get_order(order_id: str, service: FreshMartService = Depends(get_freshmart_service)):
    """
    Get detailed order information.

    Returns enriched order data including customer, store, and delivery task information.
    """
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.put("/orders/{order_id:path}/atomic", status_code=status.HTTP_200_OK)
async def atomic_update_order(
    order_id: str,
    data: OrderAtomicUpdate,
    service: OrderLineService = Depends(get_order_line_service),
):
    """
    Atomically update an order's fields and line items in a single transaction.

    This endpoint ensures that both order field updates and line item replacements
    happen atomically - either all succeed or all fail together. This prevents
    inconsistent state where order fields are updated but line items aren't (or vice versa).

    The line_items array represents the complete desired state - all existing line items
    will be deleted and replaced with the provided items.

    Example:
    ```json
    {
      "order_status": "PICKING",
      "customer_id": "customer:CUST-001",
      "store_id": "store:BK-01",
      "delivery_window_start": "2024-01-15T14:00:00Z",
      "delivery_window_end": "2024-01-15T16:00:00Z",
      "line_items": [
        {
          "product_id": "product:PROD-001",
          "quantity": 2,
          "unit_price": 12.50,
          "line_sequence": 1,
          "perishable_flag": true
        }
      ]
    }
    ```

    Note: order_total_amount is auto-calculated by the materialized view based on line items.
    """
    try:
        await service.atomic_update_order_with_lines(
            order_id=order_id,
            order_status=data.order_status,
            customer_id=data.customer_id,
            store_id=data.store_id,
            delivery_window_start=data.delivery_window_start,
            delivery_window_end=data.delivery_window_end,
            line_items=data.line_items,
        )
        return {"success": True, "order_id": order_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.patch("/orders/{order_id:path}", status_code=status.HTTP_200_OK)
async def update_order_fields(
    order_id: str,
    data: OrderFieldsUpdate,
    service: OrderLineService = Depends(get_order_line_service),
    session: AsyncSession = Depends(get_pg_write_session),
):
    """
    Smart-patch order fields and line items.

    This endpoint only updates what changed:
    - Order fields: only upserts provided fields
    - Line items: smart patch (only updates/adds/deletes what changed)

    **No unnecessary triple writes!**

    Examples:
    ```json
    // Update just status - writes 1 triple
    {
      "order_status": "PICKING"
    }

    // Update status + line items - only writes changed triples
    {
      "order_status": "PICKING",
      "line_items": [...]
    }
    ```

    Contrast with `/atomic` which always deletes and recreates all line items.
    """
    try:
        # Query order's current store_id and product_ids for propagation focus
        # This ensures the propagation widget prioritizes events related to this order
        order_data = await session.execute(
            text("""
                SELECT
                    MAX(CASE WHEN predicate = 'order_store' THEN object_value END) AS store_id
                FROM triples
                WHERE subject_id = :order_id
            """),
            {"order_id": order_id}
        )
        order_row = order_data.fetchone()
        store_id = order_row.store_id if order_row else None

        # Get product_ids from order lines
        line_data = await session.execute(
            text("""
                SELECT DISTINCT t2.object_value AS product_id
                FROM triples t1
                JOIN triples t2 ON t2.subject_id = t1.subject_id AND t2.predicate = 'line_product'
                WHERE t1.predicate = 'line_of_order' AND t1.object_value = :order_id
            """),
            {"order_id": order_id}
        )
        product_ids = [row.product_id for row in line_data.fetchall()]

        # Set propagation focus before making changes
        if store_id and product_ids:
            await set_propagation_focus(order_id, store_id, product_ids)

        await service.update_order_fields(
            order_id=order_id,
            order_status=data.order_status,
            customer_id=data.customer_id,
            store_id=data.store_id,
            delivery_window_start=data.delivery_window_start,
            delivery_window_end=data.delivery_window_end,
            line_items=data.line_items,
        )
        return {"success": True, "order_id": order_id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


# =============================================================================
# Stores & Inventory
# =============================================================================


@router.get("/stores", response_model=list[StoreInfo])
async def list_stores(service: FreshMartService = Depends(get_freshmart_service)):
    """List all stores with basic information."""
    return await service.list_stores()


@router.get("/stores/inventory", response_model=list[StoreInventory])
async def list_inventory(
    store_id: Optional[str] = Query(default=None, description="Filter by store ID"),
    low_stock_only: bool = Query(default=False, description="Only show items with stock < 10"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List store inventory.

    Optionally filter by store or show only low-stock items.
    """
    return await service.list_store_inventory(
        store_id=store_id,
        low_stock_only=low_stock_only,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Customers
# =============================================================================


@router.get("/customers", response_model=list[CustomerInfo])
async def list_customers(service: FreshMartService = Depends(get_freshmart_service)):
    """List all customers."""
    return await service.list_customers()


# =============================================================================
# Products
# =============================================================================


@router.get("/products", response_model=list[ProductInfo])
async def list_products(service: FreshMartService = Depends(get_freshmart_service)):
    """List all products."""
    return await service.list_products()


@router.get("/products/{product_id:path}", response_model=ProductInfo)
async def get_product(product_id: str, service: FreshMartService = Depends(get_freshmart_service)):
    """Get product information by ID."""
    product = await service.get_product(product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.get("/stores/{store_id:path}", response_model=StoreInfo)
async def get_store(store_id: str, service: FreshMartService = Depends(get_freshmart_service)):
    """Get store information with inventory."""
    store = await service.get_store(store_id)
    if not store:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return store


# =============================================================================
# Couriers
# =============================================================================


@router.get("/couriers", response_model=list[CourierSchedule])
async def list_couriers(
    status: Optional[str] = Query(default=None, description="Filter by courier status"),
    store_id: Optional[str] = Query(default=None, description="Filter by home store"),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List couriers with their schedules.

    Filters:
    - status: OFF_SHIFT, AVAILABLE, ON_DELIVERY
    - store_id: Filter by home store
    """
    return await service.list_courier_schedules(
        status=status,
        store_id=store_id,
        limit=limit,
        offset=offset,
    )


@router.get("/couriers/{courier_id:path}", response_model=CourierSchedule)
async def get_courier(courier_id: str, service: FreshMartService = Depends(get_freshmart_service)):
    """Get courier information with current tasks."""
    courier = await service.get_courier(courier_id)
    if not courier:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier not found")
    return courier


# =============================================================================
# Order Line Items
# =============================================================================


@router.post("/orders/{order_id:path}/line-items/batch", response_model=list[OrderLineFlat], status_code=status.HTTP_201_CREATED)
async def create_order_line_items_batch(
    order_id: str,
    data: OrderLineBatchCreate,
    service: OrderLineService = Depends(get_order_line_service),
):
    """
    Create multiple line items for an order in a single transaction.

    Accepts an array of line items with auto-incrementing sequences.
    Validates line_sequence uniqueness and ontology compliance.

    Example:
    ```json
    {
      "line_items": [
        {
          "product_id": "product:PROD-001",
          "quantity": 2,
          "unit_price": 12.50,
          "line_sequence": 1,
          "perishable_flag": true
        },
        {
          "product_id": "product:PROD-002",
          "quantity": 1,
          "unit_price": 25.00,
          "line_sequence": 2,
          "perishable_flag": false
        }
      ]
    }
    ```
    """
    try:
        return await service.create_line_items_batch(order_id, data.line_items)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except TripleValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Triple validation failed",
                "errors": [err.model_dump() for err in e.validation_result.errors],
            },
        )


@router.get("/orders/{order_id:path}/line-items", response_model=list[OrderLineFlat])
async def list_order_line_items(
    order_id: str,
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List all line items for an order.

    Returns line items sorted by line_sequence.
    Uses Materialize for fast reads when available.
    """
    return await service.list_order_lines(order_id)


@router.get("/orders/{order_id:path}/line-items/{line_id:path}", response_model=OrderLineFlat)
async def get_order_line_item(
    order_id: str,
    line_id: str,
    service: OrderLineService = Depends(get_order_line_service),
):
    """Get a single line item by ID."""
    line_item = await service.get_line_item(line_id)
    if not line_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")
    if line_item.order_id != order_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Line item does not belong to this order")
    return line_item


@router.put("/orders/{order_id:path}/line-items/{line_id:path}", response_model=OrderLineFlat)
async def update_order_line_item(
    order_id: str,
    line_id: str,
    data: OrderLineUpdate,
    service: OrderLineService = Depends(get_order_line_service),
):
    """
    Update a line item.

    Can update quantity, unit_price, or line_sequence.
    line_amount is automatically recalculated.
    """
    try:
        updated = await service.update_line_item(line_id, data)
        if updated.order_id != order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Line item does not belong to this order",
            )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/orders/{order_id:path}/line-items/{line_id:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order_line_item(
    order_id: str,
    line_id: str,
    service: OrderLineService = Depends(get_order_line_service),
):
    """Delete a line item."""
    # Verify line item belongs to order
    line_item = await service.get_line_item(line_id)
    if not line_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")
    if line_item.order_id != order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Line item does not belong to this order",
        )

    deleted = await service.delete_line_item(line_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found")


# =============================================================================
# Courier Dispatch (CQRS Read Endpoints)
# =============================================================================


@router.get("/dispatch/couriers/available", response_model=list[CourierAvailable])
async def list_available_couriers(
    store_id: Optional[str] = Query(default=None, description="Filter by home store"),
    limit: int = Query(default=100, ge=1, le=1000),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List available couriers that can be assigned to orders.

    Returns couriers who are AVAILABLE and not currently assigned to an active task.
    Used by the courier dispatch system to find couriers for new assignments.
    """
    return await service.list_available_couriers(store_id=store_id, limit=limit)


@router.get("/dispatch/orders/awaiting-courier", response_model=list[OrderAwaitingCourier])
async def list_orders_awaiting_courier(
    store_id: Optional[str] = Query(default=None, description="Filter by store"),
    limit: int = Query(default=100, ge=1, le=1000),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List orders awaiting courier assignment.

    Returns orders in CREATED status that don't have an active delivery task.
    Orders are returned in FIFO order (oldest first).
    """
    return await service.list_orders_awaiting_courier(store_id=store_id, limit=limit)


@router.get("/dispatch/tasks/ready-to-advance", response_model=list[TaskReadyToAdvance])
async def list_tasks_ready_to_advance(
    limit: int = Query(default=100, ge=1, le=1000),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List delivery tasks where the timer has elapsed.

    Returns tasks where:
    - PICKING tasks with 5+ seconds elapsed -> ready to transition to DELIVERING
    - DELIVERING tasks with 5+ seconds elapsed -> ready to complete

    Uses mz_now() for real-time filtering in Materialize.
    """
    return await service.list_tasks_ready_to_advance(limit=limit)


@router.get("/dispatch/metrics", response_model=list[StoreCourierMetrics])
async def list_store_courier_metrics(
    store_id: Optional[str] = Query(default=None, description="Filter by store"),
    service: FreshMartService = Depends(get_freshmart_service),
):
    """
    List courier metrics per store.

    Returns operational metrics including:
    - Available/busy/off-shift courier counts
    - Orders in queue, picking, and delivering
    - Estimated wait time
    - Courier utilization percentage
    """
    return await service.list_store_courier_metrics(store_id=store_id)
