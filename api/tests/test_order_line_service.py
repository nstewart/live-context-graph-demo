"""Unit tests for OrderLineService."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.freshmart.models import OrderLineCreate, OrderLineFlat, OrderLineUpdate
from src.freshmart.order_line_service import OrderLineService
from src.triples.models import TripleCreate


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = AsyncMock()
    return session


@pytest.fixture
def service(mock_session):
    """Create OrderLineService with mock session."""
    return OrderLineService(mock_session)


class TestGenerateLineId:
    """Tests for _generate_line_id helper method."""

    def test_generates_uuid_format(self, service):
        """Generates line ID in UUID format."""
        line_id = service._generate_line_id()
        assert line_id.startswith("orderline:")
        # UUID is 36 chars (8-4-4-4-12 with hyphens)
        uuid_part = line_id.replace("orderline:", "")
        assert len(uuid_part) == 36
        assert uuid_part.count("-") == 4

    def test_generates_unique_ids(self, service):
        """Generates unique IDs on each call."""
        id1 = service._generate_line_id()
        id2 = service._generate_line_id()
        assert id1 != id2


class TestCreateLineItemTriples:
    """Tests for _create_line_item_triples helper method."""

    def test_creates_all_required_triples(self, service):
        """Creates required triples for a line item (perishable_flag and line_amount are derived)."""
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=2,
            unit_price=Decimal("12.50"),
            line_sequence=1,
        )

        triples = service._create_line_item_triples(
            "orderline:test-123", "order:FM-1001", line_item
        )

        # 4 base triples + 1 for line_sequence = 5
        assert len(triples) == 5
        predicates = {t.predicate for t in triples}
        assert predicates == {
            "line_of_order",
            "line_product",
            "quantity",
            "order_line_unit_price",
            "line_sequence",
        }

    def test_omits_line_sequence_when_not_provided(self, service):
        """Omits line_sequence triple when not provided."""
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=2,
            unit_price=Decimal("12.50"),
            # No line_sequence
        )

        triples = service._create_line_item_triples(
            "orderline:test-123", "order:FM-1001", line_item
        )

        # 4 base triples only
        assert len(triples) == 4
        predicates = {t.predicate for t in triples}
        assert "line_sequence" not in predicates

    def test_sets_correct_subject_id(self, service):
        """Sets correct subject_id for all triples."""
        line_id = "orderline:test-uuid-123"
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=1,
            unit_price=Decimal("5.00"),
        )

        triples = service._create_line_item_triples(line_id, "order:FM-1001", line_item)

        assert all(t.subject_id == line_id for t in triples)


class TestCreateLineItemsBatch:
    """Tests for create_line_items_batch method."""

    @pytest.mark.asyncio
    async def test_validates_unique_sequences(self, service):
        """Raises ValueError if line_sequence values are not unique."""
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_sequence=1,
            ),
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=1,  # Duplicate sequence
            ),
        ]

        with pytest.raises(ValueError, match="line_sequence values must be unique"):
            await service.create_line_items_batch("order:FM-1001", line_items)

    @pytest.mark.asyncio
    async def test_creates_triples_for_each_line_item(self, service, mock_session):
        """Creates triples for each line item."""
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_sequence=1,
            ),
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=2,
            ),
        ]

        # Mock store_id query
        mock_store_result = MagicMock()
        mock_store_result.fetchone.return_value = MagicMock(store_id="store:S001")
        mock_session.execute.return_value = mock_store_result

        with patch.object(
            service.triple_service, "create_triples_batch", new_callable=AsyncMock
        ) as mock_create:
            with patch.object(
                service, "list_order_lines", new_callable=AsyncMock
            ) as mock_list:
                with patch.object(
                    service, "_fetch_live_prices", new_callable=AsyncMock
                ) as mock_prices:
                    mock_prices.return_value = {}
                    mock_list.return_value = []
                    await service.create_line_items_batch("order:FM-1001", line_items)

                    # Verify create was called
                    assert mock_create.called


class TestListOrderLines:
    """Tests for list_order_lines method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_lines(self, service, mock_session):
        """Returns empty list when order has no line items."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        result = await service.list_order_lines("order:FM-1001")

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_sorted_by_sequence(self, service, mock_session):
        """Returns line items sorted by line_sequence."""
        now = datetime.now()
        mock_rows = [
            MagicMock(
                line_id="orderline:uuid-001",
                order_id="order:FM-1001",
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10.00"),
                line_amount=Decimal("20.00"),
                line_sequence=1,
                perishable_flag=False,
                product_name="Product 1",
                category="Test",
                effective_updated_at=now,
            ),
            MagicMock(
                line_id="orderline:uuid-002",
                order_id="order:FM-1001",
                product_id="product:PROD-002",
                quantity=1,
                unit_price=Decimal("30.00"),
                line_amount=Decimal("30.00"),
                line_sequence=2,
                perishable_flag=True,
                product_name="Product 2",
                category="Test",
                effective_updated_at=now,
            ),
        ]
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        result = await service.list_order_lines("order:FM-1001")

        assert len(result) == 2
        assert result[0].line_sequence == 1
        assert result[1].line_sequence == 2


class TestUpdateLineItem:
    """Tests for update_line_item method."""

    @pytest.mark.asyncio
    async def test_raises_error_if_not_found(self, service, mock_session):
        """Raises ValueError if line item does not exist."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        update = OrderLineUpdate(quantity=5)

        with pytest.raises(ValueError, match="Line item .* not found"):
            await service.update_line_item("orderline:uuid-001", update)

    @pytest.mark.asyncio
    async def test_updates_quantity(self, service, mock_session):
        """Updates quantity when it changes."""
        now = datetime.now()
        current_line = MagicMock(
            line_id="orderline:uuid-001",
            order_id="order:FM-1001",
            product_id="product:PROD-001",
            quantity=2,
            unit_price=Decimal("10.00"),
            line_amount=Decimal("20.00"),
            line_sequence=1,
            perishable_flag=True,
            effective_updated_at=now,
        )

        # Mock get_line_item to return current state twice
        with patch.object(service, "get_line_item", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = [
                OrderLineFlat(**current_line.__dict__),
                OrderLineFlat(
                    line_id="orderline:uuid-001",
                    order_id="order:FM-1001",
                    product_id="product:PROD-001",
                    quantity=5,
                    unit_price=Decimal("10.00"),
                    line_amount=Decimal("50.00"),  # Derived
                    line_sequence=1,
                    effective_updated_at=now,
                ),
            ]

            update = OrderLineUpdate(quantity=5)
            result = await service.update_line_item("orderline:uuid-001", update)

            assert result.quantity == 5
            assert result.line_amount == Decimal("50.00")


class TestDeleteLineItem:
    """Tests for delete_line_item method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, service, mock_session):
        """Returns True when line item is successfully deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 5  # 5 triples deleted (perishable_flag and line_amount are derived)
        mock_session.execute.return_value = mock_result

        result = await service.delete_line_item("orderline:uuid-001")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, service, mock_session):
        """Returns False when line item does not exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await service.delete_line_item("orderline:uuid-999")

        assert result is False


class TestDeleteOrderLines:
    """Tests for delete_order_lines (cascade delete) method."""

    @pytest.mark.asyncio
    async def test_returns_count_of_deleted_lines(self, service, mock_session):
        """Returns count of deleted line items (not triples)."""
        # Mock finding 3 line item IDs
        mock_line_ids = MagicMock()
        mock_line_ids.fetchall.return_value = [
            MagicMock(subject_id="orderline:uuid-001"),
            MagicMock(subject_id="orderline:uuid-002"),
            MagicMock(subject_id="orderline:uuid-003"),
        ]

        # Mock delete result
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 15  # 3 items * 5 triples each

        mock_session.execute.side_effect = [mock_line_ids, mock_delete_result]

        count = await service.delete_order_lines("order:FM-1001")

        assert count == 3  # Number of line items, not triples

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_lines(self, service, mock_session):
        """Returns 0 when order has no line items."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        count = await service.delete_order_lines("order:FM-9999")

        assert count == 0


class TestUpdateOrderFields:
    """Tests for update_order_fields method (smart-patch)."""

    @pytest.mark.asyncio
    async def test_raises_error_if_order_not_found(self, service, mock_session):
        """Raises ValueError if order does not exist."""
        # Mock order existence check returning None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Order .* not found"):
            await service.update_order_fields("order:INVALID", order_status="DELIVERED")

    @pytest.mark.asyncio
    async def test_validates_line_sequence_uniqueness(self, service, mock_session):
        """Raises ValueError if line_sequence values are not unique."""
        # Mock order exists
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_session.execute.return_value = mock_result

        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_sequence=1,
            ),
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=1,  # Duplicate!
            ),
        ]

        with pytest.raises(ValueError, match="line_sequence values must be unique"):
            await service.update_order_fields("order:FM-1001", line_items=line_items)

    @pytest.mark.asyncio
    async def test_updates_only_order_fields_when_no_line_items(
        self, service, mock_session
    ):
        """Updates only order fields when line_items not provided."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)
        mock_session.execute.return_value = mock_order_check

        with patch.object(
            service.triple_service, "upsert_triples_batch", new_callable=AsyncMock
        ) as mock_upsert:
            await service.update_order_fields("order:FM-1001", order_status="DELIVERED")

            # Verify upsert was called with order status triple
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0][0]
            assert len(call_args) == 1
            assert call_args[0].predicate == "order_status"
            assert call_args[0].object_value == "DELIVERED"

    @pytest.mark.asyncio
    async def test_creates_new_line_items(self, service, mock_session):
        """Creates new line items when they don't exist."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock no existing line items
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = []

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
        ]

        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10.00"),
                line_sequence=1,
            ),
        ]

        with patch.object(
            service, "_create_single_line_item", new_callable=AsyncMock
        ) as mock_create:
            await service.update_order_fields("order:FM-1001", line_items=line_items)

            # Verify create was called for new line item
            assert mock_create.called

    @pytest.mark.asyncio
    async def test_updates_changed_line_item_fields_only(self, service, mock_session):
        """Updates only changed fields in existing line items."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock existing line item
        existing_line_id = "orderline:uuid-123"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values query (no line_amount stored)
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(
                subject_id=existing_line_id,
                predicate="line_product",
                object_value="product:PROD-001",
            ),
            MagicMock(
                subject_id=existing_line_id, predicate="quantity", object_value="2"
            ),
            MagicMock(
                subject_id=existing_line_id,
                predicate="order_line_unit_price",
                object_value="10.00",
            ),
            MagicMock(
                subject_id=existing_line_id, predicate="line_sequence", object_value="1"
            ),
        ]

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
        ]

        # New line item with quantity changed
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=5,  # Changed from 2
                unit_price=Decimal("10.00"),
                line_sequence=1,
            ),
        ]

        with patch.object(
            service.triple_service, "upsert_triples_batch", new_callable=AsyncMock
        ) as mock_upsert:
            await service.update_order_fields("order:FM-1001", line_items=line_items)

            # Verify upsert was called with only changed triples
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0][0]

            # Should update only quantity (line_amount is derived, not stored)
            predicates = {t.predicate for t in call_args}
            assert "quantity" in predicates
            assert "line_amount" not in predicates  # Not stored

    @pytest.mark.asyncio
    async def test_deletes_removed_line_items(self, service, mock_session):
        """Deletes line items that are no longer in the new list."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock two existing line items
        existing_line_id_1 = "orderline:uuid-123"
        existing_line_id_2 = "orderline:uuid-456"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id_1),
            MagicMock(subject_id=existing_line_id_2),
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id_1, object_value="1"),
            MagicMock(subject_id=existing_line_id_2, object_value="2"),
        ]

        # Mock existing values query for both items - use consistent decimal format
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(
                subject_id=existing_line_id_1,
                predicate="line_product",
                object_value="product:PROD-001",
            ),
            MagicMock(
                subject_id=existing_line_id_1, predicate="quantity", object_value="2"
            ),
            MagicMock(
                subject_id=existing_line_id_1,
                predicate="order_line_unit_price",
                object_value="10",  # Normalized format
            ),
            MagicMock(
                subject_id=existing_line_id_1, predicate="line_sequence", object_value="1"
            ),
            MagicMock(
                subject_id=existing_line_id_2,
                predicate="line_product",
                object_value="product:PROD-002",
            ),
            MagicMock(
                subject_id=existing_line_id_2, predicate="quantity", object_value="1"
            ),
            MagicMock(
                subject_id=existing_line_id_2,
                predicate="order_line_unit_price",
                object_value="20",
            ),
            MagicMock(
                subject_id=existing_line_id_2, predicate="line_sequence", object_value="2"
            ),
        ]

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 5

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
            mock_delete_result,  # Delete query
        ]

        # New line items - only keep first one
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10"),  # Match the normalized format
                line_sequence=1,
            ),
        ]

        await service.update_order_fields("order:FM-1001", line_items=line_items)

        # Verify session.execute was called 5 times (includes delete call)
        # 1. Order check, 2. Get existing lines, 3. Get sequences, 4. Get values, 5. Delete
        assert mock_session.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_handles_empty_line_items_list(self, service, mock_session):
        """Deletes all line items when empty list is provided."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock existing line item
        existing_line_id = "orderline:uuid-123"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query (required when existing_line_ids is not empty)
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values query (required when existing_line_ids is not empty)
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = []

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 5

        # With empty line_items list, the code should:
        # 1. Check order exists
        # 2. Get existing line items
        # 3. Get line sequences (for existing items)
        # 4. Get existing values (for existing items)
        # 5. Delete all existing (since new list is empty)
        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
            mock_delete_result,
        ]

        # Empty line items list
        await service.update_order_fields("order:FM-1001", line_items=[])

        # Verify session.execute was called 5 times (includes delete call)
        # 1. Order check, 2. Get existing lines, 3. Get sequences, 4. Get values, 5. Delete
        assert mock_session.execute.call_count == 5

    @pytest.mark.asyncio
    async def test_decimal_comparison_handles_precision(self, service, mock_session):
        """Correctly compares decimal values with matching normalized representations."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock existing line item
        existing_line_id = "orderline:uuid-123"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values - use normalized format "10" (no decimals)
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(
                subject_id=existing_line_id,
                predicate="line_product",
                object_value="product:PROD-001",
            ),
            MagicMock(
                subject_id=existing_line_id, predicate="quantity", object_value="2"
            ),
            MagicMock(
                subject_id=existing_line_id,
                predicate="order_line_unit_price",
                object_value="10",  # Normalized format (Decimal normalizes to this)
            ),
            MagicMock(
                subject_id=existing_line_id, predicate="line_sequence", object_value="1"
            ),
        ]

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
        ]

        # New line item with same values - Decimal("10") normalizes to "10"
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10"),  # Matches normalized "10"
                line_sequence=1,
            ),
        ]

        with patch.object(
            service.triple_service, "upsert_triples_batch", new_callable=AsyncMock
        ) as mock_upsert:
            await service.update_order_fields("order:FM-1001", line_items=line_items)

            # Should NOT call upsert since values are the same after normalization
            assert not mock_upsert.called
