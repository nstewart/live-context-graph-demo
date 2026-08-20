#!/usr/bin/env python3
"""Leak detector #3: assert the SEEDED DATA carries no default-vertical wording.

The other two detectors are static -- check_label_leaks.py reads labels/*.yaml and
check_source_leaks.py reads the source. Neither can see what is actually in
Postgres, and that is where leaks survived longest:

  - 63 ontology descriptions ("A FreshMart store location") seeded from SQL
  - 30 policyholder addresses in Brooklyn and Queens, minted by the load
    generator, whose address builder ignored the label's own geography

Both were invisible to a static scan and visible on screen. This closes that gap:
run it against a seeded stack and it reports any row a customer could read whose
value belongs to the default vertical.

    python3 tools/check_seeded_data.py                  # against localhost tunnel
    PG_HOST=... PG_PORT=... python3 tools/check_seeded_data.py

Exits non-zero when the active label is not the default and its data still
carries FreshMart's vocabulary.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOLVED = REPO / "labels" / ".resolved" / "active.json"

# The default vertical's own words. Enum VALUES are excluded deliberately: they
# are data-model shape (the SQL joins on OUT_FOR_DELIVERY) and every label keeps
# them, so they are checked by neither this nor check_label_leaks.py.
VERTICAL = re.compile(
    r"\b("
    r"freshmart|grocer(?:y|ies)|perishables?|cold chain|refrigerat\w*"
    r"|milk|dairy|produce|bakery|snacks?|seafood|poultry"
    r"|brooklyn|manhattan|queens|bronx|staten island"
    r")\b",
    re.I,
)

# Columns holding text a customer reads. Subject ids, predicates and enum values
# are structural and excluded by construction.
CHECKS = [
    (
        "ontology class descriptions",
        "SELECT class_name, description FROM ontology_classes WHERE description IS NOT NULL",
    ),
    (
        "ontology property descriptions",
        "SELECT prop_name, description FROM ontology_properties WHERE description IS NOT NULL",
    ),
    (
        "triple values",
        # object_value only: predicates are fixed, and entity_ref values are ids.
        "SELECT subject_id || ' ' || predicate, object_value FROM triples"
        " WHERE object_type <> 'entity_ref'",
    ),
]


def main() -> int:
    if not RESOLVED.exists():
        print("error: labels/.resolved/active.json missing -- run `make label`", file=sys.stderr)
        return 1
    label = json.loads(RESOLVED.read_text())
    name = label.get("label")
    if name == "freshmart":
        print("skip: the active label IS the default vertical, so its data is expected")
        print("      to use grocery vocabulary. Resolve another label to check it.")
        return 0

    try:
        import psycopg2
    except ImportError:
        print("error: psycopg2 not installed. pip install psycopg2-binary", file=sys.stderr)
        return 1

    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", "postgres"),
        dbname=os.environ.get("PG_DATABASE", "freshmart"),
    )
    print(f"seeded-data: checking the {name} data for default-vertical wording")

    status = 0
    try:
        with conn.cursor() as cur:
            for what, sql in CHECKS:
                cur.execute(sql)
                findings = []
                for key, value in cur.fetchall():
                    if not value:
                        continue
                    hit = VERTICAL.search(str(value))
                    if hit:
                        findings.append((key, hit.group(0), str(value)[:90]))
                if findings:
                    status = 1
                    print(f"FAIL {what}: {len(findings)} row(s)")
                    for key, term, value in findings[:8]:
                        print(f"  {key}\n      matched {term!r}: {value}")
                    if len(findings) > 8:
                        print(f"  ... and {len(findings) - 8} more")
                else:
                    print(f"OK   {what}")
    finally:
        conn.close()

    if status:
        print()
        print("The label renames words, but this text was written into Postgres by a")
        print("seeder or generator that did not consult it. Fix the producer, then")
        print("re-seed -- patching the rows leaves the next seed to reintroduce them.")
    return status


if __name__ == "__main__":
    sys.exit(main())
