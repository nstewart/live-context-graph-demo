# Zero named-queries migration plan

This is a forward-looking plan, not a checklist of completed work. It exists
because:

1. `definePermissions` is `@deprecated` in Zero 1.3 — its replacement is
   `defineQueries` + `defineMutators`. The `zero-deploy-permissions` step
   prints a deprecation warning at every run.
2. `z.query.tablename...` is now opt-in via `enableLegacyQueries: true` in
   [`web/src/schema.ts`](../web/src/schema.ts). Removing that flag is the
   trigger that forces the named-queries cutover.

The cutover replaces both pieces in one motion. There is no in-between state
where one half migrates without the other.

## Current state (Zero 1.3, post-upgrade)

- Schema declares 13 tables backed by Materialize MVs and four `relationships`
  bundles.
- `enableLegacyQueries: true` keeps `z.query.<table>...` calls compiling.
- `definePermissions` declares `select: ANYONE_CAN` for every table; writes are
  blocked structurally because no mutators are defined and
  `enableLegacyMutators` is unset.
- 26 call sites across 10 files use the legacy `z.query` builder.

## Target state

- No `definePermissions` block.
- `enableLegacyQueries` removed from `createSchema`.
- All read paths go through named queries declared in a shared `queries.ts`,
  evaluated server-side at a `ZERO_QUERY_URL` endpoint.
- Read access control lives inside each query body (this app's policy stays
  "anonymous can read everything", so the bodies stay simple).

## Required infrastructure changes

The named-queries API requires a server endpoint that Zero calls to evaluate
each query AST. Today the stack has no such endpoint.

Two viable hosts:

1. **Extend [`api/`](../api)** — add a `POST /zero/queries` route that calls
   `handleQueryRequest({ queries })`. Lowest infra cost; the api container
   already has DB access and is in the docker-compose graph.
2. **Add a dedicated `zero-query` service** — a tiny Node container that only
   serves `handleQueryRequest`. Cleaner blast radius if the api container is
   restarted often, but adds a new compose entry.

Then add `ZERO_QUERY_URL=http://<host>/zero/queries` to the `zero-cache`
container env.

## File-by-file query inventory

The 10 files using `z.query` (26 sites) — each becomes one or more named
query definitions.

| File | Tables touched | Notable parameters |
|------|---------------|--------------------|
| [`pages/OrdersDashboardPage.tsx`](../web/src/pages/OrdersDashboardPage.tsx) | `orders_with_lines_mv`, `stores_mv`, `courier_schedule_mv` | status filter, store filter, search |
| [`pages/StoresInventoryPage.tsx`](../web/src/pages/StoresInventoryPage.tsx) | `stores_mv`, `store_inventory_mv`, `inventory_items_with_dynamic_pricing` | store_id, category |
| [`pages/CouriersSchedulePage.tsx`](../web/src/pages/CouriersSchedulePage.tsx) | `courier_schedule_mv`, `stores_mv` | none — full table read |
| [`pages/MetricsDashboardPage.tsx`](../web/src/pages/MetricsDashboardPage.tsx) | `pricing_yield_mv`, `inventory_risk_mv`, `store_capacity_health_mv` | time window |
| [`pages/BundlingPage.tsx`](../web/src/pages/BundlingPage.tsx) | `delivery_bundles_mv`, `compatible_pairs_mv` | store_id |
| [`pages/QueryStatisticsPage.tsx`](../web/src/pages/QueryStatisticsPage.tsx) | mixed — diagnostic | several |
| [`components/OrderFormModal.tsx`](../web/src/components/OrderFormModal.tsx) | `customers_mv`, `products_mv`, `stores_mv` | none |
| [`components/CourierFormModal.tsx`](../web/src/components/CourierFormModal.tsx) | `stores_mv` | none |
| [`components/InventoryFormModal.tsx`](../web/src/components/InventoryFormModal.tsx) | `stores_mv`, `products_mv` | none |
| [`components/ProductSelector.tsx`](../web/src/components/ProductSelector.tsx) | `products_mv` | none |

Most are simple "read whole table" or "read where parent_id = X" patterns.
The two non-trivial ones are `OrdersDashboardPage` (multiple correlated
filters) and `QueryStatisticsPage` (diagnostic introspection).

## Per-step migration sequence

The ordering matters — leaving the legacy API live until the very last step
keeps the app shippable at every commit.

1. **Stand up the query endpoint.** Add `POST /zero/queries` in `api/` (or a
   new service) wired to `handleQueryRequest({ queries: {} })`. Set
   `ZERO_QUERY_URL` on `zero-cache`. Empty `queries` object — verifies
   plumbing without changing behavior.
2. **Author `web/src/queries.ts`.** One named query per call site, named for
   the page that reads it (`ordersDashboard.list`, `storesInventory.byStore`,
   etc.). For "read whole table" calls, the body is `() => zql.<table>`.
3. **Migrate one file end-to-end** — start with `ProductSelector.tsx` (one
   call, no params, no filters). Verify the page still renders.
4. **Migrate the remaining files** in dependency order (modals first, then
   pages). Keep `enableLegacyQueries: true` so partially-migrated states
   compile.
5. **Drop `definePermissions`** from `schema.ts`. Remove the `zero-permissions`
   service from `docker-compose.yml`. Drop the `update-permissions.ts` script.
6. **Drop `enableLegacyQueries: true`** from `createSchema`. Run `tsc` —
   any straggler `z.query.*` calls fail loudly.
7. **Drop the `definePermissions` import**.

## Effort estimate

- Endpoint stand-up: ~half a day, mostly spent picking host + wiring envs.
- Query authoring (`queries.ts`): ~half a day for ~26 calls; bulk of them are
  one-liners.
- Per-file migration: 10–30 min each → ~3 hours for the 10 files.
- Cleanup (steps 5–7): under an hour.

About **1.5–2 days** of focused work. The risk surface is concentrated in
step 1 (endpoint plumbing) and `OrdersDashboardPage` (most complex query).
The rest is mechanical.

## Validation

For each migrated file, the existing browser smoke test in
`/tmp/zero-smoke/smoke-deep.js` covers it — every page is loaded, console is
checked, websocket frames are counted. Re-run after each commit.

After step 6, also run `npx tsc --noEmit` from `web/` and confirm zero
errors. The TypeScript compiler is the real safety net — without
`enableLegacyQueries`, `z.query` is typed `undefined` and any leftover usage
fails to compile.

## Why this isn't done now

The Zero 1.3 upgrade itself was the in-flight task. Named queries require
new infrastructure (the query endpoint) and touch every page component,
which is a meaningfully larger change than the SDK bump. Splitting them
keeps the rollback story sane: if Zero 1.3 had wire-level issues with the
materialize-zero sidecar, we needed a small, revertable diff to debug.
