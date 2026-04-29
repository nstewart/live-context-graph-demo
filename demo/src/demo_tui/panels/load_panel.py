"""Bottom-left: rolling order pulse."""

from __future__ import annotations

from textual.widgets import Static

from ..feeds.types import LoadTick

SPARK_GLYPHS = " ▁▂▃▄▅▆▇█"


class LoadPanel(Static):
    DEFAULT_CSS = """
    LoadPanel {
        border: round $accent;
        padding: 0 1;
        height: 100%;
        content-align: left top;
    }
    """

    BORDER_TITLE = "LOAD"
    BORDER_SUBTITLE = "rolling 60s"

    def on_mount(self) -> None:
        self.border_title = self.BORDER_TITLE
        self.border_subtitle = self.BORDER_SUBTITLE
        self.update("[dim](waiting for orders...)[/dim]")

    def on_load_tick(self, tick: LoadTick) -> None:
        spark = _sparkline(tick.sparkline_buckets)
        per_min = tick.orders_last_60s  # window is 60s, so count == orders/min
        zone_lines = _format_zones(tick.by_zone)
        body = (
            f"orders/min  [bold green]{per_min:>3}[/bold green]\n"
            f"  {spark}\n"
            f"{zone_lines}"
        )
        self.update(body)


def _sparkline(buckets: list[int]) -> str:
    if not buckets:
        return ""
    peak = max(buckets) or 1
    out = []
    for v in buckets:
        idx = min(len(SPARK_GLYPHS) - 1, int((v / peak) * (len(SPARK_GLYPHS) - 1)))
        out.append(SPARK_GLYPHS[idx])
    return "".join(out)


def _format_zones(by_zone: dict[str, int]) -> str:
    if not by_zone:
        return "[dim](no recent orders by zone)[/dim]"
    peak = max(by_zone.values()) or 1
    lines = []
    for zone in sorted(by_zone.keys()):
        n = by_zone[zone]
        bar_len = int((n / peak) * 12)
        bar = "#" * bar_len + "." * (12 - bar_len)
        lines.append(f"  {zone:<3} {bar} {n:>3}")
    return "\n".join(lines)
