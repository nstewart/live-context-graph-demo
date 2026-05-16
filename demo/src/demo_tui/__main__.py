"""CLI entry point: `uv run -m demo_tui [--mode cqrs|freshness]`."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="demo_tui",
        description=(
            "FreshMart terminal demos. --mode cqrs (default) is the live CQRS "
            "dashboard; --mode freshness compares PostgreSQL view / batch cache / "
            "Materialize under load."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["cqrs", "freshness"],
        default="cqrs",
        help="Which demo to launch (default: cqrs)",
    )
    parser.add_argument(
        "--scenario",
        choices=["stockout-reroute"],
        help="cqrs only: pre-staged scenario (Phase 5).",
    )
    parser.add_argument(
        "--order",
        default=None,
        help="freshness only: order_id (e.g. 'order:FM-XXX'); auto-picks first DELIVERED if omitted.",
    )
    args = parser.parse_args()

    if args.mode == "cqrs":
        from .app import DemoApp
        from .config import Config

        DemoApp(config=Config.from_env(), scenario=args.scenario).run(mouse=False)
    else:
        from .config import Config
        from .freshness_app import FreshnessApp

        FreshnessApp(config=Config.from_env(), order_id=args.order).run(mouse=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
