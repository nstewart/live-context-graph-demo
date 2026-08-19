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


def order_prefix() -> str:
    """Order-number prefix, e.g. 'FM-'. Used when the agent mints an order."""
    return load_label()["vocabulary"]["order"]["id_prefix"]
