"""In-memory store for tracking database writes (source of propagation)."""

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


def generate_batch_id() -> str:
    """Generate a unique batch ID for grouping writes in a transaction."""
    return str(uuid.uuid4())[:8]


@dataclass
class WriteEvent:
    """A single write event representing a triple change in PostgreSQL."""

    subject_id: str  # Entity ID (e.g., "order:FM-1001")
    predicate: str  # Property name (e.g., "order_status")
    old_value: Optional[str]  # Previous value (None for inserts)
    new_value: Optional[str]  # New value (None for deletes)
    operation: str  # INSERT, UPDATE, or DELETE
    timestamp: float = field(default_factory=time.time)  # Unix timestamp
    batch_id: Optional[str] = None  # Groups writes from the same transaction

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "subject_id": self.subject_id,
            "predicate": self.predicate,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "operation": self.operation,
            "timestamp": self.timestamp,
            "batch_id": self.batch_id,
        }


class WriteEventStore:
    """Thread-safe in-memory store for write events with TTL-based expiration."""

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize the store.

        Args:
            ttl_seconds: Time-to-live for events in seconds (default: 5 minutes)
        """
        self._events: list[WriteEvent] = []
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def add_event(self, event: WriteEvent) -> None:
        """Add an event to the store."""
        with self._lock:
            self._events.append(event)
            self._cleanup_expired()

    def add_events(self, events: list[WriteEvent]) -> None:
        """Add multiple events to the store."""
        with self._lock:
            self._events.extend(events)
            self._cleanup_expired()

    def get_events(
        self,
        since_ts: Optional[float] = None,
        subject_ids: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query events from the store.

        Args:
            since_ts: Only return events with timestamp greater than this value
            subject_ids: Filter to events matching these subject IDs
            limit: Maximum number of events to return

        Returns:
            List of events as dicts, most recent first
        """
        with self._lock:
            self._cleanup_expired()

            results = []
            for event in reversed(self._events):
                # Filter by timestamp if specified
                if since_ts is not None and event.timestamp <= since_ts:
                    continue

                # Filter by subject_ids if specified
                if subject_ids is not None and event.subject_id not in subject_ids:
                    continue

                results.append(event.to_dict())

                if len(results) >= limit:
                    break

            return results

    def clear(self) -> None:
        """Clear all events from the store."""
        with self._lock:
            self._events.clear()

    def _cleanup_expired(self) -> None:
        """Remove events older than TTL. Must be called with lock held."""
        cutoff = time.time() - self._ttl_seconds
        self._events = [e for e in self._events if e.timestamp > cutoff]

    def __len__(self) -> int:
        """Return the number of events in the store."""
        with self._lock:
            return len(self._events)


# Global singleton instance
_store: Optional[WriteEventStore] = None


def get_write_store() -> WriteEventStore:
    """Get the global write event store singleton."""
    global _store
    if _store is None:
        _store = WriteEventStore()
    return _store
