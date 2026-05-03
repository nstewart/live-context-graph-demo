# Live Context Graph Demo

A demo of how Materialize provides **live, pre-assembled context** for AI agents — using FreshMart same-day grocery delivery as a concrete scenario.

## What Is This?

This project shows an AI agent architecture where:

- Operational data (orders, inventory, couriers) is written as **RDF-style triples** into PostgreSQL
- **Materialize** continuously maintains denormalized read models from CDC — no batch ETL, no stale snapshots
- **OpenSearch** indexes those documents with 384-dim embeddings for **hybrid vector + keyword search**
- A **React demo UI** lets you observe the full propagation chain: write a triple → watch it ripple through Materialize views, the search index, and the embedding in real time

The demo makes three architectural approaches directly comparable — switch between **Postgres (OLTP)**, **Batch**, and **Materialize (incremental view maintenance)** to see what changes at each layer.

**Why it matters:** AI agents need context that reflects the business *right now*. The traditional tradeoff between freshness and latency disappears when your read model is continuously maintained rather than periodically rebuilt.

## Quick Start

```bash
git clone https://github.com/nstewart/live-context-graph-demo.git
cd live-context-graph-demo
cp .env.example .env

# Install uv (Python package manager) if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Start all services
make up

# Or start with the LangGraph agent included
make up-agent
```

**Services will be ready at:**
- Demo UI: http://localhost:5173
- API Docs: http://localhost:8080/docs
- Materialize Console: http://localhost:6874
- OpenSearch: http://localhost:9200

The system seeds demo data automatically: 5 stores, 15 products, 15 customers, 20 orders.

## Demo Walkthrough

Open the **Freshmart Demo** page at http://localhost:5173. The page has three main sections:

### 1. Architecture Diagram

An interactive diagram that switches between three scenarios:

- **Materialize** — CDC from OLTP sources → incremental view maintenance (Bronze/Silver/Gold medallion) → indexed queries. Agent and MCP Server nodes show the Observe/Act interaction pattern with animated edges.
- **Batch** — same medallion structure, static arrow flow, no incremental maintenance.
- **Postgres (OLTP)** — single OLTP box with a Base Tables layer and a Business Logic layer; no medallion bands.

### 2. Context & Lineage

A live API response showing what an agent receives when it queries Materialize for order context — pre-assembled with customer, store, courier, line items, and dynamic pricing in a single read.

### 3. System Performance

Response time and reaction time charts comparing query patterns across scenarios, plus live order cards that update in real time via Zero WebSocket sync.

#### Write a Triple

Enter a subject (`order:FM-1001`), pick a predicate, set a value, and click **Write**. This writes to the PostgreSQL triple store; you can watch propagation immediately:

- The order card in the UI updates via Zero (sub-second)
- The **Search Index Updates** bar fills in colored marks as each affected document is re-indexed in OpenSearch — one mark per document, positioned proportionally across a 65k virtual space so 94 out of 8,000 docs looks sparse, not full

### 4. Hybrid Vector Search

The **Vector Pipeline** section embeds your natural language query using `BAAI/bge-small-en-v1.5` (384-dim), runs a kNN search against OpenSearch, then hydrates each hit from Materialize at request time for live fields.

- Filter by delivery zone or order status for hybrid kNN + keyword search
- Each result card shows the order's embedding hex fingerprint, embedding source text, line items with live vs. base pricing, and a % match score
- After writing a triple, the embedding fingerprint and text block flash yellow when that order is re-embedded

## Architecture

```
Write path:
  API → PostgreSQL (triple store, ontology-validated)
                ↓ CDC
                Materialize (incremental views: orders, inventory, pricing)
                ↓ SUBSCRIBE
                Zero Server → WebSocket → UI (live order cards)
                ↓ SUBSCRIBE
                search-sync → OpenSearch
                  orders index: text fields + 384-dim embedding vector
                  inventory index: text fields

Read path (agent context):
  Agent/UI → Materialize (pre-assembled context, millisecond latency)

Read path (semantic search):
  Query → fastembed (BAAI/bge-small-en-v1.5) → OpenSearch kNN
         → Materialize hydration (live price, status, timestamps)
         → merged result card
```

**Key property:** The search index's `mz_timestamp` field is stamped at flush time by `search-sync`. After a triple write, the `/api/search/impact` endpoint counts how many documents across both indexes have `mz_timestamp >= write_time`, giving a causal measure of propagation progress.

## Core Components

### search-sync

SUBSCRIBE workers that tail Materialize and push to OpenSearch:

- **`OrdersSyncWorker`** — MD5 dedup on line-item text: re-embeds only when product composition changes, patches price/qty/status updates without touching the vector. Hash cache is updated only after a successful flush to prevent stale-cache bugs on retry.
- **`InventorySyncWorker`** — text-only index, no embeddings
- **`BaseSubscribeWorker`** — stamps `mz_timestamp` (wall-clock ms) on every upserted doc; provides the causal anchor for impact measurement

### API (`/api/search`)

| Endpoint | Description |
|----------|-------------|
| `GET /vector/orders` | Embed query → kNN → hydrate from Materialize. Accepts `store_zone` and `order_status` filters for hybrid search. |
| `GET /impact?since_mz_timestamp=T` | Count docs re-indexed across orders + inventory since timestamp T. Returns combined impacted/total/pct plus per-index breakdown. All four OpenSearch `_count` calls run concurrently. |
| `GET /index-stats` | Total doc count from OpenSearch |

### Dynamic Pricing Engine

Materialize maintains live pricing through composable views:

- **Zone premiums**: Manhattan +15%, Brooklyn +5%
- **Perishability discounts**: 5% off to move inventory
- **Scarcity premiums**: +10% for low stock items
- **Demand multipliers**: based on rolling 7-day sales velocity

### LangGraph Agent (optional)

An Operations Assistant with SSE streaming, PostgreSQL-backed conversation memory, and tools for reading context from Materialize and writing triples. Start with `make up-agent` and access via the floating chat widget in the UI.

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL — triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **zero-cache** | 4848 | Zero WebSocket server for real-time UI sync |
| **opensearch** | 9200 | Search + kNN vector index |
| **api** | 8080 | FastAPI backend |
| **search-sync** | 8083 | SUBSCRIBE workers + propagation API |
| **web** | 5173 | React demo UI |
| **agents** | 8081 | LangGraph agent with SSE streaming (optional) |

## Development

**Note:** Doesn't run well with Zoom in parallel locally. Use the AWS path for screen-share demos.

```bash
# Start all services
make up

# Start with agent
make up-agent

# Stop (data persists)
make down

# View logs
docker compose logs -f api
docker compose logs -f search-sync

# Track write propagation (clean output)
docker compose logs -f api search-sync | sed 's/.*INFO - //'

# Restart a single service
docker compose restart api

# Run tests
docker compose exec api python -m pytest tests/ -v

# See all commands
make help
```

### AWS deployment

```bash
make aws-debug          # verify setup
make up-aws             # deploy without agent
make up-agent-aws       # deploy with agent
make down-aws           # tear down
```

See [aws/README.md](aws/README.md) for full details.

### Generate live load

```bash
make load-gen           # 5 orders/min (demo profile)
make load-gen-standard  # 20 orders/min
make load-gen-peak      # 60 orders/min
make load-gen-stress    # 200 orders/min
```

## Project Structure

```
live-context-graph-demo/
├── docker-compose.yml
├── Makefile
├── .env.example
│
├── db/
│   ├── migrations/             # SQL migrations
│   ├── seed/                   # Demo data
│   ├── materialize/            # Materialize view initialization
│   └── scripts/                # Load test data generator
│
├── api/                        # FastAPI backend
│   └── src/
│       ├── routes/
│       │   ├── search.py       # Vector search + impact endpoints
│       │   └── query_stats.py  # Write triple, metrics, lineage
│       ├── ontology/
│       └── triples/
│
├── search-sync/                # OpenSearch sync workers
│   └── src/
│       ├── base_subscribe_worker.py
│       ├── embedder.py         # fastembed BAAI/bge-small-en-v1.5
│       ├── orders_sync.py      # Embedding + patch dedup logic
│       └── inventory_sync.py
│
├── web/                        # React demo UI
│   └── src/
│       ├── components/
│       │   ├── LineageGraph.tsx        # Architecture diagram (3 scenarios)
│       │   ├── VectorPipelineCard.tsx  # Hybrid search UI
│       │   ├── WriteTripleForm.tsx     # Triple write form
│       │   ├── SearchIndexUpdates.tsx  # Impact marker bar
│       │   └── PropagationWidget.tsx   # Real-time event stream
│       └── pages/
│           └── QueryStatisticsPage.tsx # Main demo page
│
├── agents/                     # LangGraph agent (optional)
│   └── src/
│       ├── server.py           # FastAPI + SSE streaming
│       └── tools/
│
└── docs/
```

## Known Limitations

### Zero and Materialize UNIQUE Index Constraint

Zero requires a `PRIMARY KEY` or `UNIQUE` index. Materialize supports `PRIMARY KEY` on tables but not `UNIQUE` indexes on materialized views, so time-series views can't sync through Zero. Time-series data for charts is fetched via direct API polling (`/api/metrics/timeseries`, 5-second interval) instead.

### Delivery Bundling (opt-in, CPU intensive)

`WITH MUTUALLY RECURSIVE` views that group compatible orders by store, time window, inventory, and courier capacity. Disabled by default (~460s of compute).

```bash
make up-agent-bundling
```

## Agent Skills

This repo includes the [materialize-docs](https://github.com/MaterializeInc/agent-skills) skill for Claude Code, which provides Materialize documentation in-context when working on this project.

```bash
# Update to latest version
npx skills update
```

## License

MIT
