#!/usr/bin/env python3
"""Leak detector: assert a non-default label carries no grocery vocabulary.

Careful reading does not scale across ~35 files of copy. This does the check
that actually matters -- resolve every label and grep the human-facing strings
for FreshMart's vertical.

Structural identifiers are exempt because they are deliberately fixed: route
paths (/orders), subject prefixes (order:, store:, courier:), enum KEYS, tool
and field names inside the agent prompt. Only text a customer reads is checked.

    python3 tools/check_label_leaks.py            # every non-default label
    python3 tools/check_label_leaks.py --label life-insurance
"""

from __future__ import annotations

import argparse
import re
import sys

from resolve_label import BASE_LABEL, LabelError, available_labels, resolve

# Vocabulary that belongs to the default label's vertical and must not survive
# into another label's user-facing copy.
GROCERY_TERMS = [
    "freshmart", "grocery", "perishable", "refrigerat", "cold chain",
    "courier", "delivery", "deliver", "shopping cart",
    "brooklyn", "manhattan", "queens", "bronx", "staten island",
    "milk", "dairy", "produce", "organic", "snack", "seafood", "poultry",
    "storefront", "aisle", "basket",
    # Entity nouns. These are the likelier miss -- a label that renames the
    # headline copy but leaves "No triples found for this order" behind. Any
    # label is expected to give each of these its own display word.
    "order", "store", "product", "inventory", "customer",
]

# Phrases where a flagged word is genuinely generic rather than domain
# vocabulary, stripped before the scan.
ALLOWED_PHRASES = [
    "vector store",     # the vector database, not a retail store
    "data product",     # architecture term used in the reference-architecture copy
    "data products",
]

# Paths whose values are structural, not copy.
EXEMPT_PREFIXES = (
    ".label",
    ".nav[",              # .path is a route; .label is checked separately below
    ".aliases.",          # left side is the real identifier by definition
    ".enums.",            # keys are fixed; values ARE checked (see below)
    ".seed.catalog.items",  # authored per label, checked for category sanity only
    ".seed.locations",      # 'code' is a fixed join key
    ".brand.favicon",
)

# Identifier-shaped tokens that legitimately appear inside prose (tool names,
# field names, subject prefixes). Stripped before the term scan.
IDENTIFIER_RE = re.compile(
    r"(\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b)"     # snake_case: search_orders, live_price
    r"|(\b(?:order|store|courier|customer|product|inventory|task|orderline):[A-Za-z0-9_\-]+)"  # subject ids
    r"|(/[a-z\-]+)"                             # route paths
)


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def exempt(path: str) -> bool:
    if path.startswith(".nav[") and path.endswith(".path"):
        return True
    return any(path.startswith(p) for p in EXEMPT_PREFIXES if not p.startswith(".enums"))


def scan(label_name: str) -> list[tuple[str, str, str]]:
    resolved = resolve(label_name)
    findings: list[tuple[str, str, str]] = []
    # Enum VALUES (CREATED, OUT_FOR_DELIVERY, ...) are fixed by the SQL and appear
    # verbatim in prose and sample values. They are structure, not copy.
    enum_values = {v for mapping in resolved.get("enums", {}).values() for v in mapping}
    enum_re = (
        re.compile(
            "|".join(
                rf"\b{re.escape(v)}\b"
                for v in sorted(enum_values, key=len, reverse=True)
            )
        )
        if enum_values
        else None
    )
    for path, value in walk(resolved):
        if exempt(path):
            continue
        # Identifiers first: stripping enum values earlier would break subject
        # ids like "store:BK-01" into a bare "store" and flag it.
        prose = IDENTIFIER_RE.sub(" ", value)
        if enum_re:
            prose = enum_re.sub(" ", prose)
        prose = prose.lower()
        for phrase in ALLOWED_PHRASES:
            prose = prose.replace(phrase, " ")
        for term in GROCERY_TERMS:
            if re.search(rf"\b{re.escape(term)}", prose):
                findings.append((path, term, value.strip()[:120]))
                break
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", help="check one label (default: all non-default)")
    args = parser.parse_args()

    names = [args.label] if args.label else [
        n for n in available_labels() if n != BASE_LABEL
    ]
    if not names:
        print(f"only '{BASE_LABEL}' exists; nothing to check.")
        print("Authoring a second label is what proves the abstraction holds.")
        return 0

    failed = False
    for name in names:
        try:
            findings = scan(name)
        except LabelError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if findings:
            failed = True
            print(f"\nFAIL {name}: {len(findings)} leaked string(s)")
            for path, term, value in findings:
                print(f"  {path}\n      matched '{term}': {value}")
        else:
            print(f"OK   {name}: no default-vertical vocabulary in user-facing copy")

    if failed:
        print(
            "\nEach finding is a key the label inherited from "
            f"{BASE_LABEL}.yaml but should override.",
            file=sys.stderr,
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
