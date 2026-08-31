# Demo labels

Each `*.yaml` here is a white-label skin for the demo. Pick one at start time:

```bash
make up                          # freshmart (default)
make up LABEL=life-insurance
make up LABEL=logistics
make up LABEL=portfolio-risk
make up LABEL=mortgage-underwriting
make up LABEL=airline-irops
make labels                      # list what's available
make label LABEL=life-insurance  # resolve + validate without starting anything
```

`freshmart.yaml` is the **base and the complete reference** — it defines every key.
Every other label lists only what it changes and inherits the rest.

**Adding a label?** Follow the step-by-step in
[`docs/WHITE_LABELING.md#adding-a-new-label`](../docs/WHITE_LABELING.md#adding-a-new-label)
— there is a skeleton, a key reference, and a checklist. The three steps people
miss are overriding `agent.system_prompt` (otherwise your assistant introduces
itself as a grocery service), writing the `ontology` block (68 class and property
descriptions, shown on the Knowledge Graph tab — omit it and you inherit
FreshMart's, which `make label-leaks` will report), and adding the favicon file
under `web/public/`.

Once the stack is up, `make label-data` checks the seeded rows themselves: the
static checks cannot see what a seeder or generator wrote into Postgres, and that
is where leaks have survived longest.

## Merge semantics

Dicts merge recursively. **Everything else, including lists, is replaced
wholesale** — a label that wants to change one nav item must restate all of
them. This is deliberate: element-wise list merging makes it impossible to
remove or reorder an inherited entry.

## What a label may not change

The data model's *shape* is fixed, so a field engineer's mental model of the demo
holds no matter which label is loaded:

| Fixed | Label-driven |
|---|---|
| predicate names (`order_status`) | their display labels and sample values |
| view names (`orders_with_lines_mv`) | their display names, via `aliases.views` |
| enum **values** (`CREATED`, `MAN`, `BIKE`) | their display labels, via `enums` |
| subject prefixes (`order:`, `store:`) | the order-number prefix (`FM-`) |
| JSON field names on the wire | their display names, via `aliases.columns` |
| entity counts (10 / 760 / 100 / 500) | the catalog contents |
| all SQL: pricing, bundling, dispatch | — |

`aliases.*` are applied **at render time only**. They never touch the wire
format, the SQL, or the database.

## Files the resolver generates

Run `make label` after editing any YAML.

| Path | Committed? | Consumed by |
|---|---|---|
| `web/src/generated/label.json` | **yes** | Vite + vitest (so a bare `npm run dev` works) |
| `labels/.resolved/active.json` | no | api, agents, seeder |
| `os-bootstrap/rendered/templates/*.json` | no | OpenSearch index bootstrap |

CI runs `python3 tools/resolve_label.py --check` to assert the committed web
artifact still matches `freshmart.yaml`. If it fails, run `make label` and commit
the result.

## Two things that will bite you

**Changing seed data requires a reseed.** Seed data is baked into Postgres at
`make up`. Switching to a label with a different catalog on an existing volume
would leave the old data under the new copy, so `make up` refuses to start on a
mismatch and tells you to run `make reset-db LABEL=<label>`.

**`agent.system_prompt` restates the dynamic-pricing rules in prose.** That makes
it a *third* copy of a formula that already lives in
`db/materialize/init.sh:470-721` and `db/migrations/081_dynamic_pricing_views.sql`.
If you change the pricing SQL, update the prompt in every label — nothing
enforces this.
