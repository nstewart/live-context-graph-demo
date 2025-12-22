"""In-memory event store for tracking write propagation to search indexes."""

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PropagationEvent:
    """A single propagation event representing an index update."""

    mz_ts: str  # Materialize timestamp
    index_name: str  # OpenSearch index name
    doc_id: str  # Document ID (e.g., "order:FM-1001")
    operation: str  # INSERT, UPDATE, or DELETE
    field_changes: dict[str, dict[str, str]] = field(default_factory=dict)  # {field: {old, new}}
    timestamp: float = field(default_factory=time.time)  # Unix timestamp when event was recorded

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "mz_ts": self.mz_ts,
            "index_name": self.index_name,
            "doc_id": self.doc_id,
            "operation": self.operation,
            "field_changes": self.field_changes,
            "timestamp": self.timestamp,
        }


class PropagationEventStore:
    """Thread-safe in-memory store for propagation events with TTL-based expiration."""

    def __init__(self, ttl_seconds: float = 300.0):
        """Initialize the store.

        Args:
            ttl_seconds: Time-to-live for events in seconds (default: 5 minutes)
        """
        self._events: list[PropagationEvent] = []
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def add_event(self, event: PropagationEvent) -> None:
        """Add an event to the store."""
        with self._lock:
            self._events.append(event)
            self._cleanup_expired()

    def add_events(self, events: list[PropagationEvent]) -> None:
        """Add multiple events to the store."""
        with self._lock:
            self._events.extend(events)
            self._cleanup_expired()

    def get_events(
        self,
        since_mz_ts: Optional[str] = None,
        subject_ids: Optional[list[str]] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query events from the store.

        Args:
            since_mz_ts: Only return events with mz_ts greater than this value
            subject_ids: Filter to events where doc_id starts with any of these prefixes
            limit: Maximum number of events to return

        Returns:
            List of events as dicts, most recent first
        """
        with self._lock:
            self._cleanup_expired()

            results = []
            for event in reversed(self._events):
                # Filter by mz_ts if specified
                if since_mz_ts is not None and event.mz_ts <= since_mz_ts:
                    continue

                # Filter by subject_ids if specified
                if subject_ids is not None:
                    # Check if doc_id matches any subject_id prefix
                    # e.g., doc_id="order:FM-1001" matches subject_id="order:FM-1001"
                    # Also handle case where doc_id might be in a different format
                    matches = False
                    for subject_id in subject_ids:
                        if event.doc_id == subject_id or event.doc_id.startswith(subject_id):
                            matches = True
                            break
                    if not matches:
                        continue

                results.append(event.to_dict())

                if len(results) >= limit:
                    break

            return results

    def get_all_events(self, limit: int = 100) -> list[dict]:
        """Get all recent events without filtering.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of events as dicts, most recent first
        """
        return self.get_events(limit=limit)

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


# Global singleton instance for use across workers
_store: Optional[PropagationEventStore] = None


def get_propagation_store() -> PropagationEventStore:
    """Get the global propagation event store singleton."""
    global _store
    if _store is None:
        _store = PropagationEventStore()
    return _store
