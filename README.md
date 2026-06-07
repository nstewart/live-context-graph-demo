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
                ↓ CREATE SINK (Avro, ENVELOPE DEBEZIUM)
                Redpanda → Kafka Connect → OpenSearch
                  embedding SMT calls the embedding service for the vector
                  orders index: text fields + 384-dim embedding vector
                  inventory index: text fields

Read path (agent context):
  Agent/UI → Materialize (pre-assembled context, millisecond latency)

Read path (semantic search):
  Query → embedding service (BAAI/bge-small-en-v1.5) → OpenSearch kNN
         → Materialize hydration (live price, status, timestamps)
         → merged result card
```

**Key property:** Materialize sets an `mz_timestamp` Kafka header on every sink record; the Kafka Connect `HeaderToValue` transform copies it into the indexed document. After a triple write, the `/api/search/impact` endpoint counts how many documents across both indexes have `mz_timestamp >= write_time`, giving a causal measure of propagation progress.

## How Vector Embeddings Stay in Sync

The key insight: Materialize's `SUBSCRIBE` protocol streams **differential updates** — each row carries a `mz_diff` of `+1` (insert/upsert) or `-1` (delete). The `search-sync` workers consume this stream and maintain the OpenSearch index incrementally, only re-computing embeddings when the underlying text actually changes.

### Data Flow

```
PostgreSQL (triple writes)
      ↓ CDC
Materialize (orders_with_lines_mv)
  — computes embedding_hash = md5(string_agg(product_name (category), ' | '))
      ↓ SUBSCRIBE — differential stream of (+1/-1) row deltas
OrdersSyncWorker (batches up to 1000 events, flushes every 5s)
      ↓
  consolidate DELETE+INSERT pairs into UPDATE events
  _should_reembed(): compare embedding_hash from old vs. new row
      ↙                        ↘
 hash changed?             hash unchanged?
 build text + embed         patch non-vector fields only
      ↓
OpenSearch (knn_vector index, 384 dims)
```

### The Smart Dedup Pattern

Embedding is CPU-bound. Re-embedding every update (price change, status flip, qty tweak) would be wasteful. Rather than maintaining a separate in-process cache, the worker delegates the hash to Materialize itself: `embedding_hash` is a column in `orders_with_lines_mv`, computed incrementally as the view updates. When a SUBSCRIBE `UPDATE` arrives, the differential carries both the old and new row — the worker just compares the two `embedding_hash` values.

```sql
-- Materialize view: orders_with_lines_mv
SELECT
  ...
  md5(
    string_agg(
      product_name || ' (' || category || ')',
      ' | '
      ORDER BY line_sequence
    ) FILTER (WHERE product_name IS NOT NULL)
  ) AS embedding_hash,
  ...
```

```python
# Pseudocode: BaseSubscribeWorker consolidation

for DELETE, INSERT pair at same timestamp:
    # This is an UPDATE — annotate before it reaches _flush_batch
    doc["_needs_embedding"] = _should_reembed(old_row, new_row)

# OrdersSyncWorker._should_reembed
def _should_reembed(old_data, new_data):
    return old_data["embedding_hash"] != new_data["embedding_hash"]
```

```python
# Pseudocode: orders_sync._flush_batch()

for doc in batch:
    needs_embedding = doc.pop("_needs_embedding", True)  # new inserts always embed

    if needs_embedding:
        embedding_text = build_embedding_text(doc)       # build text only when needed
        needs_embed_batch.append((doc, embedding_text))
    else:
        needs_patch_batch.append(doc)

# Embed only what actually changed
vectors = embedder.embed([text for _, text in needs_embed_batch])

# Two bulk ops to OpenSearch:
bulk_upsert(needs_embed_batch, vectors)   # full doc including new vector
bulk_patch(needs_patch_batch)             # partial update, vector untouched
```

No in-memory hash cache — the hash lives in Materialize and rides along in the SUBSCRIBE stream.

### Query-time Embedding

Search queries use the same model so vector spaces are compatible:

```python
# Pseudocode: GET /api/search/vector/orders?q=<query>

query_vector = embedder.embed([query_text])[0]   # 384-dim float list

results = opensearch.knn_search(
    index="orders",
    vector=query_vector,
    k=10,
    filter={"order_status": status, "store_zone": zone}  # optional hybrid filters
)

# Hydrate with live fields from Materialize (price, status, timestamps)
for hit in results:
    hit.live_data = materialize.query(order_id=hit.id)
```

### Embedding Model

Both paths use `BAAI/bge-small-en-v1.5` via `fastembed` (local ONNX runtime — no external API call):

| Property | Value |
|----------|-------|
| Model | `BAAI/bge-small-en-v1.5` |
| Dimensions | 384 |
| Runtime | fastembed / ONNX (local CPU) |
| Index field | `knn_vector` in OpenSearch |

**Replicating this pattern:** Swap the Materialize `SUBSCRIBE` for any CDC stream (Kafka, Debezium, Postgres logical replication). Swap `fastembed` for any embedding API. The structural insight — push hash computation into the view, stream deltas with hashes, annotate at consolidation time, embed only on content change — is model and transport agnostic.

---

## Core Components

### Search ingest pipeline (Materialize sink → Redpanda → Kafka Connect)

Materialize `CREATE SINK` publishes `orders_with_lines_mv` and
`inventory_items_with_dynamic_pricing_mv` to Redpanda as Avro/Debezium
records. Kafka Connect (Aiven OpenSearch sink) upserts them into OpenSearch:

- **orders connector** — the embedding SMT (`EmbeddingDiffTransform`) diffs the Debezium before/after structs and only calls the embedding service when the `embedding_text` column changes; otherwise unchanged columns are preserved by the UPSERT. The resulting `embedding_text_embedding` is a 384-dim `knn_vector`.
- **inventory connector** — text-only index, no embedding SMT.
- **embedding-service** — an OpenAI-compatible (`/v1/embeddings`) facade over local `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim), shared by the ingest SMT and the query path.

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
| **redpanda** | 19092 / 18081 | Kafka broker (ext) + Schema Registry (ext) |
| **kafka-connect** | 8083 | Kafka Connect — OpenSearch sink + embedding SMT |
| **embedding-service** | 8085 | OpenAI-compatible embedding facade (fastembed) |
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
docker compose logs -f kafka-connect

# Track write propagation (clean output)
docker compose logs -f api kafka-connect | sed 's/.*INFO - //'

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
├── embedding-service/          # OpenAI-compatible embedding facade
│   └── src/main.py             # POST /v1/embeddings (fastembed bge-small/384)
│
├── kafka-connect/              # Search ingest pipeline (Connect + embedding SMT)
│   ├── Dockerfile              # Connect + Aiven OpenSearch sink + embedding SMT
│   ├── connectors/             # orders + inventory sink configs
│   ├── opensearch-templates/   # index mappings (knn_vector, analyzers)
│   └── init.sh                 # applies templates + registers connectors
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
