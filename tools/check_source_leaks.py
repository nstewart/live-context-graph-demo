#!/usr/bin/env python3
"""Leak detector #2: assert the SOURCE carries no hardcoded default-label wording.

check_label_leaks.py proves a LABEL's copy is free of the default vertical.
This proves the opposite direction, which is how white-labeling actually
regressed here: labels/ authored "case manager" correctly, but ~140 component
strings still said "Courier", so 9 of 10 vocabulary entries and 7 of 8 enum maps
were never read by the UI at all.

Four checks:

  brand       the default brand name or order-number prefix, typed into code
  vocabulary  the default vertical's words in a user-visible string
  raw-fields  a database field rendered without its label helper
  dead-keys   a label key the UI could read but never does

`vocabulary` and `raw-fields` are the two halves of the same problem, and both
are needed. `vocabulary` reads string literals, so it caught the literal
"Couriers & Schedule" but was blind to `{triple.predicate}` -- a binding that
renders whatever Postgres holds. That blind spot is why the "Agent Writes and
Memories" card still showed raw grocery predicates after every literal on it had
been fixed.

Run standalone, or via `make label-lint`:

    python3 tools/check_source_leaks.py
    python3 tools/check_source_leaks.py --only vocabulary
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOLVED = REPO / "labels" / ".resolved" / "active.json"

# Customer-visible surfaces only. Deliberately NOT scanned: Python internals in
# api/, load-generator/ and db/scripts, whose module docstrings, class names
# (FreshMartAPIClient) and log lines carry the default brand without a customer
# ever seeing it. Widen this list rather than sprinkling exemptions.
SCAN_PATHSPEC = ["web/src", "agents/src", "api/src/main.py", "api/src/demo_label.py"]
SKIP_RE = re.compile(r"\.test\.(ts|tsx)$|(^|/)tests?/|web/src/generated/|web/src/test/")

# An inline escape hatch, for a string that must stay literal. Put it on the
# offending line or the line above, and say why:
#     <div>GET orders/_search</div>  {/* label-lint-ok: real index name */}
PRAGMA = "label-lint-ok"

# ---------------------------------------------------------------------------
# check 1: the brand itself
# ---------------------------------------------------------------------------

BRAND_PATTERNS = [
    (re.compile(r"freshmart", re.I), "brand name"),
    (re.compile(r"""["'`f]FM-"""), "order-number prefix"),
]

# Structural identifiers that are deliberately NOT label-driven, because a field
# engineer's mental model depends on them being stable: the /freshmart API router
# prefix, the Postgres database name, the Docker network name.
STRUCTURAL_RE = re.compile(
    r"/freshmart/|freshmartApi|freshmart-network|pg_database|PG_DATABASE"
    r'|"freshmart"|freshmart_|_freshmart'
)

# ---------------------------------------------------------------------------
# check 2: the default vertical's vocabulary in a visible string
# ---------------------------------------------------------------------------

# Entity nouns. Every one already has a `vocabulary`, `enums` or `copy` key, so
# reading that key is always the fix -- never an exemption.
#
# Scoped to web/src ONLY. In agents/src the tool names and parameters ARE
# `create_order`, `list_stores`, `search_inventory` and `store_id` -- fixed shape
# by the same rule that fixes predicate and view names -- so a docstring
# describing create_order has to say "order" to be coherent. What the assistant
# actually says to a customer is governed by agent.system_prompt, which every
# label authors in full.
ENTITY_TERMS = re.compile(
    r"\b("
    r"orders?|stores?|products?|inventor(?:y|ies)|customers?|couriers?"
    r"|deliver(?:y|ies|ed|ing)|line items?|zones?"
    r")\b",
    re.I,
)

# The default vertical's own words. These are never structural anywhere, so they
# are scanned across every surface including the agent's tool docstrings.
VERTICAL_TERMS = re.compile(
    r"\b("
    r"grocer(?:y|ies)|perishables?|cold chain|refrigerat\w*|storefronts?|aisles?"
    r"|shopping cart|milk|dairy|poultry|seafood|vegetables?"
    r"|brooklyn|manhattan|queens|bronx|staten island"
    r")\b",
    re.I,
)

# Phrases where a flagged word is genuinely generic rather than vertical
# vocabulary. Stripped before the scan.
ALLOWED_PHRASES = [
    "vector store",  # the vector database, not a retail store
    "data product",  # architecture term in the reference-architecture copy
    "data products",
    "in order to",
    "order by",  # SQL
    "sort order",
    "z-order",
]

# Identifier-shaped tokens legitimately inside prose: field names, view names,
# tool names, subject prefixes. Stripped before the scan.
IDENTIFIER_RE = re.compile(
    r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"  # snake_case: order_status, live_price
    r"|\b(?:order|store|product|inventory|customer|courier|task|orderline):"  # subject prefixes
    r"|\b[a-z]+[A-Z][a-zA-Z]*\b"  # camelCase: orderId, storeName
)


def visible_strings(path: Path, text: str) -> list[tuple[int, str]]:
    """Every string a user could read, as (line number, text).

    JSX text nodes plus quoted literals. Comments are dropped -- they are
    developer-facing -- EXCEPT docstrings under agents/src/tools, which LangChain
    ships to the model as tool descriptions and a customer therefore hears.
    """
    out: list[tuple[int, str]] = []
    llm_facing = "agents/src/tools" in path.as_posix()
    in_block = False  # /* ... */
    in_docstring = False  # triple-quoted
    triple = re.compile(r'"""' + "|'''")
    for lineno, raw in enumerate(text.split("\n"), 1):
        line = raw
        stripped = line.strip()

        if path.suffix == ".py":
            # Docstrings under agents/src/tools become the tool description
            # LangChain ships to the model, so they are read. Docstrings and
            # comments elsewhere are developer-facing and skipped.
            fences = len(triple.findall(stripped))
            was_inside = in_docstring
            if fences % 2 == 1:
                in_docstring = not in_docstring
            if was_inside or fences:
                if llm_facing and stripped:
                    out.append((lineno, triple.sub("", stripped).strip()))
                continue
            if stripped.startswith("#"):
                continue

        # /* ... */ and JSX {/* ... */} blocks
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                continue
        line = re.sub(r"/\*.*?\*/", " ", line)
        if "/*" in line:
            line = line.split("/*", 1)[0]
            in_block = True
        line = re.sub(r"//.*$", "", line)
        stripped = line.strip()
        if stripped.startswith("*"):  # continuation of a /** ... */ block
            continue

        candidates: list[str] = []
        candidates += re.findall(r">([^<>{}]{3,})<", line)
        candidates += [
            m.group(1) or m.group(2) or m.group(3)
            for m in re.finditer(r"'([^'\\]{3,})'|\"([^\"\\]{3,})\"|`([^`\\$]{3,})`", line)
        ]
        for c in candidates:
            c = c.strip()
            if not c or c.startswith(("/", "http")):
                continue
            out.append((lineno, c))
    return out


def has_pragma(lines: list[str], lineno: int) -> bool:
    """True when the offending line, or the one above it, carries the pragma."""
    for i in (lineno - 1, lineno - 2):
        if 0 <= i < len(lines) and PRAGMA in lines[i]:
            return True
    return False


def scan_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", *SCAN_PATHSPEC],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [
        REPO / f
        for f in listed
        if f.endswith((".ts", ".tsx", ".py")) and not SKIP_RE.search(f)
    ]


def check_brand(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        text = path.read_text()
        lines = text.split("\n")
        for lineno, raw in enumerate(lines, 1):
            if STRUCTURAL_RE.search(raw) or has_pragma(lines, lineno):
                continue
            visible = {s for ln, s in visible_strings(path, text) if ln == lineno}
            for pattern, what in BRAND_PATTERNS:
                if any(pattern.search(s) for s in visible):
                    rel = path.relative_to(REPO)
                    problems.append(f"{rel}:{lineno}: {what}: {raw.strip()[:100]}")
    return problems


def check_vocabulary(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        rel = path.relative_to(REPO)
        # Entity nouns are only a leak where a display helper exists for them.
        in_ui = rel.as_posix().startswith("web/src")
        text = path.read_text()
        lines = text.split("\n")
        for lineno, s in visible_strings(path, text):
            if has_pragma(lines, lineno):
                continue
            probe = s
            for phrase in ALLOWED_PHRASES:
                probe = re.sub(re.escape(phrase), " ", probe, flags=re.I)
            probe = IDENTIFIER_RE.sub(" ", probe)
            # Prose has spaces. A bare token is an identifier or a fixed enum
            # value, both of which are data-model shape.
            if " " not in probe.strip():
                continue
            hit = VERTICAL_TERMS.search(probe) or (in_ui and ENTITY_TERMS.search(probe))
            if hit:
                problems.append(f"{rel}:{lineno}: {hit.group(0)!r} in {s[:80]!r}")
    return problems


def check_dead_keys() -> list[str]:
    """A label key the UI could read, that no component reads."""
    if not RESOLVED.exists():
        return ["labels/.resolved/active.json missing -- run `make label` first"]
    label = json.loads(RESOLVED.read_text())
    blob = "\n".join(
        p.read_text()
        for p in scan_files()
        if p.suffix in {".ts", ".tsx"}
    )
    dead = []

    def bundle_read(kind: str, key: str) -> bool:
        k = re.escape(key)
        return bool(
            re.search(rf"{kind}\(\s*['\"]{k}['\"]", blob)
            or re.search(rf"{kind}Text\(\s*['\"]{k}['\"]", blob)
        )

    for key in label.get("pages", {}):
        if not bundle_read("page", key):
            dead.append(f"pages.{key}")
    for key in label.get("copy", {}):
        if not bundle_read("copy", key):
            dead.append(f"copy.{key}")
    for key in label.get("placeholders", {}):
        if not re.search(rf"placeholder\(\s*['\"]{re.escape(key)}['\"]", blob):
            dead.append(f"placeholders.{key}")
    for key in label.get("enums", {}):
        if not re.search(rf"enum(?:Label|Options)\(\s*['\"]{re.escape(key)}['\"]", blob):
            dead.append(f"enums.{key}")
    for key in label.get("vocabulary", {}):
        if not re.search(
            rf"(?:entity|Entity|Entities|words)\(\s*['\"]{re.escape(key)}['\"]", blob
        ):
            dead.append(f"vocabulary.{key}")
    return dead


# ---------------------------------------------------------------------------
# check 4: a raw database field rendered without its label helper
# ---------------------------------------------------------------------------
#
# The `vocabulary` check reads string literals, so it is blind to
# `{triple.predicate}` -- a binding that renders whatever Postgres holds. That
# blindness is exactly how "Agent Writes and Memories" kept showing raw
# predicates after every literal on the screen had been fixed.

# field name -> the helper its rendered value must pass through
ALIASABLE_FIELDS = {
    "predicate": "aliasPredicate",
    "prop_name": "aliasPredicate",
    "class_name": "aliasClass",
    "domain_class_name": "aliasClass",
    "range_class_name": "aliasClass",
    "order_status": "enumLabel('order_status', …)",
    "courier_status": "enumLabel('courier_status', …)",
    "task_status": "enumLabel('task_status', …)",
    "delivery_task_status": "enumLabel('task_status', …)",
    "vehicle_type": "enumLabel('vehicle_type', …)",
    "store_status": "enumLabel('store_status', …)",
    "store_zone": "enumLabel('zone', …)",
    "health_status": "enumLabel('capacity_health', …)",
    "recommended_action": "enumLabel('recommended_action', …)",
    "availability_status": "enumLabel('availability_status', …)",
}

LABEL_HELPERS = (
    "enumLabel",
    "enumOptions",
    "displayValue",  # takes the field name as an argument, not as display text
    "enumForField",
    "aliasPredicate",
    "aliasClass",
    "aliasColumn",
    "aliasView",
    "entity",
    "Entity",
    "Entities",
    "words",
)

# JSX attributes that are NOT display: the form's stored value, a React key, a
# CSS class, and props whose component aliases internally. Everything else --
# children, title, placeholder, aria-label -- is read by a human.
NON_DISPLAY_ATTR = re.compile(
    r"\b(?:value|key|className|status|data-[\w-]+|htmlFor|id|name|type)="
    r"(?:\{`[^`]*`\}|\{[^{}]*\})"  # a template literal, or a plain expression
)

# `${...}` is a template-literal interpolation, not a JSX child: React keys,
# Set dedup keys and URL building all live there. JSX children are a bare `{`.
INTERPOLATION = "$"


def check_raw_fields(files: list[Path]) -> list[str]:
    problems = []
    for path in files:
        if path.suffix != ".tsx":
            continue
        rel = path.relative_to(REPO)
        lines = path.read_text().split("\n")
        for lineno, raw in enumerate(lines, 1):
            if has_pragma(lines, lineno):
                continue
            line = re.sub(r"//.*$", "", raw)
            # An object literal is a write payload on the wire, not a render.
            if re.search(r"\b(?:predicate|object_value|subject_id)\s*:", line):
                continue
            # Drop attributes that are not display, so only children and the
            # human-readable attributes are left to inspect.
            display = NON_DISPLAY_ATTR.sub(" ", line)
            for m in re.finditer(r"\{([^{}]*?)\}", display):
                expr = m.group(1)
                if any(h + "(" in expr for h in LABEL_HELPERS):
                    continue
                # `healthStatusColors[metrics.health_status]` and
                # `getStatusClasses(x.order_status)` map a raw value to a CSS
                # class -- they must keep the real value.
                if re.search(r"\w\[[^\]]*\]|\bget\w+\(", expr):
                    continue
                if m.start() > 0 and display[m.start() - 1] == INTERPOLATION:
                    continue
                for field, helper in ALIASABLE_FIELDS.items():
                    if re.search(rf"\.{field}\b", expr):
                        problems.append(
                            f"{rel}:{lineno}: {{{expr.strip()[:52]}}} renders raw "
                            f"{field} -- needs {helper}"
                        )
                        break
    return problems


CHECKS = {
    "brand": ("no hardcoded brand name or order prefix", check_brand, True),
    "vocabulary": ("no default-vertical wording in visible strings", check_vocabulary, True),
    "raw-fields": ("no database field rendered without its label helper", check_raw_fields, True),
    "dead-keys": ("every readable label key is read", check_dead_keys, False),
}

HINTS = {
    "brand": "Read it from the active label: `import { brand } from '../label'`.",
    "vocabulary": (
        "Read the word from the active label instead:\n"
        "  entity('courier', 'many') / Entity('store') / Entities('order')\n"
        "  enumLabel('order_status', v) / words('perishable').tooltip\n"
        "  page('metrics').title / copy('cart').heading / placeholder('order_search')\n"
        f"If the literal is genuinely required, add a `{PRAGMA}: <why>` comment."
    ),
    "raw-fields": (
        "This renders whatever the database holds. Wrap it in the helper so the\n"
        "screen reads the label's word:\n"
        "  {aliasPredicate(triple.predicate)}\n"
        "  {enumLabel('order_status', order.order_status)}\n"
        f"If the raw value is required (a CSS lookup, a form value, a write\n"
        f"payload), add a `{PRAGMA}: <why>` comment."
    ),
    "dead-keys": (
        "The label authors this text but nothing renders it, so the screen is\n"
        "still showing a literal. Wire the key up, or delete it from labels/*.yaml."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=sorted(CHECKS), help="run a single check")
    args = ap.parse_args()

    files = scan_files()
    if not files:
        print("FAIL matched no source files -- the pathspec is wrong.", file=sys.stderr)
        print("     Refusing to report a vacuous pass.", file=sys.stderr)
        return 1
    print(f"source-leaks: scanning {len(files)} files")

    status = 0
    for name, (label_text, fn, takes_files) in CHECKS.items():
        if args.only and name != args.only:
            continue
        problems = fn(files) if takes_files else fn()
        if problems:
            status = 1
            print(f"FAIL {name}: {len(problems)} problem(s)")
            for p in problems:
                print(f"  {p}")
            print()
            print("  " + HINTS[name].replace("\n", "\n  "))
            print()
        else:
            print(f"OK   {name}: {label_text}")

    if status:
        print("See docs/WHITE_LABELING.md.")
    return status


if __name__ == "__main__":
    sys.exit(main())
