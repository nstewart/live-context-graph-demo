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

    def test_generates_correct_format(self, service):
        """Generates line ID in correct format."""
        line_id = service._generate_line_id("order:FM-1001", 1)
        assert line_id == "orderline:FM-1001-001"

    def test_pads_sequence_with_zeros(self, service):
        """Pads sequence number with leading zeros."""
        line_id = service._generate_line_id("order:FM-1001", 5)
        assert line_id == "orderline:FM-1001-005"

        line_id = service._generate_line_id("order:FM-1001", 99)
        assert line_id == "orderline:FM-1001-099"


class TestCreateLineItemTriples:
    """Tests for _create_line_item_triples helper method."""

    def test_creates_all_required_triples(self, service):
        """Creates all 7 required triples for a line item."""
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=2,
            unit_price=Decimal("12.50"),
            line_sequence=1,
            perishable_flag=True,
        )

        triples = service._create_line_item_triples("order:FM-1001", 1, line_item)

        assert len(triples) == 7
        predicates = {t.predicate for t in triples}
        assert predicates == {
            "line_of_order",
            "line_product",
            "quantity",
            "order_line_unit_price",
            "line_amount",
            "line_sequence",
            "perishable_flag",
        }

    def test_calculates_line_amount_correctly(self, service):
        """Calculates line_amount as quantity * unit_price."""
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=3,
            unit_price=Decimal("10.00"),
            line_sequence=1,
            perishable_flag=False,
        )

        triples = service._create_line_item_triples("order:FM-1001", 1, line_item)

        line_amount_triple = next(t for t in triples if t.predicate == "line_amount")
        assert line_amount_triple.object_value == "30.00"

    def test_sets_correct_line_id(self, service):
        """Sets correct line_id for all triples."""
        line_item = OrderLineCreate(
            product_id="product:PROD-001",
            quantity=1,
            unit_price=Decimal("5.00"),
            line_sequence=2,
            perishable_flag=True,
        )

        triples = service._create_line_item_triples("order:FM-1001", 2, line_item)

        assert all(t.subject_id == "orderline:FM-1001-002" for t in triples)


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
                perishable_flag=False,
            ),
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=1,  # Duplicate sequence
                perishable_flag=True,
            ),
        ]

        with pytest.raises(ValueError, match="line_sequence values must be unique"):
            await service.create_line_items_batch("order:FM-1001", line_items)

    @pytest.mark.asyncio
    async def test_sorts_by_sequence_before_creating(self, service, mock_session):
        """Sorts line items by sequence before creating triples."""
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=2,
                perishable_flag=True,
            ),
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_sequence=1,
                perishable_flag=False,
            ),
        ]

        # Mock triple service and list method
        with patch.object(service.triple_service, "create_triples_batch", new_callable=AsyncMock) as mock_create:
            with patch.object(service, "list_order_lines", new_callable=AsyncMock) as mock_list:
                mock_list.return_value = []
                await service.create_line_items_batch("order:FM-1001", line_items)

                # Verify create was called with triples in correct order
                assert mock_create.called
                call_args = mock_create.call_args[0][0]

                # First triple should be for sequence 1
                assert call_args[0].subject_id == "orderline:FM-1001-001"


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
                line_id="orderline:FM-1001-001",
                order_id="order:FM-1001",
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10.00"),
                line_amount=Decimal("20.00"),
                line_sequence=1,
                perishable_flag=True,
                effective_updated_at=now,
            ),
            MagicMock(
                line_id="orderline:FM-1001-002",
                order_id="order:FM-1001",
                product_id="product:PROD-002",
                quantity=1,
                unit_price=Decimal("30.00"),
                line_amount=Decimal("30.00"),
                line_sequence=2,
                perishable_flag=False,
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
            await service.update_line_item("orderline:FM-1001-001", update)

    @pytest.mark.asyncio
    async def test_recalculates_line_amount_on_quantity_change(self, service, mock_session):
        """Recalculates line_amount when quantity changes."""
        now = datetime.now()
        current_line = MagicMock(
            line_id="orderline:FM-1001-001",
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
                    line_id="orderline:FM-1001-001",
                    order_id="order:FM-1001",
                    product_id="product:PROD-001",
                    quantity=5,
                    unit_price=Decimal("10.00"),
                    line_amount=Decimal("50.00"),  # Updated
                    line_sequence=1,
                    perishable_flag=True,
                    effective_updated_at=now,
                ),
            ]

            update = OrderLineUpdate(quantity=5)
            result = await service.update_line_item("orderline:FM-1001-001", update)

            assert result.quantity == 5
            assert result.line_amount == Decimal("50.00")


class TestDeleteLineItem:
    """Tests for delete_line_item method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, service, mock_session):
        """Returns True when line item is successfully deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 7  # 7 triples deleted
        mock_session.execute.return_value = mock_result

        result = await service.delete_line_item("orderline:FM-1001-001")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, service, mock_session):
        """Returns False when line item does not exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        result = await service.delete_line_item("orderline:FM-1001-999")

        assert result is False


class TestDeleteOrderLines:
    """Tests for delete_order_lines (cascade delete) method."""

    @pytest.mark.asyncio
    async def test_returns_count_of_deleted_lines(self, service, mock_session):
        """Returns count of deleted line items."""
        mock_result = MagicMock()
        mock_result.rowcount = 21  # 3 line items * 7 triples each
        mock_session.execute.return_value = mock_result

        count = await service.delete_order_lines("order:FM-1001")

        assert count == 3

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_lines(self, service, mock_session):
        """Returns 0 when order has no line items."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
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
                perishable_flag=False,
            ),
            OrderLineCreate(
                product_id="product:PROD-002",
                quantity=2,
                unit_price=Decimal("20.00"),
                line_sequence=1,  # Duplicate!
                perishable_flag=True,
            ),
        ]

        with pytest.raises(ValueError, match="line_sequence values must be unique"):
            await service.update_order_fields("order:FM-1001", line_items=line_items)

    @pytest.mark.asyncio
    async def test_validates_line_sequence_positive(self, service, mock_session):
        """Raises ValueError if line_sequence is not positive."""
        # Mock order exists
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_session.execute.return_value = mock_result

        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=1,
                unit_price=Decimal("10.00"),
                line_sequence=0,  # Invalid!
                perishable_flag=False,
            ),
        ]

        with pytest.raises(ValueError, match="line_sequence must be positive"):
            await service.update_order_fields("order:FM-1001", line_items=line_items)

    @pytest.mark.asyncio
    async def test_updates_only_order_fields_when_no_line_items(self, service, mock_session):
        """Updates only order fields when line_items not provided."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)
        mock_session.execute.return_value = mock_order_check

        with patch.object(service.triple_service, "upsert_triples_batch", new_callable=AsyncMock) as mock_upsert:
            await service.update_order_fields(
                "order:FM-1001",
                order_status="DELIVERED"
            )

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
                perishable_flag=False,
            ),
        ]

        with patch.object(service, "_create_single_line_item", new_callable=AsyncMock) as mock_create:
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
        existing_line_id = "orderline:12345"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values query
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, predicate="line_product", object_value="product:PROD-001"),
            MagicMock(subject_id=existing_line_id, predicate="quantity", object_value="2"),
            MagicMock(subject_id=existing_line_id, predicate="order_line_unit_price", object_value="10.00"),
            MagicMock(subject_id=existing_line_id, predicate="line_amount", object_value="20.00"),
            MagicMock(subject_id=existing_line_id, predicate="perishable_flag", object_value="false"),
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
                perishable_flag=False,
            ),
        ]

        with patch.object(service.triple_service, "upsert_triples_batch", new_callable=AsyncMock) as mock_upsert:
            await service.update_order_fields("order:FM-1001", line_items=line_items)

            # Verify upsert was called with only changed triples
            assert mock_upsert.called
            call_args = mock_upsert.call_args[0][0]

            # Should update quantity and line_amount (quantity changed, so amount changes)
            predicates = {t.predicate for t in call_args}
            assert "quantity" in predicates
            assert "line_amount" in predicates

            # Should NOT update unchanged fields
            assert len(call_args) == 2  # Only quantity and line_amount

    @pytest.mark.asyncio
    async def test_deletes_removed_line_items(self, service, mock_session):
        """Deletes line items that are no longer in the new list."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock two existing line items
        existing_line_id_1 = "orderline:12345"
        existing_line_id_2 = "orderline:67890"
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

        # Mock existing values query for first item only
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id_1, predicate="line_product", object_value="product:PROD-001"),
            MagicMock(subject_id=existing_line_id_1, predicate="quantity", object_value="2"),
            MagicMock(subject_id=existing_line_id_1, predicate="order_line_unit_price", object_value="10.00"),
            MagicMock(subject_id=existing_line_id_1, predicate="line_amount", object_value="20.00"),
            MagicMock(subject_id=existing_line_id_1, predicate="perishable_flag", object_value="false"),
        ]

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 7

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
                unit_price=Decimal("10.00"),
                line_sequence=1,
                perishable_flag=False,
            ),
        ]

        await service.update_order_fields("order:FM-1001", line_items=line_items)

        # Verify delete was called for second line item
        delete_calls = [call for call in mock_session.execute.call_args_list
                       if "DELETE" in str(call)]
        assert len(delete_calls) == 1

    @pytest.mark.asyncio
    async def test_handles_empty_line_items_list(self, service, mock_session):
        """Deletes all line items when empty list is provided."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock existing line item
        existing_line_id = "orderline:12345"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values query
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = []

        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 7

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
            mock_delete_result,
        ]

        # Empty line items list
        await service.update_order_fields("order:FM-1001", line_items=[])

        # Verify delete was called
        delete_calls = [call for call in mock_session.execute.call_args_list
                       if "DELETE" in str(call)]
        assert len(delete_calls) == 1

    @pytest.mark.asyncio
    async def test_decimal_comparison_handles_precision(self, service, mock_session):
        """Correctly compares decimal values with different string representations."""
        # Mock order exists
        mock_order_check = MagicMock()
        mock_order_check.fetchone.return_value = (1,)

        # Mock existing line item
        existing_line_id = "orderline:12345"
        mock_existing_lines = MagicMock()
        mock_existing_lines.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id)
        ]

        # Mock line sequence query
        mock_line_seq = MagicMock()
        mock_line_seq.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, object_value="1")
        ]

        # Mock existing values with "10.0" (different format from "10.00")
        mock_existing_vals = MagicMock()
        mock_existing_vals.fetchall.return_value = [
            MagicMock(subject_id=existing_line_id, predicate="line_product", object_value="product:PROD-001"),
            MagicMock(subject_id=existing_line_id, predicate="quantity", object_value="2"),
            MagicMock(subject_id=existing_line_id, predicate="order_line_unit_price", object_value="10.0"),  # Different format
            MagicMock(subject_id=existing_line_id, predicate="line_amount", object_value="20"),  # Different format
            MagicMock(subject_id=existing_line_id, predicate="perishable_flag", object_value="false"),
        ]

        mock_session.execute.side_effect = [
            mock_order_check,
            mock_existing_lines,
            mock_line_seq,
            mock_existing_vals,
        ]

        # New line item with same values but different string format
        line_items = [
            OrderLineCreate(
                product_id="product:PROD-001",
                quantity=2,
                unit_price=Decimal("10.00"),  # Same as "10.0"
                line_sequence=1,
                perishable_flag=False,
            ),
        ]

        with patch.object(service.triple_service, "upsert_triples_batch", new_callable=AsyncMock) as mock_upsert:
            await service.update_order_fields("order:FM-1001", line_items=line_items)

            # Should NOT call upsert since values are actually the same
            assert not mock_upsert.called
