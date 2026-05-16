"""Correlate agent writes with Materialize reads -- the demo's headline beat.

Lifecycle of one write:
  1. Agent emits a write `tool_call` (manage_order_lines, create_order, ...) -> push
     it onto the pending queue with t_tool_call.
  2. Matching `tool_result` arrives -> pop the pending entry, scrape PKs from result
     content (and original args), open a `WriteRecord` per PK with t_tool_result.
  3. `mz_subscribe` row whose columns contain a tracked PK with diff>0 -> set
     t_mv_reflects.
  4. A *subsequent* agent `tool_result` whose content mentions the same PK -> the
     agent has just re-observed its own write through Materialize. Set
     t_re_observed and emit the AgentClimax annotation.

Edges handled:
- Tools are popped from the pending queue in arrival order; LangGraph emits one
  result per call sequentially.
- Same PK rewritten quickly: latest record wins (overwrite open_writes[pk]).
- Records older than EXPIRY_SEC without re-observation are evicted.
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass

from .feeds.types import (
    AgentClimax,
    AgentEvent,
    MzAnnotation,
    MzRow,
    WriteRecord,
    now_mono,
)

# Tool names that mutate state. Match agents/src/tools/*.
WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {"manage_order_lines", "create_order", "create_customer", "write_triples"}
)

PK_PATTERN = re.compile(r"FM-[A-Za-z0-9]+")
EXPIRY_SEC = 60.0  # drop records that haven't been re-observed within the window


@dataclass
class _Pending:
    tool: str
    t_tool_call: float
    args_pks: set[str]
    submitted_at: float | None


class WriteTracker:
    """Stateful correlator. Single instance per app."""

    def __init__(self) -> None:
        self._pending: deque[_Pending] = deque()
        self._open: dict[str, WriteRecord] = {}
        self._closed: deque[WriteRecord] = deque(maxlen=20)
        # The wall time the user submitted the *latest* prompt. End-to-end measures
        # from this. Updated by app.notify_submit().
        self._latest_submit_t: float | None = None

    # ----- inputs -----

    def notify_submit(self, t_mono: float) -> None:
        self._latest_submit_t = t_mono

    def on_agent_event(self, evt: AgentEvent) -> AgentClimax | None:
        if evt.type == "tool_call":
            data = evt.data or {}
            name = data.get("name") or ""
            if name in WRITE_TOOL_NAMES:
                args_pks = _extract_pks(data.get("args", {}))
                self._pending.append(
                    _Pending(
                        tool=name,
                        t_tool_call=evt.t_mono,
                        args_pks=args_pks,
                        submitted_at=self._latest_submit_t,
                    )
                )
            return None

        if evt.type == "tool_result":
            content = (evt.data or {}).get("content", "")
            result_pks = _extract_pks(content)
            # Phase A: if a write tool_call is in flight, this result belongs to it.
            if self._pending:
                pending = self._pending.popleft()
                pks = pending.args_pks | result_pks
                for pk in pks:
                    self._open[pk] = WriteRecord(
                        pk=pk,
                        tool=pending.tool,
                        t_tool_call=pending.t_tool_call,
                        t_tool_result=evt.t_mono,
                        submitted_at=pending.submitted_at,
                    )
                # No climax for the originating tool_result, even if it mentions PK.
                return None
            # Phase B: not a write result -- is it a re-observation?
            for pk in result_pks:
                wr = self._open.get(pk)
                if wr and wr.t_mv_reflects is not None and wr.t_re_observed is None:
                    wr.t_re_observed = evt.t_mono
                    self._closed.append(wr)
                    self._open.pop(pk, None)
                    return AgentClimax(pk=pk, deltas=wr.deltas())
            return None

        return None

    def on_mz_row(self, row: MzRow) -> MzAnnotation | None:
        if row.is_heartbeat or row.diff <= 0:
            return None
        for pk in _pks_from_row(row):
            wr = self._open.get(pk)
            if wr and wr.t_mv_reflects is None:
                wr.t_mv_reflects = row.t_mono
                return MzAnnotation(pk=pk)
        return None

    # ----- outputs -----

    def latest_closed(self) -> WriteRecord | None:
        return self._closed[-1] if self._closed else None

    def open_count(self) -> int:
        return len(self._open)

    def tracked_pks(self) -> list[str]:
        """PKs of agent writes still awaiting re-observation."""
        return list(self._open.keys())

    def expire_old(self) -> None:
        """Drop open records older than EXPIRY_SEC."""
        now = now_mono()
        stale = [
            pk
            for pk, wr in self._open.items()
            if now - wr.t_tool_call > EXPIRY_SEC
        ]
        for pk in stale:
            self._open.pop(pk, None)


# ----- helpers -----


def _extract_pks(value) -> set[str]:
    """Find all FM-* tokens in a value (dict, list, str, anything stringifiable)."""
    text = _to_text(value)
    return set(PK_PATTERN.findall(text))


def _pks_from_row(row: MzRow) -> set[str]:
    pks: set[str] = set()
    for col, val in row.columns.items():
        if isinstance(val, str):
            pks.update(PK_PATTERN.findall(val))
    return pks


def _to_text(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)
