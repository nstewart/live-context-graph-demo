# White-labeling the demo

The demo ships as **FreshMart**, a same-day grocery delivery business. A *label*
re-skins everything a customer sees — brand, theme, copy, vocabulary, seed data,
search synonyms, and the agent's persona — without changing how the demo behaves.

- [Using a label](#using-a-label) — running the demo under a different skin
- [Adding a new label](#adding-a-new-label) — step-by-step
- [Key reference](#key-reference) — what every YAML section controls
- [Guard rails](#guard-rails) and [Troubleshooting](#troubleshooting)

---

## The one rule

**A label changes words and data. It never changes shape.**

Field engineers already know how to give this demo. The same clicks must produce
the same behavior no matter which label is loaded, so these are identical across
every label:

| Fixed forever | Why |
|---|---|
| predicate names (`order_status`, `store_zone`) | ~30 SQL views pivot on these exact string literals |
| view names (`orders_with_lines_mv`) | referenced by Zero, the API's view whitelist, and the lineage graph |
| enum **values** (`CREATED`, `MAN`, `BIKE`) | the dynamic-pricing SQL joins on them |
| zone **codes** (`MAN`, `BK`, `QNS`, `BX`, `SI`) | join keys in the pricing multipliers |
| subject prefixes (`order:`, `store:`) | ontology class prefixes drive validation |
| JSON field names on the wire | the OpenSearch mappings and Zero schema depend on them |
| entity counts (10 / 760 / 100 / 500 / 7,600) | keeps index size, kNN recall, and demo timings stable |
| all SQL: pricing, bundling, dispatch, capacity | out of scope; see [what is not label-driven](#what-is-deliberately-not-label-driven) |

A label changes the *display* of all of the above, via `enums` and `aliases`.

---

## Using a label

```bash
make labels                      # list what's available
make up                          # freshmart (the default)
make up LABEL=life-insurance     # in-force life insurance / annuity servicing
make up LABEL=logistics          # LTL freight and final-mile carrier
```

`LABEL` is optional everywhere and defaults to `freshmart`. It works on:

| Target | Notes |
|---|---|
| `make up LABEL=…` | full stack |
| `make up-agent LABEL=…` | with the LangGraph agent |
| `make up-agent-bundling LABEL=…` | with delivery bundling (CPU intensive) |
| `make seed LABEL=…` | re-seed only |
| `make reset-db LABEL=…` | destroy + rebuild |
| `make up-aws LABEL=…` and the other `*-aws` targets | resolved artifacts rsync automatically |

Every `up*` target depends on `make label`, so an unknown or malformed label
**fails before Docker is touched**:

```
$ make up LABEL=nope
error: unknown label 'nope'.
Available: freshmart, life-insurance, logistics
```

### Switching labels

Just re-run `make up` with the new label. `make up` always re-seeds (the
generator does `DELETE FROM triples` first), so the data is replaced, never
mixed. Two consequences:

- Switching labels **discards anything you wrote during a demo**.
- You do *not* need `reset-db` to switch. Use it only if the database is
  otherwise wedged.

### Checking what's live

```bash
curl -s localhost:8080/api/features/label
{"active":"life-insurance","brand":"Acme Life","seeded":"life-insurance","matches":true,"hint":null}
```

`active` is what the API process was started with; `seeded` is what produced the
rows in Postgres. They disagree if a UI or API is running against another
label's data — see [Troubleshooting](#troubleshooting).

### Before you commit

`web/src/generated/label.json` is a **committed** artifact holding the *freshmart*
resolve, so a bare `npm run dev` / `vitest` works without Python. Running any
other label overwrites it. Restore it before committing:

```bash
make label        # re-resolves freshmart, restoring the committed artifact
```

`make label-check` fails in CI with that instruction if you forget.

---

## Adding a new label

### 1. Create the file

Name it after the vertical, lowercase with hyphens. It lists only what *differs*
from `freshmart.yaml` — everything else is inherited.

```bash
$EDITOR labels/acme-widgets.yaml
```

Minimum viable skeleton:

```yaml
label: acme-widgets          # must match the filename stem

brand:
  name: Acme Widgets
  tagline: Operations Console
  tab_title: Acme Widgets Operations - Console
  theme:
    primary: indigo          # Tailwind palette names; see Key reference
    accent: teal
  favicon: acme-widgets.svg  # you must add this file -- step 2

vocabulary:
  order:   { one: work order, many: work orders,
             title: Work Order, title_many: Work Orders, id_prefix: WO- }
  # ... repeat for customer, store, product, inventory, courier, task

enums:                       # KEYS are fixed; only the display labels change
  order_status: { CREATED: Received, PICKING: In Build,
                  OUT_FOR_DELIVERY: Shipping, DELIVERED: Delivered,
                  CANCELLED: Cancelled }
  zone: { MAN: Northeast, BK: Mid-Atlantic, QNS: Midwest,
          BX: Southeast, SI: West }

seed:
  store_name_template: Acme Widgets {zone_name} Plant {n}
  locations:
    - { code: BK, name: Mid-Atlantic, streets: [Market St, Arch St] }
    # ... all five codes, which never change
  catalog:
    expand_to: 760
    variant_suffixes: ["(rush)", "(custom)", "(bulk)"]
    categories:
      - { name: Fabrication, perishable_default: false }
    items:
      - ["Bracket assembly", "Fabrication", 12.50, 400, false]
      # ~130 rows is plenty

agent:
  persona: Operations Assistant
  system_prompt: |
    ...                      # REQUIRED -- step 3
```

### 2. Add the favicon

Drop an SVG at `web/public/<brand.favicon>`. The tab title and icon are
substituted into `index.html` at build time by the `demo-label-html` plugin in
`web/vite.config.ts`, so there is no flash of the wrong brand.

### 3. Override the agent system prompt

Easy to forget, and the leak detector will catch it. If you inherit
`agent.system_prompt`, your insurance demo's chat assistant introduces itself as
a grocery delivery service.

Start from freshmart's and rewrite the prose. **Do not touch** the identifiers
inside it — tool names (`search_orders`, `list_stores`, …), field names
(`live_price`, `base_price`, `store_id`), predicates (`placed_by`,
`line_of_order`), enum values, or subject ids. The agent actually calls those.

```bash
# Dump the current prompt to work from
python3 tools/resolve_label.py --label freshmart --print \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['agent']['system_prompt'])"
```

### 4. Resolve and validate

```bash
make label LABEL=acme-widgets
```

Deep-merges over freshmart, validates against `labels/schema.json`, and writes
the three artifacts. Fix anything it reports.

### 5. Prove no default vocabulary leaked

```bash
make label-leaks
```

Copy lives in ~35 files; careful reading does not scale. This resolves every
label and greps its user-facing strings for grocery vocabulary, so a key you
forgot to override shows up as:

```
FAIL acme-widgets: 1 leaked string(s)
  .pages.metrics.kpi_revenue_at_risk
      matched 'perishable': Revenue at Risk from perishable spoilage
```

### 6. Run it

```bash
make up LABEL=acme-widgets
```

Then walk the demo — architecture diagram, Context & Lineage, Write a Triple,
Vector Search, Metrics, agent chat. The two places worth looking hardest are the
**SQL preview** on `/` and the **lineage graph**, since that is where the display
aliases do their work.

### 7. Restore the default before committing

```bash
make label && make label-ci
```

### Checklist

- [ ] `label:` matches the filename stem
- [ ] `brand.favicon` file exists under `web/public/`
- [ ] all five zone **codes** present in `seed.locations` (names may change)
- [ ] `vocabulary.order.id_prefix` set (e.g. `WO-`)
- [ ] `agent.system_prompt` rewritten, identifiers untouched
- [ ] `seed.catalog.variant_suffixes` set if `expand_to` exceeds the item count
- [ ] `make label LABEL=… && make label-leaks` both clean
- [ ] `make label` run last, so the committed artifact is freshmart again

---

## Key reference

| Section | Controls | Where it shows |
|---|---|---|
| `brand.name` / `tagline` | sidebar wordmark and subtitle | every page |
| `brand.tab_title` / `favicon` | browser tab | `index.html`, build-time |
| `brand.theme.primary` / `accent` | `brand-*` / `accent-*` Tailwind scales | buttons, active nav, focus rings |
| `brand.qr` | QR modal URL and CTA | sidebar → Show QR Code |
| `vocabulary.<entity>` | display words per entity type | everywhere, via `entity()` |
| `vocabulary.order.id_prefix` | order-number prefix | seeder, load generator, agent |
| `enums.<name>` | value → display label | dropdowns, status badges |
| `aliases.columns` / `views` / `predicates` | **display-only** identifier renaming | SQL preview, lineage graph, predicate dropdown, raw JSON, OpenSearch examples |
| `nav` | sidebar labels **and order** | sidebar (icons stay keyed by route) |
| `pages.<page>` | titles, subtitles, search placeholders | each page header |
| `copy.<block>` | narrative/explainer prose | the teaching cards |
| `placeholders` | form input placeholders | all modals and forms |
| `examples.search_queries` | "Try:" suggestions | Vector Pipeline |
| `examples.predicate_values` | sample values per predicate | Write a Triple |
| `seed.store_name_template` | store naming (`{zone_name}`, `{n}`) | seeded data |
| `seed.locations` | zone names and street pools | seeded addresses |
| `seed.catalog` | the product catalog | seeded data, search results |
| `search.synonyms` | OpenSearch synonym filter | keyword half of hybrid search |
| `agent.persona` / `placeholder` / `empty_state` | chat widget chrome | chat widget |
| `agent.system_prompt` | the LLM's entire briefing | agent responses |

### The catalog

Rows are `[name, category, price, weight_grams, perishable]`. The last two are
mandatory in every vertical because the dynamic-pricing and bundling SQL key on
them — reinterpret them rather than dropping them:

| Column | freshmart | life-insurance | logistics |
|---|---|---|---|
| `price` | item price | cost to serve | freight rate |
| `weight_grams` | grams | handling effort | billable handling weight |
| `perishable` | needs cold chain | has a statutory deadline | needs reefer equipment |

Keep `weight_grams` in freshmart's magnitude whatever it means in your vertical.
The bundling SQL compares it against fixed gram thresholds (5 kg / 20 kg / 50 kg),
so authoring literal pallet weights would push every pair over the limit and the
Load Consolidation page would render empty.

`freshmart` authors all 760 rows so its seeded data is byte-identical to the
pre-white-labeling demo. Other labels author a compact list (~130 is plenty) and
set `expand_to: 760`; the seeder appends `variant_suffixes` to reach the same
count, scaling price and weight deterministically. Keep `expand_to` at 760 so
index size and kNN behavior match across labels.

---

## How it works

One Python resolver deep-merges your label over `freshmart.yaml` and writes the
artifacts every service reads. It is the only place YAML is parsed, so merge
semantics can only ever be wrong in one place.

```
labels/freshmart.yaml         complete reference -- defines every key
labels/<name>.yaml            diffs only; everything else inherited
labels/schema.json            validated on resolve
        |
        v   tools/resolve_label.py
        |
        +--> web/src/generated/label.json      committed; Vite + vitest import it
        +--> labels/.resolved/active.json      gitignored; api / agents / seeder
        +--> os-bootstrap/rendered/templates/  gitignored; OpenSearch mappings
```

The web artifact is a **projection** — the 760-row catalog, the synonym list, and
the system prompt are server-side only and would otherwise ship to the browser
(8 KB instead of 103 KB).

Resolution needs `pyyaml` and `jsonschema`. The Makefile uses your system
`python3` only if it has **both**, otherwise it falls back to
`uv run --with pyyaml --with jsonschema`. If validation is ever skipped, the
resolver says so on stderr rather than passing quietly.

### Merge semantics

Dicts merge recursively. **Everything else, including lists, is replaced
wholesale.** A label that wants to change one nav item must restate all ten.
This is deliberate: element-wise list merging makes it impossible to remove or
reorder an inherited entry.

---

## Guard rails

`make label-ci` runs all three; `make test` includes it.

| Command | Catches |
|---|---|
| `make label-check` | the committed web artifact drifting from `freshmart.yaml` |
| `make label-leaks` | a label that inherited the default vertical's wording |
| `make label-lint` | the brand hardcoded back into application source |

---

## Troubleshooting

**The UI shows the wrong brand.** The web reads the committed
`web/src/generated/label.json`. Run `make label LABEL=<name>`; Vite hot-reloads it.

**`/api/features/label` reports `matches: false`.** The API caches the resolved
label for its process lifetime, so it holds whatever was active when it booted.
Recreate it:

```bash
DEMO_LABEL=<name> docker compose up -d --force-recreate api
```

`make up LABEL=<name>` does this for you; a bare `make seed LABEL=<name>` does not.

**`os-bootstrap` exits 1 with "NOT knn_vector".** An `orders` index exists in your
OpenSearch volume from before the index was label-stamped, and templates only
apply at creation. Normally `make up` heals this by itself (see below); if it
doesn't, delete the derived indices and re-run — they rebuild from Materialize:

```bash
curl -X DELETE localhost:9200/orders
curl -X DELETE localhost:9200/inventory
make up LABEL=<name>
```

**Search returns results from the previous label.** Shouldn't happen any more,
but here is the mechanism, because it is subtle. The OpenSearch sink only
*upserts* by key — it never deletes documents whose keys disappear upstream.
Re-seeding under a new label mints new order ids (`SC-…` → `SH-…`), so the old
label's documents would survive and a freight demo could return life-insurance
hits from semantic search.

Each index is therefore stamped at creation with `mappings._meta.demo_label`.
`create-indices.sh` compares that to the label being started and deletes the
index on a mismatch, so it rebuilds from the template. An index with no stamp
reads as `unknown` and is also rebuilt, which is what heals the stale-mapping
case above.

To check:

```bash
curl -s localhost:9200/orders/_mapping?filter_path=orders.mappings._meta
curl -s localhost:9200/orders/_count      # should equal the seeded order count
```

**This self-heals only inside `make up`.** Deleting an index repopulates it
because `make up` recreates `materialize-init`, which recreates the sinks and
re-emits their snapshot to Kafka. Running `docker compose run --rm os-bootstrap`
on its own deletes the index and leaves it **empty** — the sink's consumer
offsets are already past those messages. If you do that, follow with a full
`make up LABEL=<name>`.

**Seeded orders have the wrong prefix.** `db/seed/demo_bundleable_orders.sql` is
hand-written SQL; `db/scripts/seed_docker.sh` rewrites its `FM-` prefix at seed
time. If you changed that script, check the `ORDER_PREFIX` substitution.

**`make label` warns that jsonschema is not installed.** Structural checks ran
but `labels/schema.json` was not enforced. Install `jsonschema`, or let the
Makefile's `uv` fallback handle it.

---

## What is deliberately not label-driven

**The SQL.** The 8-factor dynamic pricing formula
(`db/materialize/init.sh:470-721`), the courier dispatch state machine
(`:1087-1160`), the store capacity model (`:995-1059`), and the mutually
recursive bundling (`:1439-1548`) are the demo's actual subject matter. They stay
grocery-shaped; a label reinterprets what those numbers *mean*.

**Structural identifiers.** The `/freshmart/*` API route prefix, the `freshmart`
Postgres database name, and the `freshmart-network` Docker network keep their
names. Renaming them would break a field engineer's mental model for no customer
benefit — none is visible in the demo.

**Python internals.** Module docstrings, class names (`FreshMartAPIClient`), log
lines, and comments in `api/`, `load-generator/`, and `db/scripts/` still say
FreshMart. They are developer-facing. `label-lint` scans only the
customer-visible surfaces: `web/src`, `agents/src`, and the OpenAPI metadata in
`api/src/main.py`.

---

## Theming

`brand.theme.primary` and `.accent` name Tailwind palettes, wired into
`tailwind.config.js` as the `brand-*` and `accent-*` scales.

The convention, which matters when editing components:

- **`brand-*` / `accent-*`** — identity and interaction: buttons, active nav,
  focus rings, the wordmark.
- **plain `green-*` / `red-*` / `amber-*`** — semantics: success, health, "live",
  positive deltas, status badges. These must **not** follow the brand, or a
  navy-branded demo turns its success messages navy.
- **`*-400` on dark backgrounds** — syntax highlighting in the SQL and JSON
  panels (green = string literal, purple = keyword). Also not brand.

---

## Two things that will bite you

**`agent.system_prompt` restates the pricing rules in prose.** That makes it a
*third* copy of a formula that also lives in `db/materialize/init.sh:470-721` and
`db/migrations/081_dynamic_pricing_views.sql`. If you change the pricing SQL, you
must update the prompt in **every** label — nothing enforces this. (The three
copies were already inconsistent before this existed: the prompt claimed 7
factors while the SQL computed 8, and named three predicates that do not exist.
Both are fixed.)

**Switching labels re-seeds the database**, discarding anything written during a
demo. See [Switching labels](#switching-labels).
