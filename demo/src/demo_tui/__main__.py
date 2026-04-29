"""CLI entry point: `uv run -m demo_tui [--scenario NAME]`."""

from __future__ import annotations

import argparse
import sys

from .app import DemoApp
from .config import Config


def main() -> int:
    parser = argparse.ArgumentParser(prog="demo_tui", description="FreshMart live CQRS dashboard")
    parser.add_argument(
        "--scenario",
        choices=["stockout-reroute"],
        help="Run a pre-staged scenario (Phase 5 wires this; ignored in Phase 1).",
    )
    args = parser.parse_args()

    DemoApp(config=Config.from_env(), scenario=args.scenario).run(mouse=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
