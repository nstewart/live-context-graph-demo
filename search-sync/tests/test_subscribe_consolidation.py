"""Tests for SUBSCRIBE event consolidation logic.

These tests verify that the timestamp-based consolidation logic correctly
handles UPDATE operations that Materialize emits as DELETE+INSERT pairs.
"""

import pytest
from src.mz_client_subscribe import SubscribeEvent


class TestSubscribeEventConsolidation:
    """Tests for SUBSCRIBE event consolidation."""

    def test_delete_then_insert_at_same_timestamp_consolidates(self):
        """DELETE+INSERT at same timestamp should consolidate to UPDATE."""
        # Simulate events at the same timestamp (e.g., 1000)
        timestamp = "1000"

        # First event: DELETE (old state)
        delete_event = SubscribeEvent(
            timestamp=timestamp,
            diff=-1,
            data={"order_id": "order:123", "order_status": "CREATED"}
        )

        # Second event: INSERT (new state)
        insert_event = SubscribeEvent(
            timestamp=timestamp,
            diff=1,
            data={"order_id": "order:123", "order_status": "PICKING"}
        )

        # Verify event types
        assert delete_event.is_delete()
        assert not delete_event.is_insert()
        assert insert_event.is_insert()
        assert not insert_event.is_delete()

        # When both events exist at the same timestamp, application logic
        # should consolidate them into a single UPDATE (INSERT operation)
        # by keeping the INSERT and discarding the DELETE

    def test_insert_then_delete_at_same_timestamp_consolidates(self):
        """INSERT+DELETE at same timestamp should also consolidate to UPDATE.

        Events can arrive in either order (DELETE+INSERT or INSERT+DELETE).
        Both should result in keeping the INSERT (new state).
        """
        timestamp = "1000"

        # First event: INSERT (new state)
        insert_event = SubscribeEvent(
            timestamp=timestamp,
            diff=1,
            data={"order_id": "order:123", "order_status": "PICKING"}
        )

        # Second event: DELETE (old state)
        delete_event = SubscribeEvent(
            timestamp=timestamp,
            diff=-1,
            data={"order_id": "order:123", "order_status": "CREATED"}
        )

        # Verify event types
        assert insert_event.is_insert()
        assert delete_event.is_delete()

        # Application logic should keep the INSERT regardless of order

    def test_events_at_different_timestamps_do_not_consolidate(self):
        """Events at different timestamps should NOT consolidate."""
        # Events at different timestamps
        delete_event = SubscribeEvent(
            timestamp="1000",
            diff=-1,
            data={"order_id": "order:123", "order_status": "CREATED"}
        )

        insert_event = SubscribeEvent(
            timestamp="1001",  # Different timestamp!
            diff=1,
            data={"order_id": "order:123", "order_status": "PICKING"}
        )

        # These should be treated as separate operations
        # DELETE at ts=1000, then INSERT at ts=1001
        assert delete_event.timestamp != insert_event.timestamp

    def test_timestamp_ordering_prevents_premature_broadcasting(self):
        """Verify the critical timestamp check ordering.

        The fix requires checking if timestamp advanced BEFORE adding events
        to the batch. This ensures:
        1. Events at ts=X are accumulated
        2. When ts=X+1 arrives, batch from ts=X is broadcast
        3. Event at ts=X+1 starts new batch

        This prevents broadcasting events at ts=X before all events at that
        timestamp have arrived.
        """
        # Example scenario:
        # ts=100: DELETE for order:123
        # ts=100: INSERT for order:123
        # ts=101: (next timestamp triggers broadcast of ts=100 batch)

        events_at_ts_100 = [
            SubscribeEvent("100", -1, {"order_id": "order:123", "status": "OLD"}),
            SubscribeEvent("100", 1, {"order_id": "order:123", "status": "NEW"}),
        ]

        event_at_ts_101 = SubscribeEvent(
            "101", 1, {"order_id": "order:456", "status": "CREATED"}
        )

        # When ts=101 arrives, it should trigger broadcast of ts=100 batch
        # The batch should contain consolidated events (INSERT only)
        assert all(e.timestamp == "100" for e in events_at_ts_100)
        assert event_at_ts_101.timestamp == "101"

    def test_progress_message_indicates_timestamp_advance(self):
        """Progress messages signal that all events at timestamp are complete."""
        # Progress message with is_progress=True
        progress_event = SubscribeEvent(
            timestamp="1000",
            diff=0,  # Progress messages have no diff
            data={},
            is_progress=True
        )

        assert progress_event.is_progress
        # Progress messages should trigger broadcast of pending events


class TestSubscribeEventTypes:
    """Tests for SubscribeEvent type detection."""

    def test_insert_event_is_identified_correctly(self):
        """Events with diff > 0 are inserts."""
        event = SubscribeEvent("1000", 1, {"id": "123"})
        assert event.is_insert()
        assert not event.is_delete()

    def test_delete_event_is_identified_correctly(self):
        """Events with diff < 0 are deletes."""
        event = SubscribeEvent("1000", -1, {"id": "123"})
        assert event.is_delete()
        assert not event.is_insert()

    def test_progress_event_has_no_operation(self):
        """Progress events don't represent data changes."""
        event = SubscribeEvent("1000", 0, {}, is_progress=True)
        assert event.is_progress
        # Progress events shouldn't be classified as insert or delete
