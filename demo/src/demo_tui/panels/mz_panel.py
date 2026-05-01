"""Right column: live-read side, mirroring web's PropagationWidget.

Renders two stacked sections inside a VerticalScroll:

  POSTGRESQL WRITES   (N transactions, M triples)     <- /api/audit/writes
   ...
  INDEX PROPAGATION   (K updates)                      <- /propagation/events/all
   ...

Logic is a 1:1 port of web/src/components/PropagationWidget.tsx + the polling
in web/src/contexts/PropagationContext.tsx. The two sections poll independently
and dedupe by the same keys the React widget uses.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..feeds.types import PropagationEvent, SourceWriteEvent

# Display caps -- match React's UI bounds (web/src/contexts/PropagationContext.tsx)
MAX_SOURCE_WRITES = 1000
MAX_PROPAGATION_EVENTS = 1000
DISPLAY_BATCHES = 10
DISPLAY_TIMESTAMPS = 10
DISPLAY_DOCS_PER_TIMESTAMP = 5


class MzPanel(VerticalScroll):
    """Two-section panel: PG source writes on top, index propagation below."""

    DEFAULT_CSS = """
    MzPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
    }
    MzPanel:focus {
        border: heavy $success;
    }
    MzPanel > .section_header {
        height: 1;
        color: $text;
        text-style: bold;
        background: $boost;
        padding: 0 1;
    }
    MzPanel > .section_body {
        height: auto;
        padding: 0 1;
    }
    """

    can_focus = True
    BORDER_TITLE = "(3) MATERIALIZE -- live read side"
    BINDINGS = [
        Binding("left", "scroll_left", "scroll left", show=False),
        Binding("right", "scroll_right", "scroll right", show=False),
        Binding("ctrl+pageup", "page_left", "page left", show=False),
        Binding("ctrl+pagedown", "page_right", "page right", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._writes: list[SourceWriteEvent] = []
        self._props: list[PropagationEvent] = []
        self._writes_seen: set[str] = set()
        self._props_seen: set[str] = set()
        self._tracked_pks: set[str] = set()  # set by app from WriteTracker.open_writes
        # Counters that survive memory eviction (match React's totalIndexUpdates)
        self._writes_total = 0
        self._props_total = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="pg_header", classes="section_header")
        yield Static("[dim](no PG writes yet)[/dim]", id="pg_section", classes="section_body")
        yield Static("", id="prop_header", classes="section_header")
        yield Static(
            "[dim](no index propagation events yet)[/dim]",
            id="prop_section",
            classes="section_body",
        )

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self.border_subtitle = "polling /api/audit/writes + /propagation/events/all"
        self._refresh()

    # ----- inputs -----

    def on_source_write(self, event: SourceWriteEvent) -> None:
        if event.dedup_key in self._writes_seen:
            return
        self._writes_seen.add(event.dedup_key)
        self._writes.insert(0, event)
        self._writes_total += 1
        if len(self._writes) > MAX_SOURCE_WRITES:
            evicted = self._writes[MAX_SOURCE_WRITES:]
            self._writes = self._writes[:MAX_SOURCE_WRITES]
            for ev in evicted:
                self._writes_seen.discard(ev.dedup_key)
        self._refresh()

    def on_propagation_event(self, event: PropagationEvent) -> None:
        if event.dedup_key in self._props_seen:
            return
        self._props_seen.add(event.dedup_key)
        self._props.insert(0, event)
        self._props_total += 1
        if len(self._props) > MAX_PROPAGATION_EVENTS:
            evicted = self._props[MAX_PROPAGATION_EVENTS:]
            self._props = self._props[:MAX_PROPAGATION_EVENTS]
            for ev in evicted:
                self._props_seen.discard(ev.dedup_key)
        self._refresh()

    def set_tracked_pks(self, pks: Iterable[str]) -> None:
        """The app passes in PKs the agent has recently written, for highlight."""
        self._tracked_pks = set(pks)

    # ----- render -----

    def _refresh(self) -> None:
        try:
            self.query_one("#pg_header", Static).update(self._render_pg_header())
            self.query_one("#pg_section", Static).update(self._render_pg_section())
            self.query_one("#prop_header", Static).update(self._render_prop_header())
            self.query_one("#prop_section", Static).update(self._render_prop_section())
        except Exception:
            # Widget may not be mounted yet; skip silently.
            pass

    # PG WRITES section ------------------------------------------------------

    def _render_pg_header(self) -> str:
        batches = self._group_writes_by_batch(self._writes)
        n_tx = len(batches)
        n_triples = len(self._writes)
        return (
            f"POSTGRESQL WRITES  [dim]({n_tx} transaction{'s' if n_tx != 1 else ''}, "
            f"{n_triples} triple{'s' if n_triples != 1 else ''}, {self._writes_total} total)[/dim]"
        )

    def _render_pg_section(self) -> str:
        if not self._writes:
            return "[dim](no PG writes yet -- waiting for /api/audit/writes)[/dim]"
        batches = self._group_writes_by_batch(self._writes)
        lines: list[str] = []
        for batch in batches[:DISPLAY_BATCHES]:
            lines.append(self._render_batch(batch))
        if len(batches) > DISPLAY_BATCHES:
            lines.append(f"[dim]  ... and {len(batches) - DISPLAY_BATCHES} more transactions[/dim]")
        return "\n".join(lines)

    @staticmethod
    def _group_writes_by_batch(writes: list[SourceWriteEvent]) -> list[list[SourceWriteEvent]]:
        """Group writes by batch_id; preserve descending-time order."""
        # writes is already sorted desc (newest at index 0)
        groups: dict[str, list[SourceWriteEvent]] = defaultdict(list)
        order: list[str] = []
        for w in writes:
            key = w.batch_id or f"single-{w.timestamp}-{w.subject_id}-{w.predicate}"
            if key not in groups:
                order.append(key)
            groups[key].append(w)
        return [groups[k] for k in order]

    def _render_batch(self, batch: list[SourceWriteEvent]) -> str:
        first = batch[0]
        ts = _fmt_wall(first.timestamp)
        starred = self._is_starred_subject(first.subject_id) or any(
            self._is_starred_subject(w.subject_id) for w in batch
        )
        prefix = "[bold yellow]*[/bold yellow] " if starred else "  "
        if len(batch) == 1:
            return prefix + self._render_single_write(ts, first)
        # multi-write batch: summary line
        subjects = {w.subject_id for w in batch}
        op = first.operation
        op_color = _op_color(op)
        return (
            f"{prefix}[dim]{ts}[/dim]  "
            f"[bold]{len(subjects)} subject{'s' if len(subjects) != 1 else ''}[/bold]  "
            f"[dim]({len(batch)} triple{'s' if len(batch) != 1 else ''})[/dim]  "
            f"[{op_color}]{op}[/{op_color}]"
        )

    def _render_single_write(self, ts: str, w: SourceWriteEvent) -> str:
        old = _fmt_field_value(w.old_value) if w.old_value is not None else None
        new = _fmt_field_value(w.new_value)
        op_color = _op_color(w.operation)
        if old is not None:
            arrow = (
                f"[red]{old}[/red] [dim]->[/dim] [green]{new}[/green]"
            )
        else:
            arrow = f"[green]{new}[/green]"
        return (
            f"[dim]{ts}[/dim]  "
            f"[cyan]{w.subject_id}[/cyan][dim].[/dim][magenta]{w.predicate}[/magenta] "
            f"[dim]:[/dim] {arrow}  [{op_color}]{w.operation}[/{op_color}]"
        )

    def _is_starred_subject(self, subject_id: str) -> bool:
        if not self._tracked_pks:
            return False
        # Tracked PKs are e.g. "FM-1042"; subject_id is e.g. "order:FM-1042"
        return any(pk in subject_id for pk in self._tracked_pks)

    # INDEX PROPAGATION section ----------------------------------------------

    def _render_prop_header(self) -> str:
        return (
            f"INDEX PROPAGATION  [dim]({len(self._props)} update"
            f"{'s' if len(self._props) != 1 else ''} buffered, "
            f"{self._props_total} total)[/dim]"
        )

    def _render_prop_section(self) -> str:
        if not self._props:
            return "[dim](no propagation events yet -- waiting for /propagation/events/all)[/dim]"

        # Group by mz_ts desc (props is already insert-on-top, but mz_ts ordering
        # may vary because polling can reorder; explicit sort).
        by_mz_ts: dict[str, list[PropagationEvent]] = defaultdict(list)
        for ev in self._props:
            by_mz_ts[ev.mz_ts].append(ev)
        sorted_ts = sorted(by_mz_ts.keys(), key=lambda x: int(x), reverse=True)

        lines: list[str] = []
        for mz_ts in sorted_ts[:DISPLAY_TIMESTAMPS]:
            events = by_mz_ts[mz_ts]
            # dedup within ts by doc_id (latest wins)
            by_doc: dict[str, list[PropagationEvent]] = defaultdict(list)
            for e in events:
                by_doc[e.doc_id].append(e)
            wall_ts = _fmt_wall(events[0].timestamp)
            n_docs = len(by_doc)
            n_fields = sum(len(e.field_changes) for e in events)
            lines.append(
                f"[dim]{wall_ts}[/dim]  [dim]mz_ts:[/dim] [bold]{mz_ts}[/bold]  "
                f"[dim]({n_docs} doc{'s' if n_docs != 1 else ''}, "
                f"{n_fields} field{'s' if n_fields != 1 else ''})[/dim]"
            )
            for doc_id, doc_events in list(by_doc.items())[:DISPLAY_DOCS_PER_TIMESTAMP]:
                lines.extend(self._render_doc(doc_id, doc_events))
            if n_docs > DISPLAY_DOCS_PER_TIMESTAMP:
                lines.append(
                    f"   [dim]... and {n_docs - DISPLAY_DOCS_PER_TIMESTAMP} more docs[/dim]"
                )
        if len(sorted_ts) > DISPLAY_TIMESTAMPS:
            lines.append(f"[dim]... and {len(sorted_ts) - DISPLAY_TIMESTAMPS} more timestamps[/dim]")
        return "\n".join(lines)

    def _render_doc(self, doc_id: str, events: list[PropagationEvent]) -> list[str]:
        # Merge field_changes from all events for this doc
        merged: dict[str, tuple[str | None, str | None]] = {}
        ops: set[str] = set()
        display_name: str | None = None
        index_names: set[str] = set()
        for e in events:
            ops.add(e.operation)
            index_names.add(e.index_name)
            if not display_name and e.display_name:
                display_name = e.display_name
            for field, change in e.field_changes.items():
                merged[field] = (change.old, change.new)
        op = "INSERT" if "INSERT" in ops else "DELETE" if "DELETE" in ops else "UPDATE"
        op_color = _op_color(op)

        starred = self._is_starred_doc(doc_id, display_name)
        prefix = "[bold yellow]*[/bold yellow] " if starred else "  "
        name_part = (
            f"[cyan]{display_name}[/cyan] [dim]({doc_id})[/dim]"
            if display_name
            else f"[cyan]{doc_id}[/cyan]"
        )
        idx_part = ", ".join(sorted(index_names))
        out = [
            f" {prefix}{name_part}  [{op_color}]{op}[/{op_color}]  [dim]{idx_part}[/dim]"
        ]
        for field, (old, new) in merged.items():
            out.append(f"     [dim]{field}:[/dim] {_render_field_diff(old, new)}")
        return out

    def _is_starred_doc(self, doc_id: str, display_name: str | None) -> bool:
        if not self._tracked_pks:
            return False
        return any(pk in doc_id or (display_name and pk in display_name) for pk in self._tracked_pks)


# ----- formatting helpers (match the React formatFieldValue logic) -----


def _op_color(op: str) -> str:
    if op == "INSERT":
        return "green"
    if op == "DELETE":
        return "red"
    return "yellow"


def _fmt_wall(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _fmt_field_value(value: str | None) -> str:
    """Mirror web/src/components/PropagationWidget.tsx::formatFieldValue."""
    if value is None:
        return "(null)"
    s = str(value)
    if s.startswith("[") and s.endswith("]"):
        # Best-effort length summarization for list-like values.
        try:
            import json

            normalized = (
                s.replace("'", '"').replace("None", "null").replace("False", "false").replace("True", "true")
            )
            parsed = json.loads(normalized)
            if isinstance(parsed, list):
                return f"[{len(parsed)} item{'s' if len(parsed) != 1 else ''}]"
        except Exception:
            pass
    if s.startswith("{") and s.endswith("}") and len(s) > 50:
        return "{...}"
    if len(s) > 100:
        return s[:97] + "..."
    return s


def _render_field_diff(old: str | None, new: str | None) -> str:
    old_fmt = _fmt_field_value(old) if old is not None else None
    new_fmt = _fmt_field_value(new) if new is not None else None
    if old_fmt is None:
        return f"[green]{new_fmt}[/green]"
    if new_fmt is None:
        return f"[red]{old_fmt}[/red]"
    return f"[red]{old_fmt}[/red] [dim]->[/dim] [green]{new_fmt}[/green]"
