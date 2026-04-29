"""Textual app shell: 3-over-2 grid + live-feed workers."""

from __future__ import annotations

import logging
import os
import uuid

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer


def _configure_logging() -> str:
    """Send feed warnings/info to a file so we can tail-debug a running TUI."""
    path = os.environ.get("DEMO_TUI_LOG", "/tmp/demo-tui.log")
    handler = logging.FileHandler(path, mode="a")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger("demo_tui")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    root.info("---- demo_tui log opened ----")
    return path

from .config import Config
from .feeds.agent_stream import stream_prompt
from .feeds.load_pulse import LoadPulse, emit_ticks
from .feeds.mz_subscribe import DEFAULT_VIEWS, subscribe_view
from .feeds.reaction_time import ReactionMonitor
from .feeds.types import AgentEvent, LoadTick, MzRow, now_mono
from .panels.agent_panel import AgentPanel
from .panels.load_panel import LoadPanel
from .panels.mz_panel import MzPanel
from .panels.timing_panel import TimingPanel
from .timing import WriteTracker
from .widgets.input_pane import InputPane


class DemoApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "FreshMart Live CQRS Dashboard"
    SUB_TITLE = "you write -> agent reasons -> Materialize reflects"

    BINDINGS = [
        Binding("f1", "focus_input", "input", show=True, priority=True),
        Binding("f2", "focus_agent", "agent", show=True, priority=True),
        Binding("f3", "focus_mz", "materialize", show=True, priority=True),
        Binding("escape", "focus_input", "input", show=False, priority=True),
        Binding("ctrl+shift+c", "yank_panels", "copy panels", show=True),
        Binding("ctrl+c", "quit", "quit", show=True, priority=True),
    ]

    def __init__(self, config: Config | None = None, scenario: str | None = None) -> None:
        super().__init__()
        self.config = config or Config.from_env()
        self.scenario = scenario
        self.pulse = LoadPulse()
        self.tracker = WriteTracker()
        self.reaction = ReactionMonitor(self.config.mz_dsn)
        self.log_path = _configure_logging()
        self._chat_thread_id: str = f"tui-{uuid.uuid4().hex[:8]}"

    def compose(self) -> ComposeResult:
        with Horizontal(id="top_row"):
            yield InputPane(id="input_pane")
            yield AgentPanel(id="agent_panel")
            yield MzPanel(id="mz_panel")
        with Horizontal(id="bottom_row"):
            yield LoadPanel(id="load_panel")
            yield TimingPanel(id="timing_panel")
        yield Footer()

    def on_mount(self) -> None:
        # One worker per Materialize view + one for the load pulse aggregator
        # + one for the reaction-time point-query loop.
        for spec in DEFAULT_VIEWS:
            self.run_worker(
                _bind(self._mz_worker, spec),
                name=f"mz:{spec.view}",
                exclusive=False,
                exit_on_error=False,
            )
        self.run_worker(
            self._pulse_worker, name="pulse", exclusive=False, exit_on_error=False
        )
        self.run_worker(
            self._reaction_query_worker,
            name="reaction_query",
            exclusive=False,
            exit_on_error=False,
        )

    # ----- workers -----

    async def _mz_worker(self, spec) -> None:
        await subscribe_view(self.config.mz_dsn, spec, self._on_mz_row)

    async def _pulse_worker(self) -> None:
        await emit_ticks(self.pulse, self._on_load_tick, interval_sec=1.0)

    async def _reaction_query_worker(self) -> None:
        await self.reaction.run_query_loop()

    async def _agent_worker(self, prompt: str) -> None:
        await stream_prompt(
            self.config.agent_base_url,
            prompt,
            thread_id=self._chat_thread_id,
            emit=self._on_agent_event,
        )

    # ----- emit callbacks -----

    def _on_mz_row(self, row: MzRow) -> None:
        self.pulse.ingest(row)
        self.reaction.ingest_row(row)
        annotation = self.tracker.on_mz_row(row)
        try:
            self.query_one(MzPanel).on_mz_row(row, annotation=annotation)
        except Exception:  # widget may be unmounted during shutdown
            pass

    def _on_load_tick(self, tick: LoadTick) -> None:
        try:
            self.query_one(LoadPanel).on_load_tick(tick)
        except Exception:
            pass
        # Same 1Hz tick services housekeeping + the timing panel refresh.
        self.tracker.expire_old()
        try:
            tp = self.query_one(TimingPanel)
            tp.set_record(self.tracker.latest_closed(), open_count=self.tracker.open_count())
            tp.set_reaction_stats(self.reaction.stats())
        except Exception:
            pass

    def _on_agent_event(self, evt: AgentEvent) -> None:
        climax = self.tracker.on_agent_event(evt)
        try:
            self.query_one(AgentPanel).on_agent_event(evt, climax=climax)
        except Exception:
            pass
        if climax is not None:
            try:
                self.query_one(TimingPanel).set_record(
                    self.tracker.latest_closed(), open_count=self.tracker.open_count()
                )
            except Exception:
                pass

    # ----- actions -----

    def action_focus_input(self) -> None:
        from .widgets.input_pane import PromptTextArea

        try:
            self.query_one(PromptTextArea).focus()
        except Exception:
            pass

    def action_focus_agent(self) -> None:
        try:
            self.query_one(AgentPanel).focus()
        except Exception:
            pass

    def action_focus_mz(self) -> None:
        try:
            self.query_one(MzPanel).focus()
        except Exception:
            pass

    def action_yank_panels(self) -> None:
        agent = self.query_one(AgentPanel).to_plaintext()
        mz = self.query_one(MzPanel).to_plaintext()
        bundle = (
            "===== AGENT =====\n" + agent + "\n\n"
            "===== MATERIALIZE =====\n" + mz + "\n"
        )
        self.copy_to_clipboard(bundle)
        self.notify("copied agent + materialize panes to clipboard", timeout=2)

    def on_input_pane_submitted(self, message: InputPane.Submitted) -> None:
        self.tracker.notify_submit(now_mono())
        self.query_one(AgentPanel).show_submitted(message.text)
        self.run_worker(
            _bind(self._agent_worker, message.text),
            name="agent_call",
            exclusive=False,
            exit_on_error=False,
        )


def _bind(coro_fn, *args):
    """Wrap a bound async method so Textual calls it lazily."""

    async def _start():
        return await coro_fn(*args)

    return _start


def run(scenario: str | None = None) -> None:
    # mouse=False disables Textual's mouse capture so the terminal handles
    # selection natively -- click-and-drag works for copy in iTerm/Terminal.app
    # without needing Option as a modifier. This app is keyboard-driven anyway.
    DemoApp(scenario=scenario).run(mouse=False)


if __name__ == "__main__":
    run()
