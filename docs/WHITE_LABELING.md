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
| `vocabulary.<entity>` | display words per entity type | everywhere, via `entity()`; also names the eight ontology classes, via `aliasClass()` |
| `vocabulary.order.id_prefix` | order-number prefix | seeder, load generator, agent |
| `enums.<name>` | value → display label | dropdowns, status badges |
| `aliases.columns` / `views` / `predicates` | **display-only** identifier renaming | SQL preview, lineage graph, predicate dropdown, raw JSON, OpenSearch examples |
| `nav` | sidebar labels **and order** | sidebar (icons stay keyed by route) |
| `pages.<page>` | titles, subtitles, search placeholders | each page header |
| `copy.<block>` | narrative/explainer prose | the teaching cards |
| `placeholders` | form input placeholders | all modals and forms |
| `examples.search_queries` | "Try:" suggestions (semantic) | Vector Pipeline |
| `examples.keyword_queries` | "Try:" suggestions (literal keyword match) | Agent-native Reads |
| `examples.predicate_values` | sample values per predicate | Write a Triple |
| `seed.store_name_template` | store naming (`{zone_name}`, `{n}`) | seeded data |
| `seed.locations` | zone names and street pools | seeded addresses |
| `seed.catalog` | the product catalog | seeded data, search results |
| `search.synonyms` | OpenSearch synonym filter | keyword half of hybrid search |
| `ontology.classes` / `.properties` | descriptions for the 8 classes and 60 properties | Knowledge Graph tab (Classes and Properties) |
| `agent.persona` / `placeholder` / `empty_state` | chat widget chrome | chat widget |
| `agent.system_prompt` | the LLM's entire briefing, including the tool list and the resolve-names-first rule | agent responses |

### Reading a key from the UI

Everything in `web/src` goes through `web/src/label.ts`. There is no reason for a
component to contain a literal a label could supply, and `make label-lint` fails
if one does.

| Helper | Use |
|---|---|
| `entity('courier', 'many')` | a display word; `Entity()` / `Entities()` are the capitalized forms |
| `words('perishable')` | the forms `entity()` cannot express: `adjective`, `note`, `tooltip`, `cart_note` |
| `enumLabel('order_status', v)` | a fixed SQL value → its display text; unknown values pass through |
| `enumOptions('vehicle_type')` | the same map as `{value, label}` pairs, for a dropdown |
| `aliasColumn` / `aliasView` / `aliasPredicate` | display-only identifier renaming |
| `aliasClass('Courier')` | an ontology class name → its display word |
| `page('metrics')` / `copy('cart')` | a string bundle; `pageText()` / `copyText()` fetch one field |
| `placeholder('order_search')` | a form input placeholder |
| `displayValue('order_status', v)` | a stored value as a human reads it, given the field it came from; free-text passes through |
| `enumForField('store_zone')` | which enum a field's values are drawn from, when the names differ |

A missing key renders `⟪pages.orders.no_such_field⟫` and warns on the console,
rather than silently rendering an empty string — a half-wired screen should be
obvious, not subtle.

`aliasClass()` maps the eight seeded ontology class names (`Order`, `Courier`,
`InventoryItem`, …) onto the `vocabulary` key that already names the same entity,
so the ontology screens skin themselves and no label authors those words twice. A
class created at runtime is unknown to the map and passes through unchanged.

`HighlightedJson` runs field names through `aliasColumn()` and enum values through
`enumLabel()`, because the JSON panes on the home page and the Agent-native Reads
card are on-screen surfaces like any other. The rewrite is render-time only — the
`data` prop, change tracking, and the wire format all keep the real key.

### The agent's write paths

The assistant's wording is label-driven (`agent.system_prompt`), and that creates
a hazard the read paths do not have: a user speaks the label's vocabulary, and a
tool may write it. Two guards exist because both failures happened.

**Names never become ids.** A subject id is opaque — `customer:00002` is not
derived from "James Spence". Asked to open a case for a named person, the model
used to invent `customer:james_spence`, which has no triples, so `placed_by`
pointed at nothing and the policyholder rendered blank on every view that joins
the two. `find_customer` resolves a name to the real id, `create_order` probes
the id and refuses a dangling reference, and every label's prompt carries the
rule: resolve first, never construct an id from a name, ask when ambiguous.

**Display words never become stored values.** "Mark it settled" used to store
`order_status = SETTLED`. The enum is `CREATED / PICKING / OUT_FOR_DELIVERY /
DELIVERED / CANCELLED`; "Settled" is only what this label *shows* for
`DELIVERED`, so nothing keyed on it and the case dropped out of every
status-filtered view. `write_triples` now maps display → stored via
`stored_enum_value()` in `agents/src/demo_label.py`, reading the active label's
`enums`. Matching ignores case and spacing, so "on case", "On Case" and
`ON_CASE` all resolve to `ON_DELIVERY`. Unrecognised values pass through
untouched — genuinely new data is never silently rewritten.

The general rule when adding a tool that writes: **resolve to shape at the
boundary.** Accept the label's words if you like, but store the fixed value.

### Ontology descriptions

`db/seed/demo_ontology_freshmart.sql` defines the ontology's *shape* — the eight
classes, their prefixes, and the 60 properties with their domains and range
kinds — and is identical for every label. It seeds every `description` as **NULL**
on purpose, because the prose is what a customer reads on the Knowledge Graph tab.
`db/scripts/apply_ontology_labels.py` writes the descriptions from
`labels/<name>.yaml` immediately afterwards, and fails the seed if the active
label is missing any. A blank column beats silently showing the wrong vertical's
wording.

Keys are the fixed `class_name` and `prop_name`; only the prose changes. Because
they live in the label, `make label-leaks` already covers them — a label that
forgets one inherits FreshMart's wording and the check reports the exact path.

Descriptions that list a fixed enum pair the stored value with what the UI shows,
since a triple-writer needs the real value:

```yaml
order_status: "Case status. Stored/shown: CREATED=Received, PICKING=In Review,
  OUT_FOR_DELIVERY=Awaiting Settlement, DELIVERED=Settled, CANCELLED=Withdrawn"
```

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
| `make label-lint` | source that ignores the label (three checks, below) |
| `make label-data` | seeded rows a producer wrote without consulting the label (needs a running stack) |

`label-data` (`tools/check_seeded_data.py`) is the third axis and is deliberately
outside `label-ci`, because it needs a seeded database. Both static checks are blind to what a seeder or
generator *wrote*, and that is where leaks have survived longest: 63 ontology
descriptions, and 30 policyholder addresses in Brooklyn and Queens minted by the
load generator, whose address builder ignored `seed.locations` entirely. Run it
after `make up LABEL=<name>`. It skips when the active label is the default,
whose data is *supposed* to be grocery.

`label-leaks` reads in one direction — it proves a *label's copy* is clean.
`label-lint` (`tools/check_source_leaks.py`) reads the other, which is the
direction white-labeling actually regresses in: `labels/` can author "case
manager" perfectly while a component still renders the literal `Courier`, so the
key is authored, correct, and never read.

| Check | Catches | Scope |
|---|---|---|
| `brand` | `FreshMart` or the `FM-` prefix typed into code | all scanned source |
| `vocabulary` | the default vertical's words in a user-visible string | entity nouns in `web/src`; grocery-specific words everywhere |
| `raw-fields` | a database field rendered without its label helper | `web/src` `.tsx` |
| `dead-keys` | a label key the UI could read but no component reads | `web/src` |

`vocabulary` and `raw-fields` are two halves of one problem and you need both.
`vocabulary` reads *string literals*, so it catches a hardcoded
`Couriers & Schedule` but is blind to `{triple.predicate}` — a binding that
renders whatever Postgres holds. That blind spot is why the "Agent Writes and
Memories" card still showed raw grocery predicates after every literal on it had
been fixed: the leak was in the data path, not the copy.

`raw-fields` flags a render of `predicate`, `class_name`, `order_status`,
`store_zone` and friends when the expression is not wrapped in a label helper. It
deliberately ignores positions where the raw value is required: `value=` and
`key=` attributes, `className` lookups like `healthStatusColors[x.health_status]`,
triple-write payloads (`{ predicate: …, object_value: … }`), and `${…}` template
interpolations, which build React keys and dedup keys rather than display text.

`dead-keys` is the cheap proxy for "did anyone wire this up?" — when it was first
run it found 3 page bundles, 7 enum maps and 9 of 10 `vocabulary` entries that no
component had ever read.

The `vocabulary` check scans JSX text and string literals, skipping comments. It
does **not** skip docstrings under `agents/src/tools`, because LangChain ships
those to the model as tool descriptions and a customer hears the result. Entity
nouns are only flagged in `web/src`: in `agents/src` the tool names and
parameters *are* `create_order` and `store_id`, fixed by the same rule that fixes
predicate names, so a docstring describing `create_order` has to say "order". The
assistant's own wording comes from `agent.system_prompt`, which each label
authors in full.

When a literal genuinely has to stay, mark it and say why:

```tsx
{/* label-lint-ok: real index name, these must run as pasted */}
<div className="text-purple-600">GET orders/_search</div>
```

The pragma applies to its own line and the line below it. Reach for it rarely —
the ones in the tree today are a real OpenSearch index name and an ontology class
name the user actually types.

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

Note the distinction: those files' *comments* are out of scope, but anything they
**write into the database is not**. `db/scripts/apply_ontology_labels.py` and the
load generator's address builder both read the active label, because their output
is on screen. `make label-data` is what enforces that.

**`SHOW CREATE` output.** The View Definition modal (click a lineage-graph node)
shows the real object name and the real SQL Materialize returns, with grocery
identifiers intact. That is deliberate: the modal exists so a field engineer can
copy a runnable `SHOW CREATE` and open it in the SQL shell, and aliasing it would
produce object names that do not exist. Note the consequence — the node you click
is *labelled* `cases_flat_mv` and the modal it opens is titled `orders_flat_mv`.
If that mismatch is a problem in front of a prospect, show `aliasView(name)` as
the modal heading and keep the real name only on the copyable `SHOW CREATE` line.

**The seeder's console banner.** `db/scripts` prints `FreshMart Load Test Data
Generator` while it seeds, and the Postgres database is named `freshmart` under
every label. Both are deploy-log and DB-client text, not demo UI — but they are
the one place the default brand surfaces if you screen-share a terminal.

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
