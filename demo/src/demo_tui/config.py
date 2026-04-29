"""Connection config for the demo TUI."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    agent_base_url: str
    mz_dsn: str
    api_base_url: str
    mz_views: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            agent_base_url=os.environ.get("DEMO_AGENT_URL", "http://localhost:8081"),
            mz_dsn=os.environ.get(
                "DEMO_MZ_DSN",
                "host=localhost port=6875 user=materialize password=materialize dbname=materialize",
            ),
            api_base_url=os.environ.get("DEMO_API_URL", "http://localhost:8080"),
            mz_views=(
                "inventory_items_with_dynamic_pricing_mv",
                "orders_with_lines_mv",
            ),
        )
