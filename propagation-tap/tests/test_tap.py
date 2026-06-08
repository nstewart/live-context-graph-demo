"""Regression tests for how the propagation tap derives mz_ts.

The propagation widget groups a write's effects by mz_ts. mz_ts MUST come from
Materialize's `materialize-timestamp` header (the LOGICAL time the change
occurred, identical across every sink for one write), NOT from the Kafka record
timestamp (per-sink emission time, which differs by tens of ms between the
orders and inventory sinks) and NOT from the Kafka offset (unique per message).

If someone reverts to msg.timestamp() or msg.offset(), these tests fail.
"""

from src.tap import _make_event, _materialize_timestamp


class FakeMsg:
    """Minimal stand-in for a confluent_kafka Message."""

    def __init__(self, headers, record_ts_ms):
        self._headers = headers  # list[(str, bytes|str)] | None
        self._record_ts = record_ts_ms

    def headers(self):
        return self._headers

    def timestamp(self):
        # (timestamp_type, epoch_ms) — the per-sink EMISSION time.
        return (1, self._record_ts)


LOGICAL_TS = 1780950684500   # materialize-timestamp header value
RECORD_TS = 1780950684634    # Kafka record (emission) timestamp — intentionally different


def test_prefers_materialize_timestamp_header_over_record_timestamp():
    msg = FakeMsg([("materialize-timestamp", b"1780950684500")], record_ts_ms=RECORD_TS)
    assert _materialize_timestamp(msg) == str(LOGICAL_TS)
    # Guard against a regression to the emission timestamp.
    assert _materialize_timestamp(msg) != str(RECORD_TS)


def test_header_value_may_be_str():
    msg = FakeMsg([("materialize-timestamp", "1780950684500")], record_ts_ms=RECORD_TS)
    assert _materialize_timestamp(msg) == str(LOGICAL_TS)


def test_falls_back_to_record_timestamp_when_header_absent():
    msg = FakeMsg([], record_ts_ms=RECORD_TS)
    assert _materialize_timestamp(msg) == str(RECORD_TS)

    msg_none = FakeMsg(None, record_ts_ms=RECORD_TS)
    assert _materialize_timestamp(msg_none) == str(RECORD_TS)


def test_one_write_groups_orders_and_inventory_under_one_mz_ts():
    """The core regression: orders and inventory messages from one logical write
    carry the same materialize-timestamp header, so their events share mz_ts —
    even though their Kafka record timestamps differ."""
    header = [("materialize-timestamp", b"1780950684500")]
    inv_msg = FakeMsg(header, record_ts_ms=1780950684591)  # inventory emitted earlier
    ord_msg = FakeMsg(header, record_ts_ms=1780950684634)  # orders emitted ~40ms later

    inv_value = {
        "before": {"inventory_id": "inventory:INV-1", "product_name": "Veggie Straws", "category": "Snacks"},
        "after": {"inventory_id": "inventory:INV-1", "product_name": "Veggie Straws", "category": "Snacks > Veggie Straws"},
    }
    ord_value = {
        "before": {"order_id": "order:FM-1", "order_number": "FM-1", "embedding_text": "old"},
        "after": {"order_id": "order:FM-1", "order_number": "FM-1", "embedding_text": "new"},
    }

    inv_event = _make_event("inventory", _materialize_timestamp(inv_msg), inv_value)
    ord_event = _make_event("orders", _materialize_timestamp(ord_msg), ord_value)

    assert inv_event is not None and ord_event is not None
    assert inv_event.mz_ts == ord_event.mz_ts == str(LOGICAL_TS)
    # And they are distinct index/doc events (so this isn't trivially true).
    assert inv_event.index_name == "inventory" and ord_event.index_name == "orders"


def test_make_event_computes_field_changes_from_before_after():
    header = [("materialize-timestamp", b"1780950684500")]
    value = {
        "before": {"inventory_id": "inventory:INV-1", "category": "Snacks"},
        "after": {"inventory_id": "inventory:INV-1", "category": "Snacks > Veggie Straws"},
    }
    event = _make_event("inventory", _materialize_timestamp(FakeMsg(header, 1)), value)
    assert event.operation == "UPDATE"
    assert "category" in event.field_changes
    assert event.field_changes["category"] == {"old": "Snacks", "new": "Snacks > Veggie Straws"}
