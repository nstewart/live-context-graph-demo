#!/usr/bin/env python3
"""Write the active label's ontology descriptions into Postgres.

`demo_ontology_freshmart.sql` defines the ontology's SHAPE -- the eight classes,
their prefixes, and the 60 properties with their domains and range kinds. All of
that is fixed for every label. It deliberately seeds every description as NULL,
because the prose is the one part a label owns, and the Knowledge Graph tab shows
it on screen.

Run after the seed SQL. Idempotent.

    python3 db/scripts/apply_ontology_labels.py
"""

from __future__ import annotations

import os
import sys

import psycopg2

from demo_label import load_label


def main() -> int:
    label = load_label()
    ontology = label.get("ontology") or {}
    classes = ontology.get("classes") or {}
    properties = ontology.get("properties") or {}

    if not classes or not properties:
        print(
            "error: the active label defines no ontology.classes/ontology.properties.\n"
            "       The Knowledge Graph tab would render blank descriptions.\n"
            "       Add an `ontology:` block to labels/<name>.yaml.",
            file=sys.stderr,
        )
        return 1

    conn = psycopg2.connect(
        host=os.environ.get("PG_HOST", "db"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("PG_USER", "postgres"),
        password=os.environ.get("PG_PASSWORD", "postgres"),
        dbname=os.environ.get("PG_DATABASE", "freshmart"),
    )
    conn.autocommit = False
    updated_c = updated_p = 0
    missing: list[str] = []
    try:
        with conn.cursor() as cur:
            for name, text in classes.items():
                cur.execute(
                    "UPDATE ontology_classes SET description = %s WHERE class_name = %s",
                    (text, name),
                )
                updated_c += cur.rowcount

            for name, text in properties.items():
                cur.execute(
                    "UPDATE ontology_properties SET description = %s WHERE prop_name = %s",
                    (text, name),
                )
                updated_p += cur.rowcount

            # Anything the label forgot would render as an empty cell on screen,
            # so name it rather than letting it ship blank.
            cur.execute(
                "SELECT class_name FROM ontology_classes WHERE description IS NULL"
                " UNION ALL "
                "SELECT prop_name FROM ontology_properties WHERE description IS NULL"
            )
            missing = [r[0] for r in cur.fetchall()]
        conn.commit()
    finally:
        conn.close()

    print(
        f"  Labelled {updated_c} ontology classes and {updated_p} properties "
        f"({label.get('label')})"
    )
    if missing:
        print(
            f"  WARNING: {len(missing)} object(s) have no description in this label: "
            + ", ".join(sorted(missing)[:10])
            + ("..." if len(missing) > 10 else ""),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
