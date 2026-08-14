#!/usr/bin/env python3
"""Read the resolved white-label config that `make label` produced.

The seeder uses this for the product catalog, store naming, locations, and the
order-number prefix. Everything structural -- predicates, subject prefixes, zone
CODES, entity counts -- stays fixed regardless of label, so the demo behaves
identically whichever label is loaded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_LABEL_FILE = "/labels/active.json"
# Fallback for running on the host (seed_demo.sh) rather than in the container.
REPO_FALLBACK = Path(__file__).resolve().parent.parent.parent / "labels" / ".resolved" / "active.json"


class LabelUnavailable(RuntimeError):
    """The resolved label file is missing or malformed."""


def label_path() -> Path:
    explicit = os.environ.get("DEMO_LABEL_FILE")
    if explicit:
        return Path(explicit)
    default = Path(DEFAULT_LABEL_FILE)
    return default if default.exists() else REPO_FALLBACK


def load_label() -> dict[str, Any]:
    path = label_path()
    try:
        with path.open() as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise LabelUnavailable(
            f"resolved label not found at {path}.\n"
            "Run `make label` (or `make label LABEL=<name>`) to generate it."
        ) from exc
    except json.JSONDecodeError as exc:
        raise LabelUnavailable(f"{path} is not valid JSON: {exc}") from exc


def expand_catalog(
    items: list[list[Any]], expand_to: int, variant_suffixes: list[str]
) -> list[tuple[str, str, float, int, bool]]:
    """Grow an authored catalog to `expand_to` rows by adding variants.

    Keeping the row count identical across labels matters: it holds the search
    index size, kNN recall, and the seeded entity counts steady, so a demo
    behaves the same no matter which label is loaded.

    Variants are derived deterministically from the suffix index (bigger pack =
    pricier and heavier) rather than randomly, so the catalog is reproducible
    regardless of when this runs.
    """
    base = [(str(n), str(c), float(p), int(w), bool(x)) for n, c, p, w, x in items]
    if expand_to <= len(base):
        return base[:expand_to]

    if not variant_suffixes:
        raise LabelUnavailable(
            f"catalog has {len(base)} items but expand_to is {expand_to}, and no "
            "seed.catalog.variant_suffixes are defined.\n"
            "Either author more items or add variant suffixes to the label."
        )

    out = list(base)
    round_index = 0
    while len(out) < expand_to:
        suffix = variant_suffixes[round_index % len(variant_suffixes)]
        step = round_index + 1
        for name, category, price, weight, perishable in base:
            if len(out) >= expand_to:
                break
            out.append(
                (
                    f"{name} {suffix}",
                    category,
                    round(price * (1 + 0.15 * step), 2),
                    int(weight * (1 + 0.25 * step)),
                    perishable,
                )
            )
        round_index += 1
    return out


def catalog(label: dict[str, Any]) -> list[tuple[str, str, float, int, bool]]:
    """The label's product catalog, expanded to its configured size."""
    cat = label["seed"]["catalog"]
    return expand_catalog(
        cat["items"], int(cat["expand_to"]), cat.get("variant_suffixes", [])
    )


def locations(label: dict[str, Any]) -> list[tuple[str, str, list[str]]]:
    """(code, name, streets) per zone.

    Zone CODES are join keys in the dynamic-pricing SQL and must not change; only
    the display names and street lists are label-driven.
    """
    return [
        (loc["code"], loc["name"], list(loc.get("streets") or [loc["name"]]))
        for loc in label["seed"]["locations"]
    ]


def order_prefix(label: dict[str, Any]) -> str:
    return label["vocabulary"]["order"]["id_prefix"]


def store_name(label: dict[str, Any], zone_name: str, n: int) -> str:
    return label["seed"]["store_name_template"].format(zone_name=zone_name, n=n)


def address_state(label: dict[str, Any]) -> str:
    return label["seed"].get("address_state", "NY")
