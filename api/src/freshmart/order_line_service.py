"""Order Line service for CRUD operations on line items."""

import logging
import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.client import get_mz_session_factory
from src.freshmart.models import OrderLineCreate, OrderLineFlat, OrderLineUpdate
from src.triples.models import TripleCreate
from src.triples.service import TripleService

logger = logging.getLogger(__name__)


class OrderLineService:
    """Service for managing order line items with transactional integrity."""

    def __init__(self, session: AsyncSession):
        """Initialize service with database session."""
        self.session = session
        self.triple_service = TripleService(session, validate=True)

    def _generate_line_id(self) -> str:
        """Generate a unique UUID-based line item ID.

        Returns:
            Line ID in format 'orderline:<uuid>'
        """
        line_uuid = str(uuid.uuid4())
        return f"orderline:{line_uuid}"

    def _normalize_decimal(self, value) -> Optional[str]:
        """Normalize a numeric value to a consistent string representation.

        Args:
            value: Numeric value (int, float, Decimal, or string)

        Returns:
            Normalized string representation or None if value is None
        """
        if value is None:
            return None
        return str(Decimal(str(value)))

    async def _fetch_live_prices(
        self, store_id: str, product_ids: list[str]
    ) -> dict[str, Decimal]:
        """Fetch live prices from Materialize inventory_items_with_dynamic_pricing view.

        Args:
            store_id: Store ID to query inventory for
            product_ids: List of product IDs to fetch prices for (max 100)

        Returns:
            Dictionary mapping product_id to live_price

        Raises:
            ValueError: If product_ids list exceeds 100 items (DoS protection)
        """
        live_prices = {}

        if not product_ids:
            return live_prices

        # DoS protection: limit IN clause size to prevent excessive query complexity
        if len(product_ids) > 100:
            raise ValueError(
                f"Cannot fetch prices for {len(product_ids)} products. "
                f"Maximum allowed is 100 products per request."
            )

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
            logger.warning(
                "Failed to fetch live prices from Materialize",
                extra={
                    "store_id": store_id,
                    "product_count": len(product_ids),
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

        return live_prices

    def _create_line_item_triples(
        self, line_id: str, order_id: str, line_item: OrderLineCreate
    ) -> list[TripleCreate]:
        """Generate triple records for a line item.

        Args:
            line_id: Line item ID (UUID-based)
            order_id: Parent order ID
            line_item: Line item data

        Returns:
            List of TripleCreate objects
        """
        # Note: line_amount is derived in Materialize views as quantity * unit_price
        triples = [
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
                predicate="perishable_flag",
                object_value=str(line_item.perishable_flag).lower(),
                object_type="bool",
            ),
        ]

        # Add line_sequence triple only if provided
        if line_item.line_sequence is not None:
            triples.append(
                TripleCreate(
                    subject_id=line_id,
                    predicate="line_sequence",
                    object_value=str(line_item.line_sequence),
                    object_type="int",
                )
            )

        return triples

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
            ValueError: If line_sequence values are not unique (when provided)
            TripleValidationError: If triples fail ontology validation
        """
        # Validate unique sequences if provided
        sequences = [item.line_sequence for item in line_items if item.line_sequence is not None]
        if sequences and len(sequences) != len(set(sequences)):
            raise ValueError("line_sequence values must be unique within an order")

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
        product_ids = [item.product_id for item in line_items]
        live_prices = await self._fetch_live_prices(store_id, product_ids)

        # Update line items with live prices from inventory
        for item in line_items:
            if item.product_id in live_prices:
                item.unit_price = live_prices[item.product_id]

        # Generate all triples with UUID-based line IDs
        all_triples = []
        created_line_ids = []
        for item in line_items:
            # Use provided line_id or generate new UUID-based one
            line_id = item.line_id if item.line_id else self._generate_line_id()
            created_line_ids.append(line_id)
            triples = self._create_line_item_triples(line_id, order_id, item)
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
        # Query by line_of_order relationship to support both sequential and UUID-based line IDs
        query = """
            WITH line_items AS (
                SELECT DISTINCT subject_id AS line_id
                FROM triples
                WHERE predicate = 'line_of_order' AND object_value = :order_id
            ),
            line_data AS (
                SELECT
                    li.line_id,
                    MAX(CASE WHEN t.predicate = 'line_of_order' THEN t.object_value END) AS order_id,
                    MAX(CASE WHEN t.predicate = 'line_product' THEN t.object_value END) AS product_id,
                    MAX(CASE WHEN t.predicate = 'quantity' THEN t.object_value END)::INT AS quantity,
                    MAX(CASE WHEN t.predicate = 'order_line_unit_price' THEN t.object_value END)::DECIMAL(10,2) AS unit_price,
                    -- line_amount is derived from quantity * unit_price (not stored as triple)
                    (MAX(CASE WHEN t.predicate = 'quantity' THEN t.object_value END)::INT
                     * MAX(CASE WHEN t.predicate = 'order_line_unit_price' THEN t.object_value END)::DECIMAL(10,2))::DECIMAL(10,2) AS line_amount,
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
            ORDER BY ld.line_sequence NULLS LAST, ld.line_id
        """

        result = await self.session.execute(text(query), {"order_id": order_id})
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
                -- line_amount is derived from quantity * unit_price (not stored as triple)
                (MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT
                 * MAX(CASE WHEN predicate = 'order_line_unit_price' THEN object_value END)::DECIMAL(10,2))::DECIMAL(10,2) AS line_amount,
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

        # Track what's being updated for logging
        changes = []
        triples_written = 0
        if updates.quantity is not None and updates.quantity != current.quantity:
            changes.append(f"quantity: {current.quantity} → {updates.quantity}")
        if updates.unit_price is not None and updates.unit_price != current.unit_price:
            changes.append(f"unit_price: {current.unit_price} → {updates.unit_price}")
        if updates.line_sequence is not None and updates.line_sequence != current.line_sequence:
            changes.append(f"line_sequence: {current.line_sequence} → {updates.line_sequence}")

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
            triples_written += 1

        if updates.unit_price is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'order_line_unit_price'
                """),
                {"line_id": line_id, "value": str(new_unit_price)},
            )
            triples_written += 1

        if updates.line_sequence is not None:
            await self.session.execute(
                text("""
                    UPDATE triples
                    SET object_value = :value, updated_at = NOW()
                    WHERE subject_id = :line_id AND predicate = 'line_sequence'
                """),
                {"line_id": line_id, "value": str(new_sequence)},
            )
            triples_written += 1

        # Note: line_amount is derived in Materialize views, so we calculate it here for logging only
        if updates.quantity is not None or updates.unit_price is not None:
            if current.line_amount != new_line_amount:
                changes.append(f"line_amount: {current.line_amount} → {new_line_amount} (derived)")

        # Log summary of changes
        if changes:
            logger.info(f"📝 [LINE ITEM UPDATE] {line_id} ({triples_written} triples): {', '.join(changes)}")

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
        # First, get the list of line item IDs to delete
        line_ids_result = await self.session.execute(
            text("""
                SELECT DISTINCT subject_id
                FROM triples
                WHERE predicate = 'line_of_order' AND object_value = :order_id
            """),
            {"order_id": order_id},
        )
        line_ids = [row.subject_id for row in line_ids_result.fetchall()]

        if not line_ids:
            return 0

        # Delete all triples for these line items
        # Build IN clause with placeholders
        placeholders = ', '.join(f':line_id_{i}' for i in range(len(line_ids)))
        params = {f"line_id_{i}": line_id for i, line_id in enumerate(line_ids)}

        result = await self.session.execute(
            text(f"DELETE FROM triples WHERE subject_id IN ({placeholders})"),
            params,
        )

        # Return the count of line items deleted (not triples)
        return len(line_ids)

    async def atomic_update_order_with_lines(
        self,
        order_id: str,
        order_status: Optional[str] = None,
        customer_id: Optional[str] = None,
        store_id: Optional[str] = None,
        delivery_window_start: Optional[str] = None,
        delivery_window_end: Optional[str] = None,
        line_items: list[OrderLineCreate] = None,
    ) -> OrderLineFlat:
        """
        Atomically update order fields and replace all line items in a single transaction.

        This method ensures that both order field updates and line item replacements
        happen atomically - either all succeed or all fail together.

        Args:
            order_id: Order ID to update
            order_status: New order status (optional)
            customer_id: New customer ID (optional)
            store_id: New store ID (optional)
            delivery_window_start: New delivery window start (optional)
            delivery_window_end: New delivery window end (optional)
            line_items: Complete new set of line items (replaces all existing)

        Returns:
            Updated order data

        Raises:
            ValueError: If order not found or validation fails
        """
        logger.info(f"🔵 [TRANSACTION START] Starting atomic update for {order_id} with {len(line_items) if line_items else 0} line items")

        # Build order field triples to upsert
        order_triples: list[TripleCreate] = []

        if order_status is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="order_status",
                    object_value=order_status,
                    object_type="string",
                )
            )

        if customer_id is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="placed_by",
                    object_value=customer_id,
                    object_type="entity_ref",
                )
            )

        if store_id is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="order_store",
                    object_value=store_id,
                    object_type="entity_ref",
                )
            )

        if delivery_window_start is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="delivery_window_start",
                    object_value=delivery_window_start,
                    object_type="timestamp",
                )
            )

        if delivery_window_end is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="delivery_window_end",
                    object_value=delivery_window_end,
                    object_type="timestamp",
                )
            )

        # Step 1: Upsert order fields (if any)
        if order_triples:
            logger.info(f"  [STEP 1/3] Upserting {len(order_triples)} order field(s)")
            await self.triple_service.upsert_triples_batch(order_triples)

        # Step 2: Delete all existing line items
        logger.info(f"  [STEP 2/3] Deleting all existing line items for {order_id}")
        deleted_count = await self.delete_order_lines(order_id)
        logger.info(f"  [STEP 2/3] Deleted {deleted_count} existing line item(s)")

        # Step 3: Create new line items (if any)
        if line_items:
            logger.info(f"  [STEP 3/3] Creating {len(line_items)} new line item(s)")
            await self.create_line_items_batch(order_id, line_items)

        # logger.info(f"✅ [ATOMIC UPDATE] Completed atomic update for {order_id} (awaiting transaction commit)")

        # Note: order_total_amount will be auto-calculated by the materialized view
        # based on the new line items

        return None  # Could return updated order if needed

    async def update_order_fields(
        self,
        order_id: str,
        order_status: Optional[str] = None,
        customer_id: Optional[str] = None,
        store_id: Optional[str] = None,
        delivery_window_start: Optional[str] = None,
        delivery_window_end: Optional[str] = None,
        line_items: Optional[list[OrderLineCreate]] = None,
    ) -> None:
        """Update order fields and optionally patch line items.

        This method only updates what changed:
        - Order fields: only upsert provided fields
        - Line items (if provided): smart patch - only update/add/delete what changed

        Args:
            order_id: Order ID to update
            order_status: New order status (optional)
            customer_id: New customer ID (optional)
            store_id: New store ID (optional)
            delivery_window_start: New delivery window start (optional)
            delivery_window_end: New delivery window end (optional)
            line_items: New line items to patch (optional). If provided, will smart-patch.

        Raises:
            ValueError: If order not found
        """
        # Validate order exists
        order_check = await self.session.execute(
            text("SELECT 1 FROM triples WHERE subject_id = :order_id LIMIT 1"),
            {"order_id": order_id}
        )
        if not order_check.fetchone():
            raise ValueError(f"Order {order_id} not found")

        # Validate line sequence uniqueness if provided
        if line_items is not None:
            sequences = [item.line_sequence for item in line_items]
            if len(sequences) != len(set(sequences)):
                raise ValueError("line_sequence values must be unique")
            if any(seq < 1 for seq in sequences):
                raise ValueError("line_sequence must be positive")

        field_count = sum([
            order_status is not None,
            customer_id is not None,
            store_id is not None,
            delivery_window_start is not None,
            delivery_window_end is not None,
        ])
        line_item_count = len(line_items) if line_items is not None else 0
        logger.info(
            f"🔵 [TRANSACTION START] Patching {order_id}: "
            f"{field_count} field(s), {line_item_count} line item(s)"
        )

        order_triples = []

        # Build list of triples to upsert (only for provided fields)
        if order_status is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="order_status",
                    object_value=order_status,
                    object_type="string",
                )
            )

        if customer_id is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="placed_by",
                    object_value=customer_id,
                    object_type="entity_ref",
                )
            )

        if store_id is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="order_store",
                    object_value=store_id,
                    object_type="entity_ref",
                )
            )

        if delivery_window_start is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="delivery_window_start",
                    object_value=delivery_window_start,
                    object_type="timestamp",
                )
            )

        if delivery_window_end is not None:
            order_triples.append(
                TripleCreate(
                    subject_id=order_id,
                    predicate="delivery_window_end",
                    object_value=delivery_window_end,
                    object_type="timestamp",
                )
            )

        # Only upsert if there are fields to update
        if order_triples:
            logger.info(f"📝 [PARTIAL UPDATE] Updating {len(order_triples)} order field(s) for {order_id}")
            await self.triple_service.upsert_triples_batch(order_triples)

        # Smart line item patching (if provided)
        if line_items is not None:
            # Get existing line items
            existing_lines_result = await self.session.execute(
                text("""
                    SELECT DISTINCT subject_id
                    FROM triples
                    WHERE predicate = 'line_of_order' AND object_value = :order_id
                """),
                {"order_id": order_id},
            )
            existing_line_ids = {row.subject_id for row in existing_lines_result.fetchall()}

            # Get existing line item details (line_sequence -> line_id mapping)
            existing_items_map = {}
            if existing_line_ids:
                # Batch fetch all line sequence numbers in a single query
                existing_items_result = await self.session.execute(
                    text("""
                        SELECT subject_id, object_value
                        FROM triples
                        WHERE subject_id = ANY(:line_ids) AND predicate = 'line_sequence'
                    """),
                    {"line_ids": list(existing_line_ids)},
                )
                existing_items_map = {
                    int(row.object_value): row.subject_id
                    for row in existing_items_result.fetchall()
                }

            # Batch fetch all existing values for all line items in a single query
            existing_vals_by_line = {}
            if existing_line_ids:
                existing_vals_result = await self.session.execute(
                    text("""
                        SELECT subject_id, predicate, object_value
                        FROM triples
                        WHERE subject_id = ANY(:line_ids)
                    """),
                    {"line_ids": list(existing_line_ids)},
                )
                for row in existing_vals_result.fetchall():
                    if row.subject_id not in existing_vals_by_line:
                        existing_vals_by_line[row.subject_id] = {}
                    existing_vals_by_line[row.subject_id][row.predicate] = row.object_value

            # Track which line items to keep
            line_ids_to_keep = set()

            # Process each new line item
            for new_item in line_items:
                line_sequence = new_item.line_sequence
                existing_line_id = existing_items_map.get(line_sequence)

                if existing_line_id:
                    # Line item exists at this sequence - check if it changed
                    line_ids_to_keep.add(existing_line_id)

                    # Get existing values from our batch-fetched data
                    existing_vals = existing_vals_by_line.get(existing_line_id, {})

                    # Build triples for changed fields only (line_amount is derived in Materialize)
                    changed_triples = []

                    if existing_vals.get("line_product") != new_item.product_id:
                        changed_triples.append(TripleCreate(
                            subject_id=existing_line_id,
                            predicate="line_product",
                            object_value=new_item.product_id,
                            object_type="entity_ref",
                        ))

                    # Use normalized decimal comparison for numeric fields
                    existing_qty = self._normalize_decimal(existing_vals.get("quantity"))
                    new_qty = self._normalize_decimal(new_item.quantity)
                    if existing_qty != new_qty:
                        changed_triples.append(TripleCreate(
                            subject_id=existing_line_id,
                            predicate="quantity",
                            object_value=str(new_item.quantity),
                            object_type="int",
                        ))

                    if self._normalize_decimal(existing_vals.get("order_line_unit_price")) != self._normalize_decimal(new_item.unit_price):
                        changed_triples.append(TripleCreate(
                            subject_id=existing_line_id,
                            predicate="order_line_unit_price",
                            object_value=str(new_item.unit_price),
                            object_type="float",
                        ))

                    if existing_vals.get("perishable_flag") != str(new_item.perishable_flag).lower():
                        changed_triples.append(TripleCreate(
                            subject_id=existing_line_id,
                            predicate="perishable_flag",
                            object_value=str(new_item.perishable_flag).lower(),
                            object_type="bool",
                        ))

                    if self._normalize_decimal(existing_vals.get("line_sequence")) != self._normalize_decimal(line_sequence):
                        changed_triples.append(TripleCreate(
                            subject_id=existing_line_id,
                            predicate="line_sequence",
                            object_value=str(line_sequence),
                            object_type="int",
                        ))

                    # Only update if something actually changed
                    if changed_triples:
                        logger.info(f"  📝 Updating {len(changed_triples)} triple(s) for line item seq={line_sequence}")
                        await self.triple_service.upsert_triples_batch(changed_triples)

                else:
                    # New line item - create it
                    line_id = self._generate_line_id()
                    line_ids_to_keep.add(line_id)
                    logger.info(f"  ➕ Creating new line item seq={line_sequence}")
                    await self._create_single_line_item(order_id, line_id, new_item)

            # Delete line items that are no longer in the new list
            line_ids_to_delete = existing_line_ids - line_ids_to_keep
            if line_ids_to_delete:
                logger.info(f"  🗑️  Deleting {len(line_ids_to_delete)} line item(s)")
                await self.session.execute(
                    text("DELETE FROM triples WHERE subject_id = ANY(:line_ids)"),
                    {"line_ids": list(line_ids_to_delete)},
                )

        return None

    async def _create_single_line_item(
        self, order_id: str, line_id: str, line_item: OrderLineCreate
    ) -> None:
        """Helper to create a single line item.

        Args:
            order_id: Parent order ID
            line_id: Generated line item ID
            line_item: Line item data
        """
        triples = self._create_line_item_triples(line_id, order_id, line_item)
        await self.triple_service.create_triples_batch(triples)
