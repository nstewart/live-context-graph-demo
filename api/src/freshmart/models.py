"""FreshMart domain models for flattened views."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class OrderFlat(BaseModel):
    """Flattened order view."""

    order_id: str
    order_number: Optional[str] = None
    order_status: Optional[str] = None
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    delivery_window_start: Optional[str] = None
    delivery_window_end: Optional[str] = None
    order_total_amount: Optional[Decimal] = None
    effective_updated_at: Optional[datetime] = None

    # Enriched fields (from search source)
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
    store_name: Optional[str] = None
    store_zone: Optional[str] = None
    store_address: Optional[str] = None
    assigned_courier_id: Optional[str] = None
    delivery_task_status: Optional[str] = None
    delivery_eta: Optional[str] = None


class StoreInventory(BaseModel):
    """Store inventory view."""

    inventory_id: str
    store_id: Optional[str] = None
    product_id: Optional[str] = None
    stock_level: Optional[int] = None
    replenishment_eta: Optional[str] = None
    effective_updated_at: Optional[datetime] = None

    # Enriched fields
    store_name: Optional[str] = None
    product_name: Optional[str] = None


class CourierSchedule(BaseModel):
    """Courier schedule view."""

    courier_id: str
    courier_name: Optional[str] = None
    home_store_id: Optional[str] = None
    vehicle_type: Optional[str] = None
    courier_status: Optional[str] = None
    tasks: list[dict] = Field(default_factory=list)
    effective_updated_at: Optional[datetime] = None

    # Enriched fields
    home_store_name: Optional[str] = None


class OrderFilter(BaseModel):
    """Filter options for orders."""

    status: Optional[str] = None
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    window_start_before: Optional[datetime] = None
    window_end_after: Optional[datetime] = None


class StoreInfo(BaseModel):
    """Store information with inventory summary."""

    store_id: str
    store_name: Optional[str] = None
    store_address: Optional[str] = None
    store_zone: Optional[str] = None
    store_status: Optional[str] = None
    store_capacity_orders_per_hour: Optional[int] = None
    inventory_items: list[StoreInventory] = Field(default_factory=list)


class CourierInfo(BaseModel):
    """Courier information with tasks."""

    courier_id: str
    courier_name: Optional[str] = None
    home_store_id: Optional[str] = None
    vehicle_type: Optional[str] = None
    courier_status: Optional[str] = None
    tasks: list[dict] = Field(default_factory=list)


class CustomerInfo(BaseModel):
    """Customer information."""

    customer_id: str
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_address: Optional[str] = None
