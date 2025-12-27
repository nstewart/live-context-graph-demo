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

    # Enriched fields from products
    store_name: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    perishable: Optional[bool] = None


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


class ProductInfo(BaseModel):
    """Product information."""

    product_id: str
    product_name: Optional[str] = None
    category: Optional[str] = None
    unit_price: Optional[Decimal] = None
    perishable: Optional[bool] = None


class OrderLineFlat(BaseModel):
    """Flattened order line item view."""

    line_id: str
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    quantity: Optional[int] = None
    unit_price: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    line_sequence: Optional[int] = None
    perishable_flag: Optional[bool] = None
    effective_updated_at: Optional[datetime] = None

    # Enriched fields from product
    product_name: Optional[str] = None
    category: Optional[str] = None


class OrderLineCreate(BaseModel):
    """Request model for creating an order line item."""

    line_id: Optional[str] = Field(None, description="Optional line ID (UUID-based). If not provided, will be auto-generated.")
    product_id: str = Field(..., description="Product ID (e.g., product:PROD-001)")
    quantity: int = Field(..., gt=0, description="Quantity ordered")
    unit_price: Decimal = Field(..., gt=0, description="Unit price at order time")
    line_sequence: Optional[int] = Field(None, gt=0, description="Optional display sequence within order")
    # Note: perishable_flag is NOT stored on order lines - it is derived from the product's perishable attribute


class OrderLineUpdate(BaseModel):
    """Request model for updating an order line item."""

    quantity: Optional[int] = Field(None, gt=0, description="New quantity")
    unit_price: Optional[Decimal] = Field(None, gt=0, description="New unit price")
    line_sequence: Optional[int] = Field(None, gt=0, description="New sequence")


class OrderLineBatchCreate(BaseModel):
    """Request model for batch creating order line items."""

    line_items: list[OrderLineCreate] = Field(..., min_length=1, max_length=100, description="Line items to create")


class OrderWithLinesFlat(OrderFlat):
    """Order with aggregated line items."""

    line_items: list[dict] = Field(default_factory=list, description="Line items as JSONB array")
    line_item_count: Optional[int] = Field(None, description="Number of line items")
    computed_total: Optional[Decimal] = Field(None, description="Computed total from line items")
    has_perishable_items: Optional[bool] = Field(None, description="Whether order contains perishable items")
    total_weight_kg: Optional[Decimal] = Field(None, description="Total weight in kg")


class OrderFieldsUpdate(BaseModel):
    """Partial update for order fields and optional smart line item patching."""

    order_status: Optional[str] = Field(None, description="Order status")
    customer_id: Optional[str] = Field(None, description="Customer ID")
    store_id: Optional[str] = Field(None, description="Store ID")
    delivery_window_start: Optional[str] = Field(None, description="Delivery window start (ISO 8601)")
    delivery_window_end: Optional[str] = Field(None, description="Delivery window end (ISO 8601)")
    line_items: Optional[list[OrderLineCreate]] = Field(
        None,
        description="Line items to smart-patch (only updates/adds/deletes what changed)",
    )


class OrderAtomicUpdate(BaseModel):
    """Atomic update for order fields and line items in a single transaction."""

    # Order fields
    order_status: Optional[str] = Field(None, description="Order status")
    customer_id: Optional[str] = Field(None, description="Customer ID")
    store_id: Optional[str] = Field(None, description="Store ID")
    delivery_window_start: Optional[str] = Field(None, description="Delivery window start (ISO 8601)")
    delivery_window_end: Optional[str] = Field(None, description="Delivery window end (ISO 8601)")

    # Line items - the complete desired state
    line_items: list[OrderLineCreate] = Field(
        default_factory=list,
        description="Complete list of desired line items (replaces all existing)",
    )


# =============================================================================
# Courier Dispatch Models (CQRS Views)
# =============================================================================


class CourierAvailable(BaseModel):
    """Available courier from couriers_available view."""

    courier_id: str
    courier_name: Optional[str] = None
    home_store_id: Optional[str] = None
    vehicle_type: Optional[str] = None
    courier_status: Optional[str] = None
    effective_updated_at: Optional[datetime] = None


class OrderAwaitingCourier(BaseModel):
    """Order awaiting courier assignment from orders_awaiting_courier view."""

    order_id: str
    order_number: Optional[str] = None
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    order_total_amount: Optional[Decimal] = None
    delivery_window_start: Optional[str] = None
    delivery_window_end: Optional[str] = None
    created_at: Optional[datetime] = None


class TaskReadyToAdvance(BaseModel):
    """Delivery task ready to advance from tasks_ready_to_advance view."""

    task_id: str
    order_id: Optional[str] = None
    courier_id: Optional[str] = None
    task_status: Optional[str] = None
    task_started_at: Optional[datetime] = None
    store_id: Optional[str] = None
    expected_completion_at: Optional[datetime] = None


class StoreCourierMetrics(BaseModel):
    """Store courier metrics from store_courier_metrics_mv view."""

    store_id: str
    store_name: Optional[str] = None
    store_zone: Optional[str] = None
    total_couriers: int = 0
    available_couriers: int = 0
    busy_couriers: int = 0
    off_shift_couriers: int = 0
    orders_in_queue: int = 0
    orders_picking: int = 0
    orders_delivering: int = 0
    estimated_wait_minutes: Optional[float] = None
    courier_utilization_pct: Optional[float] = None
    effective_updated_at: Optional[datetime] = None
