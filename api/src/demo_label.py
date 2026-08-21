"""Read the resolved white-label config that `make label` produced.

The API is mostly label-agnostic -- its routes, models, and SQL are data-model
shape and identical for every label. This exists for the surfaces a customer
actually sees: the OpenAPI docs page, and reporting which label the running
stack was started with.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LABEL_FILE = "/labels/active.json"
REPO_FALLBACK = Path(__file__).resolve().parents[2] / "labels" / ".resolved" / "active.json"


@lru_cache(maxsize=1)
def load_label() -> dict[str, Any]:
    """The resolved label, or {} when it hasn't been generated.

    Never raises: the API must still boot and serve /health if the label file is
    missing, so callers fall back to neutral wording.
    """
    path = Path(os.environ.get("DEMO_LABEL_FILE") or DEFAULT_LABEL_FILE)
    if not path.exists():
        path = REPO_FALLBACK
    try:
        with path.open() as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def label_name() -> str:
    return load_label().get("label") or os.environ.get("DEMO_LABEL", "freshmart")


def brand_name() -> str:
    return load_label().get("brand", {}).get("name", "Live Context Graph")


def api_title() -> str:
    return f"{brand_name()} Digital Twin API"


def entity_title(kind: str, fallback: str) -> str:
    """Display name for an entity type, e.g. entity_title("courier", "Courier").

    Used only by the OpenAPI description. Falls back to the default label's word
    so the docs page still reads sensibly if the label file is missing.
    """
    words = load_label().get("vocabulary", {}).get(kind, {})
    return words.get("title") or fallback
