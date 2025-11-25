"""FreshMart service for operational queries."""

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.freshmart.models import (
    CourierSchedule,
    OrderFilter,
    OrderFlat,
    StoreInfo,
    StoreInventory,
)


class FreshMartService:
    """Service for FreshMart operational queries using flattened views."""

    def __init__(self, session: AsyncSession, use_materialize: bool = False):
        """
        Initialize service.

        Args:
            session: Database session (can be PG or MZ)
            use_materialize: If True, queries Materialize views. If False, uses PG views.
        """
        self.session = session
        self.use_materialize = use_materialize

    def _view_suffix(self) -> str:
        """Get view suffix based on database."""
        return "_mz" if self.use_materialize else ""

    def _get_view(self, base_name: str) -> str:
        """Get the correct view name for the current database.

        Materialize uses _mv suffix for materialized views.
        PostgreSQL uses the base view name.
        """
        mz_views = {
            "orders_search_source": "orders_search_source_mv",
            "store_inventory_flat": "store_inventory_mv",
            "courier_schedule_flat": "courier_schedule_mv",
            "stores_flat": "stores_mv",
            "customers_flat": "customers_mv",
            "products_flat": "products_mv",
        }
        if self.use_materialize:
            return mz_views.get(base_name, base_name)
        return base_name

    # =========================================================================
    # Orders
    # =========================================================================

    async def list_orders(
        self,
        filter_: Optional[OrderFilter] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OrderFlat]:
        """List orders with optional filtering."""
        view = self._get_view("orders_search_source")

        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if filter_:
            if filter_.status:
                conditions.append("order_status = :status")
                params["status"] = filter_.status
            if filter_.store_id:
                conditions.append("store_id = :store_id")
                params["store_id"] = filter_.store_id
            if filter_.customer_id:
                conditions.append("customer_id = :customer_id")
                params["customer_id"] = filter_.customer_id
            if filter_.window_start_before:
                conditions.append("delivery_window_start::timestamptz < :window_start_before")
                params["window_start_before"] = filter_.window_start_before
            if filter_.window_end_after:
                conditions.append("delivery_window_end::timestamptz > :window_end_after")
                params["window_end_after"] = filter_.window_end_after

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT order_id, order_number, order_status, store_id, customer_id,
                   delivery_window_start, delivery_window_end, order_total_amount,
                   customer_name, store_name,
                   effective_updated_at
            FROM {view}
            {where_clause}
            ORDER BY effective_updated_at DESC
            LIMIT :limit OFFSET :offset
        """

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        return [
            OrderFlat(
                order_id=row.order_id,
                order_number=row.order_number,
                order_status=row.order_status,
                store_id=row.store_id,
                customer_id=row.customer_id,
                delivery_window_start=row.delivery_window_start,
                delivery_window_end=row.delivery_window_end,
                order_total_amount=row.order_total_amount,
                customer_name=row.customer_name,
                store_name=row.store_name,
                effective_updated_at=row.effective_updated_at,
            )
            for row in rows
        ]

    async def get_order(self, order_id: str) -> Optional[OrderFlat]:
        """Get detailed order information."""
        # Use the search source view for enriched data
        view = self._get_view("orders_search_source")

        result = await self.session.execute(
            text(f"""
                SELECT order_id, order_number, order_status, store_id, customer_id,
                       delivery_window_start, delivery_window_end, order_total_amount,
                       customer_name, customer_email, customer_address,
                       store_name, store_zone, store_address,
                       assigned_courier_id, delivery_task_status, delivery_eta,
                       effective_updated_at
                FROM {view}
                WHERE order_id = :order_id
            """),
            {"order_id": order_id},
        )
        row = result.fetchone()

        if not row:
            return None

        return OrderFlat(
            order_id=row.order_id,
            order_number=row.order_number,
            order_status=row.order_status,
            store_id=row.store_id,
            customer_id=row.customer_id,
            delivery_window_start=row.delivery_window_start,
            delivery_window_end=row.delivery_window_end,
            order_total_amount=row.order_total_amount,
            customer_name=row.customer_name,
            customer_email=row.customer_email,
            customer_address=row.customer_address,
            store_name=row.store_name,
            store_zone=row.store_zone,
            store_address=row.store_address,
            assigned_courier_id=row.assigned_courier_id,
            delivery_task_status=row.delivery_task_status,
            delivery_eta=row.delivery_eta,
            effective_updated_at=row.effective_updated_at,
        )

    # =========================================================================
    # Inventory
    # =========================================================================

    async def list_store_inventory(
        self,
        store_id: Optional[str] = None,
        low_stock_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StoreInventory]:
        """List store inventory, optionally filtered by store."""
        view = self._get_view("store_inventory_flat")

        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if store_id:
            conditions.append("i.store_id = :store_id")
            params["store_id"] = store_id
        if low_stock_only:
            conditions.append("i.stock_level < 10")

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        # Join with products_mv to get product details
        products_view = self._get_view("products_flat")
        query = f"""
            SELECT i.inventory_id, i.store_id, i.product_id, i.stock_level,
                   i.replenishment_eta, i.effective_updated_at,
                   p.product_name, p.category, p.perishable
            FROM {view} i
            LEFT JOIN {products_view} p ON i.product_id = p.product_id
            {where_clause}
            ORDER BY i.store_id, i.product_id
            LIMIT :limit OFFSET :offset
        """

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        return [
            StoreInventory(
                inventory_id=row.inventory_id,
                store_id=row.store_id,
                product_id=row.product_id,
                stock_level=row.stock_level,
                replenishment_eta=row.replenishment_eta,
                effective_updated_at=row.effective_updated_at,
                product_name=row.product_name,
                category=row.category,
                perishable=row.perishable,
            )
            for row in rows
        ]

    async def get_store(self, store_id: str) -> Optional[StoreInfo]:
        """Get store information with inventory."""
        view = self._get_view("stores_flat")

        result = await self.session.execute(
            text(f"""
                SELECT store_id, store_name, store_address, store_zone,
                       store_status, store_capacity_orders_per_hour
                FROM {view}
                WHERE store_id = :store_id
            """),
            {"store_id": store_id},
        )
        row = result.fetchone()

        if not row:
            return None

        # Get inventory
        inventory = await self.list_store_inventory(store_id=store_id, limit=1000)

        return StoreInfo(
            store_id=row.store_id,
            store_name=row.store_name,
            store_address=row.store_address,
            store_zone=row.store_zone,
            store_status=row.store_status,
            store_capacity_orders_per_hour=row.store_capacity_orders_per_hour,
            inventory_items=inventory,
        )

    async def list_stores(self) -> list[StoreInfo]:
        """List all stores with their inventory."""
        view = self._get_view("stores_flat")

        result = await self.session.execute(
            text(f"""
                SELECT store_id, store_name, store_address, store_zone,
                       store_status, store_capacity_orders_per_hour
                FROM {view}
                ORDER BY store_name
            """)
        )
        rows = result.fetchall()

        # Fetch all inventory at once and group by store_id
        all_inventory = await self.list_store_inventory(limit=10000)
        inventory_by_store: dict[str, list[StoreInventory]] = {}
        for inv in all_inventory:
            if inv.store_id:
                if inv.store_id not in inventory_by_store:
                    inventory_by_store[inv.store_id] = []
                inventory_by_store[inv.store_id].append(inv)

        return [
            StoreInfo(
                store_id=row.store_id,
                store_name=row.store_name,
                store_address=row.store_address,
                store_zone=row.store_zone,
                store_status=row.store_status,
                store_capacity_orders_per_hour=row.store_capacity_orders_per_hour,
                inventory_items=inventory_by_store.get(row.store_id, []),
            )
            for row in rows
        ]

    # =========================================================================
    # Customers
    # =========================================================================

    async def list_customers(self) -> list["CustomerInfo"]:
        """List all customers using materialized view."""
        from src.freshmart.models import CustomerInfo

        view = self._get_view("customers_flat")

        result = await self.session.execute(
            text(f"""
                SELECT customer_id, customer_name, customer_email, customer_address
                FROM {view}
                ORDER BY customer_name
            """)
        )
        rows = result.fetchall()

        return [
            CustomerInfo(
                customer_id=row.customer_id,
                customer_name=row.customer_name,
                customer_email=row.customer_email,
                customer_address=row.customer_address,
            )
            for row in rows
        ]

    # =========================================================================
    # Order Line Items (Read Operations)
    # =========================================================================

    async def list_order_lines(self, order_id: str) -> list["OrderLineFlat"]:
        """List all line items for an order using materialized view.

        Args:
            order_id: Parent order ID

        Returns:
            List of line items sorted by sequence
        """
        from src.freshmart.models import OrderLineFlat

        # Use order_lines_flat_mv when reading from Materialize
        # Fall back to direct triple query when reading from PostgreSQL
        if self.use_materialize:
            query = """
                SELECT
                    line_id,
                    order_id,
                    product_id,
                    quantity,
                    unit_price,
                    line_amount,
                    line_sequence,
                    perishable_flag,
                    product_name,
                    category,
                    effective_updated_at
                FROM order_lines_flat_mv
                WHERE order_id = :order_id
                ORDER BY line_sequence
            """
        else:
            # PostgreSQL fallback - query triples directly
            order_number = order_id.split(":")[1]
            pattern = f"orderline:{order_number}-%"
            query = """
                WITH line_items AS (
                    SELECT DISTINCT subject_id AS line_id
                    FROM triples
                    WHERE subject_id LIKE :pattern
                ),
                line_data AS (
                    SELECT
                        li.line_id,
                        MAX(CASE WHEN t.predicate = 'line_of_order' THEN t.object_value END) AS order_id,
                        MAX(CASE WHEN t.predicate = 'line_product' THEN t.object_value END) AS product_id,
                        MAX(CASE WHEN t.predicate = 'quantity' THEN t.object_value END)::INT AS quantity,
                        MAX(CASE WHEN t.predicate = 'order_line_unit_price' THEN t.object_value END)::DECIMAL(10,2) AS unit_price,
                        MAX(CASE WHEN t.predicate = 'line_amount' THEN t.object_value END)::DECIMAL(10,2) AS line_amount,
                        MAX(CASE WHEN t.predicate = 'line_sequence' THEN t.object_value END)::INT AS line_sequence,
                        MAX(CASE WHEN t.predicate = 'perishable_flag' THEN t.object_value END)::BOOLEAN AS perishable_flag,
                        MAX(t.updated_at) AS effective_updated_at
                    FROM line_items li
                    LEFT JOIN triples t ON t.subject_id = li.line_id
                    GROUP BY li.line_id
                ),
                products AS (
                    SELECT
                        subject_id AS product_id,
                        MAX(CASE WHEN predicate = 'product_name' THEN object_value END) AS product_name,
                        MAX(CASE WHEN predicate = 'category' THEN object_value END) AS category
                    FROM triples
                    WHERE subject_id LIKE 'product:%'
                    GROUP BY subject_id
                )
                SELECT ld.*, p.product_name, p.category
                FROM line_data ld
                LEFT JOIN products p ON p.product_id = ld.product_id
                WHERE ld.order_id = :order_id
                ORDER BY ld.line_sequence
            """

        params = {"order_id": order_id}
        if not self.use_materialize:
            order_number = order_id.split(":")[1]
            params["pattern"] = f"orderline:{order_number}-%"

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        return [
            OrderLineFlat(
                line_id=row.line_id,
                order_id=row.order_id,
                product_id=row.product_id,
                quantity=row.quantity,
                unit_price=row.unit_price,
                line_amount=row.line_amount,
                line_sequence=row.line_sequence,
                perishable_flag=row.perishable_flag,
                product_name=row.product_name,
                category=row.category,
                effective_updated_at=row.effective_updated_at,
            )
            for row in rows
        ]

    # =========================================================================
    # Products
    # =========================================================================

    async def list_products(self) -> list["ProductInfo"]:
        """List all products using materialized view."""
        from src.freshmart.models import ProductInfo

        view = self._get_view("products_flat")

        result = await self.session.execute(
            text(f"""
                SELECT product_id, product_name, category, unit_price, perishable
                FROM {view}
                ORDER BY product_name
            """)
        )
        rows = result.fetchall()

        return [
            ProductInfo(
                product_id=row.product_id,
                product_name=row.product_name,
                category=row.category,
                unit_price=row.unit_price,
                perishable=row.perishable,
            )
            for row in rows
        ]

    # =========================================================================
    # Couriers
    # =========================================================================

    async def list_courier_schedules(
        self,
        status: Optional[str] = None,
        store_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CourierSchedule]:
        """List courier schedules."""
        view = self._get_view("courier_schedule_flat")

        conditions = []
        params: dict = {"limit": limit, "offset": offset}

        if status:
            conditions.append("courier_status = :status")
            params["status"] = status
        if store_id:
            conditions.append("home_store_id = :store_id")
            params["store_id"] = store_id

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            SELECT courier_id, courier_name, home_store_id, vehicle_type,
                   courier_status, tasks, effective_updated_at
            FROM {view}
            {where_clause}
            ORDER BY courier_name
            LIMIT :limit OFFSET :offset
        """

        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        schedules = []
        for row in rows:
            # Parse tasks JSON
            tasks = row.tasks if isinstance(row.tasks, list) else json.loads(row.tasks) if row.tasks else []

            schedules.append(
                CourierSchedule(
                    courier_id=row.courier_id,
                    courier_name=row.courier_name,
                    home_store_id=row.home_store_id,
                    vehicle_type=row.vehicle_type,
                    courier_status=row.courier_status,
                    tasks=tasks,
                    effective_updated_at=row.effective_updated_at,
                )
            )

        return schedules

    async def get_courier(self, courier_id: str) -> Optional[CourierSchedule]:
        """Get courier with schedule."""
        view = self._get_view("courier_schedule_flat")

        result = await self.session.execute(
            text(f"""
                SELECT courier_id, courier_name, home_store_id, vehicle_type,
                       courier_status, tasks, effective_updated_at
                FROM {view}
                WHERE courier_id = :courier_id
            """),
            {"courier_id": courier_id},
        )
        row = result.fetchone()

        if not row:
            return None

        tasks = row.tasks if isinstance(row.tasks, list) else json.loads(row.tasks) if row.tasks else []

        return CourierSchedule(
            courier_id=row.courier_id,
            courier_name=row.courier_name,
            home_store_id=row.home_store_id,
            vehicle_type=row.vehicle_type,
            courier_status=row.courier_status,
            tasks=tasks,
            effective_updated_at=row.effective_updated_at,
        )
