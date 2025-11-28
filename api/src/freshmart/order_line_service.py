"""Order Line service for CRUD operations on line items."""

from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.client import get_mz_session_factory
from src.freshmart.models import OrderLineCreate, OrderLineFlat, OrderLineUpdate
from src.triples.models import TripleCreate
from src.triples.service import TripleService


class OrderLineService:
    """Service for managing order line items with transactional integrity."""

    def __init__(self, session: AsyncSession):
        """Initialize service with database session."""
        self.session = session
        self.triple_service = TripleService(session, validate=True)

    def _generate_line_id(self, order_id: str, sequence: int) -> str:
        """Generate line item ID from order ID and sequence.

        Args:
            order_id: Order ID (e.g., 'order:FM-1001')
            sequence: Line sequence number (1, 2, 3, ...)

        Returns:
            Line ID in format 'orderline:FM-1001-001'
        """
        order_number = order_id.split(":")[1]
        return f"orderline:{order_number}-{sequence:03d}"

    async def _fetch_live_prices(
        self, store_id: str, product_ids: list[str]
    ) -> dict[str, Decimal]:
        """Fetch live prices from Materialize inventory_items_with_dynamic_pricing view.

        Args:
            store_id: Store ID to query inventory for
            product_ids: List of product IDs to fetch prices for

        Returns:
            Dictionary mapping product_id to live_price
        """
        live_prices = {}

        if not product_ids:
            return live_prices

        try:
            # Query Materialize for live prices (not PostgreSQL)
            mz_factory = get_mz_session_factory()
            async with mz_factory() as mz_session:
                # Use serving cluster for low-latency indexed queries
                await mz_session.execute(text("SET CLUSTER = serving"))

                # Build query with IN clause (Materialize doesn't support ANY with parameters)
                # Build placeholders for IN clause
                placeholders = ', '.join(f':product_id_{i}' for i in range(len(product_ids)))
                query = f"""
                    SELECT product_id, live_price
                    FROM inventory_items_with_dynamic_pricing
                    WHERE store_id = :store_id
                    AND product_id IN ({placeholders})
                """

                # Build parameters dict
                params = {"store_id": store_id}
                for i, product_id in enumerate(product_ids):
                    params[f"product_id_{i}"] = product_id

                result = await mz_session.execute(text(query), params)
                rows = result.fetchall()

                # Build dictionary of live prices
                for row in rows:
                    if row.product_id and row.live_price is not None:
                        live_prices[row.product_id] = Decimal(str(row.live_price))

        except Exception as e:
            # Log error but don't fail - will use provided unit_price as fallback
            print(f"Warning: Failed to fetch live prices from Materialize: {e}")

        return live_prices

    def _create_line_item_triples(
        self, order_id: str, sequence: int, line_item: OrderLineCreate
    ) -> list[TripleCreate]:
        """Generate triple records for a line item.

        Args:
            order_id: Parent order ID
            sequence: Line sequence number
            line_item: Line item data

        Returns:
            List of TripleCreate objects
        """
        line_id = self._generate_line_id(order_id, sequence)
        line_amount = line_item.quantity * line_item.unit_price

        return [
            TripleCreate(
                subject_id=line_id,
                predicate="line_of_order",
                object_value=order_id,
                object_type="entity_ref",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="line_product",
                object_value=line_item.product_id,
                object_type="entity_ref",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="quantity",
                object_value=str(line_item.quantity),
                object_type="int",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="order_line_unit_price",
                object_value=str(line_item.unit_price),
                object_type="float",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="line_amount",
                object_value=str(line_amount),
                object_type="float",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="line_sequence",
                object_value=str(sequence),
                object_type="int",
            ),
            TripleCreate(
                subject_id=line_id,
                predicate="perishable_flag",
                object_value=str(line_item.perishable_flag).lower(),
                object_type="bool",
            ),
        ]

    async def create_line_items_batch(
        self, order_id: str, line_items: list[OrderLineCreate]
    ) -> list[OrderLineFlat]:
        """Create multiple line items for an order in a single transaction.

        Args:
            order_id: Parent order ID
            line_items: List of line items to create

        Returns:
            List of created line items

        Raises:
            ValueError: If line_sequence values are not unique
            TripleValidationError: If triples fail ontology validation
        """
        # Validate unique sequences
        sequences = [item.line_sequence for item in line_items]
        if len(sequences) != len(set(sequences)):
            raise ValueError("line_sequence values must be unique within an order")

        # Sort by sequence for consistent ordering
        sorted_items = sorted(line_items, key=lambda x: x.line_sequence)

        # Fetch store_id from order
        order_query = """
            SELECT MAX(CASE WHEN predicate = 'order_store' THEN object_value END) AS store_id
            FROM triples
            WHERE subject_id = :order_id
        """
        result = await self.session.execute(text(order_query), {"order_id": order_id})
        row = result.fetchone()
        store_id = row.store_id if row else None

        if not store_id:
            raise ValueError(f"Could not find store_id for order {order_id}")

        # Fetch live prices from inventory
        product_ids = [item.product_id for item in sorted_items]
        live_prices = await self._fetch_live_prices(store_id, product_ids)

        # Update line items with live prices from inventory
        for item in sorted_items:
            if item.product_id in live_prices:
                item.unit_price = live_prices[item.product_id]

        # Generate all triples
        all_triples = []
        for item in sorted_items:
            triples = self._create_line_item_triples(order_id, item.line_sequence, item)
            all_triples.extend(triples)

        # Create all triples in batch (validates and inserts in single transaction)
        await self.triple_service.create_triples_batch(all_triples)

        # Return created line items
        return await self.list_order_lines(order_id)

    async def list_order_lines(self, order_id: str) -> list[OrderLineFlat]:
        """List all line items for an order.

        Args:
            order_id: Parent order ID

        Returns:
            List of line items sorted by sequence
        """
        # Query triples directly with product enrichment (for PostgreSQL)
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

        result = await self.session.execute(text(query), {"pattern": pattern, "order_id": order_id})
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

    async def get_line_item(self, line_id: str) -> Optional[OrderLineFlat]:
        """Get a single line item by ID.

        Args:
            line_id: Line item ID

        Returns:
            Line item or None if not found
        """
        query = """
            SELECT
                subject_id AS line_id,
                MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
                MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
                MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
                MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
                MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL(10,2) AS line_amount,
                MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence,
                MAX(CASE WHEN predicate = 'perishable_flag' THEN object_value END)::BOOLEAN AS perishable_flag,
                MAX(updated_at) AS effective_updated_at
            FROM triples
            WHERE subject_id = :line_id
            GROUP BY subject_id
        """

        result = await self.session.execute(text(query), {"line_id": line_id})
        row = result.fetchone()

        if not row:
            return None

        return OrderLineFlat(
            line_id=row.line_id,
            order_id=row.order_id,
            product_id=row.product_id,
            quantity=row.quantity,
            unit_price=row.unit_price,
            line_amount=row.line_amount,
            line_sequence=row.line_sequence,
            perishable_flag=row.perishable_flag,
            effective_updated_at=row.effective_updated_at,
        )

    async def update_line_item(
        self, line_id: str, updates: OrderLineUpdate
    ) -> Optional[OrderLineFlat]:
        """Update a line item.

        Args:
            line_id: Line item ID
            updates: Fields to update

        Returns:
            Updated line item or None if not found

        Raises:
            ValueError: If line item not found
        """
        # Get current line item
        current = await self.get_line_item(line_id)
        if not current:
            raise ValueError(f"Line item {line_id} not found")

        # Apply updates
        new_quantity = updates.quantity if updates.quantity is not None else current.quantity
        new_unit_price = (
            updates.unit_price if updates.unit_price is not None else current.unit_price
        )
        new_sequence = (
            updates.line_sequence if updates.line_sequence is not None else current.line_sequence
        )

        # Calculate line amount - handle case where unit_price might be None
        if new_unit_price is not None:
            new_line_amount = new_quantity * new_unit_price
        elif current.line_amount is not None and current.quantity:
            # Calculate unit price from existing line amount
            new_unit_price = current.line_amount / current.quantity
            new_line_amount = new_quantity * new_unit_price
        else:
            # Fallback - keep existing line amount or set to 0
            new_line_amount = current.line_amount or 0

        # Update triples
        if updates.quantity is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'quantity'
                """),
                {"line_id": line_id, "value": str(new_quantity)},
            )

        if updates.unit_price is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'order_line_unit_price'
                """),
                {"line_id": line_id, "value": str(new_unit_price)},
            )

        if updates.line_sequence is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'line_sequence'
                """),
                {"line_id": line_id, "value": str(new_sequence)},
            )

        # Always update line_amount if quantity or unit_price changed
        if updates.quantity is not None or updates.unit_price is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'line_amount'
                """),
                {"line_id": line_id, "value": str(new_line_amount)},
            )

        # Return updated item
        return await self.get_line_item(line_id)

    async def delete_line_item(self, line_id: str) -> bool:
        """Delete a line item.

        Args:
            line_id: Line item ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.session.execute(
            text("DELETE FROM triples WHERE subject_id = :line_id"),
            {"line_id": line_id},
        )
        return result.rowcount > 0

    async def delete_order_lines(self, order_id: str) -> int:
        """Delete all line items for an order (cascade delete).

        Args:
            order_id: Parent order ID

        Returns:
            Number of line items deleted
        """
        order_number = order_id.split(":")[1]
        pattern = f"orderline:{order_number}-%"

        result = await self.session.execute(
            text("DELETE FROM triples WHERE subject_id LIKE :pattern"),
            {"pattern": pattern},
        )
        # Each line item has 7 triples, so divide by 7
        return result.rowcount // 7
