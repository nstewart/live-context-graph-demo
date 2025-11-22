"""FreshMart API routes for operational data."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.client import get_pg_session_factory
from src.freshmart.models import (
    CourierSchedule,
    OrderFilter,
    OrderFlat,
    StoreInfo,
    StoreInventory,
)
from src.freshmart.service import FreshMartService

router = APIRouter(prefix="/freshmart", tags=["FreshMart Operations"])


async def get_session() -> AsyncSession:
    """Dependency to get database session."""
    factory = get_pg_session_factory()
    async with factory() as session:
        yield session


async def get_freshmart_service(session: AsyncSession = Depends(get_session)) -> FreshMartService:
    """Dependency to get FreshMart service."""
    return FreshMartService(session)


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


@router.get("/orders/{order_id:path}", response_model=OrderFlat)
async def get_order(order_id: str, service: FreshMartService = Depends(get_freshmart_service)):
    """
    Get detailed order information.

    Returns enriched order data including customer, store, and delivery task information.
    """
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


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
