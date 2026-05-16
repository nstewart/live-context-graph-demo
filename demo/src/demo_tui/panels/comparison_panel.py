"""Three-source freshness/latency comparison table.

Mirrors the table at web/src/pages/QueryStatisticsPage.tsx:1380-1547:

| Source                | Response Time (ms)     | Reaction Time (ms)     | QPS  |
|                       |  median   p99   max    |  median   p99   max    |      |
| PostgreSQL View       |  ...                   |  ...                   | ...  |
| Batch MATERIALIZED... |  ...                   |  ...                   | ...  |
| Materialize  *Best*   |  ...                   |  ...                   | ...  |

Color identity matches the React widget: PG=orange, Batch=green, MZ=cyan/blue.
"""

from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static


SOURCE_META = [
    {
        "key": "postgresql_view",
        "name": "PostgreSQL View",
        "tagline": "Fresh but SLOW (computed on every query)",
        "color": "orange3",
    },
    {
        "key": "batch_cache",
        "name": "Batch MATERIALIZED VIEW",
        "tagline": "Fast but STALE (refreshes every 60s)",
        "color": "green",
    },
    {
        "key": "materialize",
        "name": "Materialize",
        "tagline": "Fast AND Fresh (incremental via CDC)",
        "color": "cyan",
        "best": True,
    },
]


class ComparisonPanel(VerticalScroll):
    """Big right-side comparison table for the freshness demo."""

    DEFAULT_CSS = """
    ComparisonPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
    }
    ComparisonPanel:focus {
        border: heavy $success;
    }
    """

    can_focus = True
    BINDINGS = [
        Binding("left", "scroll_left", "scroll left", show=False),
        Binding("right", "scroll_right", "scroll right", show=False),
    ]

    BORDER_TITLE = "FRESHNESS UNDER LOAD  --  PostgreSQL view  vs  batch cache  vs  Materialize"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._metrics: dict[str, Any] | None = None
        self._order_id: str | None = None
        self._is_polling: bool = False

    def compose(self):
        yield Static(id="info_line", classes="info_line")
        yield Static(id="comparison_table", classes="table_body")
        yield Static(id="explainer", classes="explainer")

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self.border_subtitle = "polling /api/query-stats/metrics"
        self._refresh()

    # ----- inputs -----

    def set_session(self, order_id: str | None, is_polling: bool) -> None:
        self._order_id = order_id
        self._is_polling = is_polling
        self._refresh_info()

    def set_metrics(self, payload: dict[str, Any]) -> None:
        self._metrics = payload
        if "order_id" in payload:
            self._order_id = payload.get("order_id")
        if "is_polling" in payload:
            self._is_polling = bool(payload.get("is_polling"))
        self._refresh()

    # ----- rendering -----

    def _refresh(self) -> None:
        try:
            self.query_one("#comparison_table", Static).update(self._build_table())
            self._refresh_info()
            self.query_one("#explainer", Static).update(_EXPLAINER)
        except Exception:
            pass

    def _refresh_info(self) -> None:
        try:
            self.query_one("#info_line", Static).update(self._render_info())
        except Exception:
            pass

    def _render_info(self) -> str:
        order = self._order_id or "[dim](selecting order...)[/dim]"
        polling = (
            "[bold green]POLLING[/bold green]"
            if self._is_polling
            else "[bold red]STOPPED[/bold red]"
        )
        return (
            f"[bold]order:[/bold] {order}    [bold]heartbeat:[/bold] 500ms    "
            f"[bold]server:[/bold] {polling}    [dim]reaction_time = NOW - effective_updated_at  ·  "
            f"response_time = query latency[/dim]"
        )

    def _build_table(self) -> Table:
        m = self._metrics or {}

        table = Table(
            show_header=True,
            header_style="bold",
            title_style="bold",
            border_style="grey50",
            expand=True,
            pad_edge=False,
            padding=(0, 1),
        )
        table.add_column("Source", justify="left", min_width=28, no_wrap=False)
        table.add_column("response p50", justify="right")
        table.add_column("p99", justify="right")
        table.add_column("max", justify="right")
        table.add_column("freshness p50", justify="right")
        table.add_column("p99", justify="right")
        table.add_column("max", justify="right")
        table.add_column("qps", justify="right")
        table.add_column("samples", justify="right")

        for meta in SOURCE_META:
            stats = m.get(meta["key"]) or {}
            rt = stats.get("response_time", {}) or {}
            ft = stats.get("reaction_time", {}) or {}
            qps = stats.get("qps")
            samples = stats.get("sample_count")

            color = meta["color"]
            best = meta.get("best", False)
            label_text = Text()
            if best:
                label_text.append("★ ", style="bold yellow")
            label_text.append(meta["name"], style=f"bold {color}")
            label_text.append("\n")
            label_text.append(meta["tagline"], style="dim")

            row = [
                label_text,
                _fmt_ms(rt.get("median"), color, best),
                _fmt_ms(rt.get("p99"), color, best),
                _fmt_ms(rt.get("max"), color, best),
                _fmt_ms(ft.get("median"), color, best),
                _fmt_ms(ft.get("p99"), color, best),
                _fmt_ms(ft.get("max"), color, best),
                _fmt_qps(qps, color, best),
                _fmt_int(samples, color, best),
            ]
            table.add_row(*row)
        return table


_EXPLAINER = (
    "\n[dim italic]"
    "Materialize is 'best' because the response p99 is comparable to the batch cache "
    "(both serve from memory) WHILE freshness stays close to the PostgreSQL view's "
    "fresh-on-demand result. Batch is fast but stale; PG is fresh but slow; "
    "Materialize is fast AND fresh."
    "[/dim italic]"
)


def _fmt_ms(value: float | None, color: str, best: bool) -> Text:
    if value is None or value == 0:
        return Text("--", style="dim")
    style = f"bold {color}" if best else color
    s = f"{value:,.0f} ms" if value >= 100 else f"{value:.1f} ms"
    return Text(s, style=style)


def _fmt_qps(value: float | None, color: str, best: bool) -> Text:
    if value is None:
        return Text("--", style="dim")
    style = f"bold {color}" if best else color
    return Text(f"{float(value):.1f}", style=style)


def _fmt_int(value: int | None, color: str, best: bool) -> Text:
    if value is None:
        return Text("--", style="dim")
    style = f"{color}" if not best else f"bold {color}"
    return Text(f"{int(value):,}", style=style)
