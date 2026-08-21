"""Read the resolved white-label config that `make label` produced.

The load generator only needs the order-number prefix so the traffic it creates
matches the seeded data. Everything else it uses -- statuses, transitions,
predicates -- is data-model shape and identical for every label.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LABEL_FILE = "/labels/active.json"
REPO_FALLBACK = Path(__file__).resolve().parents[2] / "labels" / ".resolved" / "active.json"
FALLBACK_PREFIX = "FM-"


@lru_cache(maxsize=1)
def load_label() -> dict[str, Any] | None:
    path = Path(os.environ.get("DEMO_LABEL_FILE") or DEFAULT_LABEL_FILE)
    if not path.exists():
        path = REPO_FALLBACK
    try:
        with path.open() as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        # The generator is often run standalone (`make load-gen`) against an
        # already-seeded stack, so fall back rather than refusing to start.
        return None


@lru_cache(maxsize=1)
def locations() -> list[tuple[str, str, list[str]]]:
    """(code, name, streets) per zone, from the active label.

    Zone CODES are join keys in the pricing SQL and never change; the display
    names and street pools are label-driven, so generated addresses land in the
    label's own geography instead of the default vertical's.
    """
    label = load_label()
    if not label:
        return []
    return [
        (loc["code"], loc["name"], list(loc.get("streets") or [loc["name"]]))
        for loc in (label.get("seed", {}).get("locations") or [])
    ]


def address_state() -> str:
    """State/region code used for generated postal codes."""
    label = load_label()
    return (label or {}).get("seed", {}).get("address_state", "NY")


def order_prefix() -> str:
    label = load_label()
    if not label:
        return FALLBACK_PREFIX
    return label.get("vocabulary", {}).get("order", {}).get("id_prefix", FALLBACK_PREFIX)
