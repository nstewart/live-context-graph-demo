"""Kafka consumer that taps the Materialize CDC topics to feed the
propagation event store (which powers the web "System Performance" card).

In the old architecture the search-sync SUBSCRIBE worker emitted a
PropagationEvent for every document it wrote to OpenSearch. In the Kafka
pipeline the OpenSearch sink connector writes silently, so this consumer
reproduces those events by tapping the SAME Debezium topics that Materialize
sinks into.

Why this is actually cleaner than the old path: Materialize emits an
``ENVELOPE DEBEZIUM`` record carrying both ``before`` and ``after`` images, so
the old/new field diff is read directly off the message instead of being
reconstructed by consolidating separate +1/-1 SUBSCRIBE deltas.

The consumer is blocking (confluent-kafka), so it runs in a background thread
while the asyncio aiohttp API serves the events on :8083 (see main.py).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

# Resilient import so the pure-Python helpers (_materialize_timestamp,
# _make_event, _field_changes, ...) can be imported and unit-tested without
# confluent_kafka installed. The consumer (run_consumer) needs the real lib.
try:
    from confluent_kafka import DeserializingConsumer, KafkaException
    from confluent_kafka.error import ConsumeError
    from confluent_kafka.schema_registry import SchemaRegistryClient
    from confluent_kafka.schema_registry.avro import AvroDeserializer
    from confluent_kafka.serialization import StringDeserializer
except ImportError:  # pragma: no cover - exercised only without confluent_kafka
    DeserializingConsumer = None
    SchemaRegistryClient = None
    AvroDeserializer = None
    StringDeserializer = None
    KafkaException = Exception
    ConsumeError = Exception

from src.propagation_events import PropagationEvent, get_propagation_store

logger = logging.getLogger(__name__)

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "redpanda:29092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://redpanda:8081")
GROUP_ID = os.environ.get("TAP_GROUP_ID", "propagation-tap")
TOPICS = [t.strip() for t in os.environ.get("TAP_TOPICS", "orders,inventory").split(",") if t.strip()]

# Top-level columns we do NOT surface as scalar field changes (too noisy / not
# scalar). line_items diffs are summarized rather than expanded.
_SKIP_DIFF_FIELDS = {"line_items", "search_text", "effective_updated_at"}


def _operation(before: Optional[dict], after: Optional[dict]) -> str:
    if before is None and after is not None:
        return "INSERT"
    if before is not None and after is None:
        return "DELETE"
    return "UPDATE"


def _field_changes(before: Optional[dict], after: Optional[dict]) -> dict[str, dict[str, str]]:
    """Diff scalar columns between the before and after images."""
    if not before or not after:
        return {}
    changes: dict[str, dict[str, str]] = {}
    keys = set(before) | set(after)
    for k in keys:
        if k in _SKIP_DIFF_FIELDS:
            continue
        ov, nv = before.get(k), after.get(k)
        if ov != nv:
            changes[k] = {"old": "" if ov is None else str(ov), "new": "" if nv is None else str(nv)}
    return changes


def _doc_id(index_name: str, row: dict) -> Optional[str]:
    key = "order_id" if index_name == "orders" else "inventory_id"
    return row.get(key)


def _display_name(index_name: str, row: dict) -> Optional[str]:
    if index_name == "orders":
        return row.get("order_number") or row.get("order_id")
    return row.get("product_name") or row.get("inventory_id")


def _materialize_timestamp(msg) -> str:
    """Return Materialize's logical timestamp for the message.

    Materialize adds a `materialize-timestamp` header to every sinked message
    whose value is the LOGICAL time at which the change occurred (epoch ms, as a
    decimal string). Every message describing the same logical write — across
    BOTH the orders and inventory sinks — carries the same value, so using it as
    mz_ts groups a write's full effect under one timestamp. The Kafka record
    timestamp (msg.timestamp()) is only the per-sink emission time and differs by
    tens of ms, so we prefer the header and fall back to the record time.
    """
    for key, value in (msg.headers() or []):
        if key == "materialize-timestamp" and value is not None:
            try:
                return str(int(value.decode() if isinstance(value, (bytes, bytearray)) else value))
            except (ValueError, AttributeError):
                pass
    _, record_ts_ms = msg.timestamp()
    return str(record_ts_ms)


def _make_event(topic: str, mz_ts: str, value: Optional[dict]) -> Optional[PropagationEvent]:
    if value is None:
        return None
    before = value.get("before")
    after = value.get("after")
    row = after or before
    if not row:
        return None

    index_name = topic  # CREATE SINK topic name == OpenSearch index name
    doc_id = _doc_id(index_name, row)
    if not doc_id:
        return None

    return PropagationEvent(
        mz_ts=mz_ts,
        index_name=index_name,
        doc_id=doc_id,
        operation=_operation(before, after),
        field_changes=_field_changes(before, after),
        display_name=_display_name(index_name, row),
        store_id=row.get("store_id"),
        product_id=row.get("product_id"),
    )


def run_consumer(stop_flag) -> None:
    """Blocking poll loop. `stop_flag` is a threading.Event."""
    sr = SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})
    consumer = DeserializingConsumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": GROUP_ID,
            # Live feed: only show changes from now on, mirroring the old worker
            # which discarded the initial SUBSCRIBE snapshot.
            "auto.offset.reset": "latest",
            "key.deserializer": StringDeserializer("utf_8"),
            "value.deserializer": AvroDeserializer(sr),
        }
    )
    consumer.subscribe(TOPICS)
    logger.info("Propagation tap consuming topics %s from %s", TOPICS, BOOTSTRAP_SERVERS)

    store = get_propagation_store()
    try:
        while not stop_flag.is_set():
            # DeserializingConsumer.poll() RAISES (it does not return a msg with
            # .error()) on Kafka errors and on deserialization failures. Many are
            # transient — e.g. UNKNOWN_TOPIC_OR_PART while a topic is (re)created,
            # or a single un-deserializable record — and must NOT kill the tap.
            # Catch, log, and keep polling; librdkafka refreshes metadata and
            # recovers on its own.
            try:
                msg = consumer.poll(1.0)
            except ConsumeError as e:
                logger.warning("Consume error (continuing): %s", e)
                continue
            except KafkaException as e:
                logger.warning("Kafka exception (continuing): %s", e)
                continue
            if msg is None:
                continue
            if msg.error():
                logger.warning("Kafka error: %s", msg.error())
                continue
            try:
                event = _make_event(msg.topic(), _materialize_timestamp(msg), msg.value())
            except Exception:  # noqa: BLE001 - never let one bad record kill the tap
                logger.exception("Failed to build propagation event")
                continue
            if event is not None:
                store.add_event(event)
    finally:
        consumer.close()
        logger.info("Propagation tap consumer stopped")
