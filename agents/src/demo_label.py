"""Read the resolved white-label config that `make label` produced.

The agent's persona and system prompt are label-driven so the assistant speaks
the customer's vocabulary. Its tool set, graph structure, and the ontology it
reads are not -- those are data-model shape and identical for every label.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LABEL_FILE = "/labels/active.json"
# Fallback for running outside the container (tests, local CLI).
REPO_FALLBACK = Path(__file__).resolve().parents[2] / "labels" / ".resolved" / "active.json"


@lru_cache(maxsize=1)
def load_label() -> dict[str, Any]:
    path = Path(os.environ.get("DEMO_LABEL_FILE") or DEFAULT_LABEL_FILE)
    if not path.exists():
        path = REPO_FALLBACK
    try:
        with path.open() as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"resolved label not found at {path}. Run `make label` to generate it."
        ) from exc


def system_prompt() -> str:
    prompt = load_label()["agent"].get("system_prompt")
    if not prompt:
        raise RuntimeError(
            "the active label defines no agent.system_prompt; "
            "add one to labels/<name>.yaml"
        )
    return prompt


def persona() -> str:
    return load_label()["agent"]["persona"]

def empty_state() -> str:
    """One line telling the operator what this deployment can be asked about."""
    return load_label()["agent"].get("empty_state", "")


def default_store() -> str:
    return load_label()["agent"].get("default_store", "")


def stored_enum_value(predicate: str, value: str) -> str:
    """Map a display word back to the fixed enum value the SQL joins on.

    The label renames what a status READS as -- DELIVERED shows as "Settled" for
    an insurance carrier -- but the stored value is data-model shape. A user who
    says "mark it settled" must not end up writing SETTLED, which no view keys
    on, so the case would silently drop out of every status filter.

    Unrecognised values pass through untouched: a predicate with no enum, or a
    genuinely new value, is the caller's business. Matching is case-insensitive
    and ignores spacing, so "on case", "On Case" and "ON_CASE" all resolve.
    """
    enums = load_label().get("enums", {})
    # The field and its enum usually share a name; these are the ones that don't.
    by_field = {
        "store_zone": "zone",
        "task_status": "task_status",
        "delivery_task_status": "task_status",
        "health_status": "capacity_health",
    }
    name = by_field.get(predicate, predicate)
    mapping = enums.get(name)
    if not mapping:
        return value

    def norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    target = norm(value)
    # Already a stored value.
    for stored in mapping:
        if norm(stored) == target:
            return stored
    # A display word for one.
    for stored, shown in mapping.items():
        if norm(shown) == target:
            return stored
    return value


def order_prefix() -> str:
    """Order-number prefix, e.g. 'FM-'. Used when the agent mints an order."""
    return load_label()["vocabulary"]["order"]["id_prefix"]
