"""Bottom-right: reaction time + the agent feedback loop."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

from ..feeds.types import WriteRecord


class TimingPanel(Static):
    DEFAULT_CSS = """
    TimingPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
        content-align: left top;
    }
    """

    BORDER_TITLE = "TIMING"
    BORDER_SUBTITLE = "lower is better"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._record: WriteRecord | None = None
        self._open_count: int = 0
        self._reaction_stats: dict[str, Any] | None = None

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self.border_subtitle = self.BORDER_SUBTITLE
        self.update(self._compose_body())

    # ----- inputs from the app -----

    def set_record(self, record: WriteRecord | None, open_count: int = 0) -> None:
        self._record = record
        self._open_count = open_count
        self._refresh()

    def set_reaction_stats(self, stats: dict[str, Any]) -> None:
        self._reaction_stats = stats
        self._refresh()

    # ----- render -----

    def _refresh(self) -> None:
        if self._open_count and not self._record:
            self.border_subtitle = (
                f"lower is better  ({self._open_count} write"
                f"{'s' if self._open_count != 1 else ''} pending)"
            )
        elif self._record:
            self.border_subtitle = (
                f"closed -- {self._open_count} pending"
                if self._open_count
                else "closed"
            )
        else:
            self.border_subtitle = "lower is better"
        self.update(self._compose_body())

    def _compose_body(self) -> str:
        # NOTE: do NOT name this `_render` -- Widget._render() is Textual
        # internal and must return a Visual; shadowing it crashes the
        # compositor with `'str' object has no attribute 'render_strips'`.
        return (
            self._render_reaction_section()
            + "\n"
            + self._render_loop_section()
        )

    def _render_reaction_section(self) -> str:
        s = self._reaction_stats
        if not s:
            return (
                "[bold]REACTION TIME[/bold]  [dim]live_price via inventory_pricing_mv "
                "(rolling 5min window)[/dim]\n"
                "[dim]  freshness  --        (NOW - effective_updated_at)\n"
                "  query      --        (point SELECT latency)[/dim]"
            )
        f = s.get("freshness", {})
        q = s.get("query", {})
        f_total = s.get("freshness_total", 0)
        q_total = s.get("query_total", 0)
        f_window = s.get("freshness_window", 0)
        q_window = s.get("query_window", 0)
        window_max = s.get("window_max", 300)
        return (
            f"[bold]REACTION TIME[/bold]  [dim]live_price via inventory_pricing_mv  "
            f"(rolling {window_max} samples, ~5min window)[/dim]\n"
            f"  freshness  p50 {_fmt_ms(f.get('p50'))}   p99 {_fmt_ms(f.get('p99'))}   "
            f"max {_fmt_ms(f.get('max'))}   [dim]NOW - effective_updated_at  "
            f"({f_window}/{window_max} in window, {f_total} total)[/dim]\n"
            f"  query      p50 {_fmt_ms(q.get('p50'))}   p99 {_fmt_ms(q.get('p99'))}   "
            f"max {_fmt_ms(q.get('max'))}   [dim]point SELECT latency  "
            f"({q_window}/{window_max} in window, {q_total} total)[/dim]"
        )

    def _render_loop_section(self) -> str:
        if self._record is None:
            return (
                "[bold]THE LOOP[/bold]  [dim]waiting for first agent write...[/dim]\n"
                "[dim]  tool_result -> mv reflects        :  --\n"
                "  mv reflects -> agent re-observes  :  --\n"
                "  agent write -> agent re-observes  :  --   <- the loop\n"
                "  end-to-end (prompt -> resolved)   :  --[/dim]"
            )
        d = self._record.deltas()
        return (
            f"[bold]THE LOOP[/bold]  [dim]last write: [/dim]"
            f"[bold]{self._record.pk}[/bold] [dim]via {self._record.tool}[/dim]\n"
            f"  tool_result -> mv reflects        : {_fmt_s(d['tool_to_mv'])}\n"
            f"  mv reflects -> agent re-observes  : {_fmt_s(d['mv_to_reobs'])}\n"
            f"  agent write -> agent re-observes  : {_fmt_climax_s(d['write_to_reobs'])}\n"
            f"  end-to-end (prompt -> resolved)   : {_fmt_s(d['end_to_end'])}"
        )


def _fmt_ms(ms: float | None) -> str:
    if ms is None:
        return "[dim]   --[/dim]"
    color = _color_ms(ms)
    return f"[{color}]{ms:6.1f}ms[/{color}]"


def _color_ms(ms: float) -> str:
    if ms < 500:
        return "green"
    if ms < 2000:
        return "yellow"
    return "red"


def _fmt_s(seconds: float | None) -> str:
    if seconds is None:
        return "[dim] --[/dim]"
    color = _color_s(seconds)
    return f"[{color}]{seconds:6.2f}s[/{color}]"


def _fmt_climax_s(seconds: float | None) -> str:
    if seconds is None:
        return "[dim] --[/dim]"
    color = _color_s(seconds)
    return f"[bold {color}]{seconds:6.2f}s[/bold {color}]   [bold green]<- the loop[/bold green]"


def _color_s(seconds: float) -> str:
    if seconds < 2.0:
        return "green"
    if seconds < 5.0:
        return "yellow"
    return "red"
