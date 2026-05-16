"""Typed events emitted by the three feeds."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal


def now_mono() -> float:
    return time.monotonic()


def now_wall() -> float:
    return time.time()


# -------- Agent SSE events --------

AgentEventType = Literal[
    "tool_call", "tool_result", "thinking", "response", "error", "done", "connect", "disconnect"
]


@dataclass
class AgentEvent:
    type: AgentEventType
    data: Any
    t_mono: float = field(default_factory=now_mono)
    t_wall: float = field(default_factory=now_wall)


# -------- Materialize SUBSCRIBE rows --------


@dataclass
class MzRow:
    """One row from a SUBSCRIBE feed.

    For SUBSCRIBE ... WITH (PROGRESS, SNAPSHOT = false) the wire format is
    (mz_timestamp, mz_progressed, mz_diff, *columns).
    Progress heartbeats arrive with `progressed=True` and no column values.
    """

    view: str
    mz_timestamp: int
    progressed: bool
    diff: int  # +1 insert, -1 delete; 0 on progress heartbeats
    columns: dict[str, Any]
    t_mono: float = field(default_factory=now_mono)
    t_wall: float = field(default_factory=now_wall)

    @property
    def is_heartbeat(self) -> bool:
        return self.progressed


# -------- Load pulse --------


@dataclass
class LoadTick:
    orders_last_60s: int
    sparkline_buckets: list[int]  # 30 buckets of 2s each
    by_zone: dict[str, int]


# -------- Timing / write correlation --------


@dataclass
class WriteRecord:
    """One agent write, traced from tool_call through agent re-observation."""

    pk: str
    tool: str
    t_tool_call: float
    t_tool_result: float | None = None
    t_mv_reflects: float | None = None
    t_re_observed: float | None = None
    submitted_at: float | None = None  # original prompt-submit time, for end-to-end

    @property
    def closed(self) -> bool:
        return self.t_re_observed is not None

    def deltas(self) -> dict[str, float | None]:
        """Convert absolute monotonic timestamps into the four headline deltas."""

        def safe(a, b):
            return (a - b) if (a is not None and b is not None) else None

        return {
            "tool_to_mv": safe(self.t_mv_reflects, self.t_tool_result),
            "mv_to_reobs": safe(self.t_re_observed, self.t_mv_reflects),
            "write_to_reobs": safe(self.t_re_observed, self.t_tool_result),
            "end_to_end": safe(self.t_re_observed, self.submitted_at),
        }


@dataclass
class MzAnnotation:
    """Hint to the MZ panel: this row matched an open agent write."""

    pk: str


@dataclass
class AgentClimax:
    """Hint to the agent panel: this tool_result re-observed our own write."""

    pk: str
    deltas: dict[str, float | None]


# -------- Write Propagation (matches PropagationContext.tsx + audit/propagation APIs) --------


@dataclass
class FieldChange:
    """One field's before/after on a propagation event (matches search-sync output)."""

    old: str | None
    new: str | None


@dataclass
class SourceWriteEvent:
    """One PG triple write from /api/audit/writes."""

    subject_id: str
    predicate: str
    old_value: str | None
    new_value: str | None
    operation: str  # "INSERT" | "UPDATE" | "DELETE"
    timestamp: float  # seconds since epoch
    batch_id: str | None
    t_received: float = field(default_factory=now_wall)

    @property
    def dedup_key(self) -> str:
        return f"{self.timestamp}-{self.subject_id}-{self.predicate}"


@dataclass
class PropagationEvent:
    """One index-side change from /propagation/events/all (search-sync transform output)."""

    mz_ts: str
    index_name: str
    doc_id: str
    operation: str  # "INSERT" | "UPDATE" | "DELETE"
    field_changes: dict[str, FieldChange]
    timestamp: float
    display_name: str | None
    store_id: str | None = None
    product_id: str | None = None
    t_received: float = field(default_factory=now_wall)

    @property
    def dedup_key(self) -> str:
        return f"{self.mz_ts}-{self.index_name}-{self.doc_id}-{self.operation}"
