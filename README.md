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
                ↓ CREATE SINK (ENVELOPE DEBEZIUM, Avro + Schema Registry)
                Redpanda (orders / inventory CDC topics)
                ├─→ Kafka Connect
                │     • perfect-embeddings SMT → embeddings shim (bge-small)
                │     • Aiven OpenSearch sink (UPSERT)
                │         ↓
                │     OpenSearch
                │       orders index: text fields + 384-dim embedding vector
                │       inventory index: text fields
                └─→ propagation-tap → :8083 (System Performance card)

Read path (agent context):
  Agent/UI → Materialize (pre-assembled context, millisecond latency)

Read path (semantic search):
  Query → fastembed (BAAI/bge-small-en-v1.5) → OpenSearch kNN
         → Materialize hydration (live price, status, timestamps)
         → merged result card
```

**Key property:** embeddings stay fresh without re-embedding unchanged content. Materialize sinks each order as an `ENVELOPE DEBEZIUM` change event; the [perfect-embeddings](https://github.com/MaterializeInc/perfect-embedding) Kafka Connect SMT re-embeds an order **only when its `embedding_text` column changes** (a product added/renamed), and otherwise preserves the existing vector via a partial UPSERT. The embedding call goes to a local OpenAI-compatible shim wrapping `bge-small`, so there is no external API cost.

## How Vector Embeddings Stay in Sync

Embedding is expensive, so the index must re-embed an order **only when the text that gets embedded actually changes** — never on a price, quantity, or status edit. This demo gets that property from [**perfect-embeddings**](https://github.com/MaterializeInc/perfect-embedding), a Kafka Connect SMT (Single Message Transform) that diffs Materialize change events and re-embeds only modified text columns.

### Data Flow

```
PostgreSQL (triple writes)
      ↓ CDC
Materialize (orders_with_lines_mv)
  — exposes embedding_text = string_agg(product_name (category), ' | ')
      ↓ CREATE SINK ... ENVELOPE DEBEZIUM   (Avro + Confluent Schema Registry)
Redpanda topic "orders"  (each msg carries before + after image)
      ↓
Kafka Connect
  perfect-embeddings SMT (EmbeddingDiffTransform)
    before.embedding_text == after.embedding_text ?
      ↙ unchanged                         ↘ changed (or insert)
   omit embedding field             POST /v1/embeddings → embeddings shim
   (vector preserved)               (bge-small) → embedding_text_embedding
      ↓
  Aiven OpenSearch sink (index.write.method=UPSERT, partial doc merge)
      ↓
OpenSearch (knn_vector index, 384 dims)
```

### The Smart Dedup Pattern

Instead of hashing in application code, we expose the **raw embedding input as a column** in the Materialize view and let the SMT diff it. A price-only change produces a new Debezium event, but `embedding_text` is byte-identical, so the SMT skips the embeddings call and the UPSERT omits the vector field — leaving the prior vector untouched in OpenSearch.

```sql
-- Materialize view: orders_with_lines_mv  (db/materialize/init.sh)
SELECT
  ...
  COALESCE(
    string_agg(
      product_name || ' (' || COALESCE(category, '') || ')',
      ' | '
      ORDER BY line_sequence
    ) FILTER (WHERE product_name IS NOT NULL AND product_name <> ''),
    ''
  ) AS embedding_text,            -- the exact text the model embeds
  ...

-- Sink it as a Debezium change stream so the SMT sees before + after:
CREATE SINK orders_sink IN CLUSTER ingest
  FROM orders_with_lines_mv
  INTO KAFKA CONNECTION kafka_connection (TOPIC 'orders')
  KEY (order_id) NOT ENFORCED
  FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY CONNECTION csr_connection
  ENVELOPE DEBEZIUM;
```

The SMT's decision, conceptually:

```text
# perfect-embeddings EmbeddingDiffTransform, per record, per embedded column
for col in embedded.columns:                 # here: ["embedding_text"]
    if record.before is None:                # INSERT  -> embed
        record[col + "_embedding"] = embed(record.after[col])
    elif record.before[col] != record.after[col]:   # text changed -> embed
        record[col + "_embedding"] = embed(record.after[col])
    else:                                     # unchanged -> leave field absent
        pass                                  # UPSERT preserves the old vector
```

### Using a cheap local model (no OpenAI key)

The SMT speaks the OpenAI embeddings protocol, but the endpoint is overridable — so we point it at a tiny local service (`embeddings-shim/`) that wraps the **same** `BAAI/bge-small-en-v1.5` model the API uses at query time. No external API, no per-embed cost, and index-time/query-time vectors stay in the same 384-dim space.

```jsonc
// connect/connectors/orders-opensearch-sink.json  (Kafka Connect connector config)
{
  "connector.class": "io.aiven.kafka.connect.opensearch.OpensearchSinkConnector",
  "topics": "orders",
  "connection.url": "http://opensearch:9200",
  "index.write.method": "upsert",          // partial merge -> preserves vector
  "behavior.on.null.values": "delete",
  "transforms": "extractKey,embed",
  "transforms.extractKey.type": "org.apache.kafka.connect.transforms.ExtractField$Key",
  "transforms.extractKey.field": "order_id",
  "transforms.embed.type": "com.materialize.connect.smt.embedding.EmbeddingDiffTransform",
  "transforms.embed.embedded.columns": "embedding_text",
  "transforms.embed.provider": "openai",
  "transforms.embed.openai.endpoint": "http://embeddings:8080/v1/embeddings", // local shim
  "transforms.embed.openai.api.key": "local-no-key-needed",
  "transforms.embed.openai.model": "BAAI/bge-small-en-v1.5",
  "transforms.embed.openai.dimensions": "384"
}
```

```python
# embeddings-shim/app.py — OpenAI-compatible endpoint backed by local fastembed
from fastembed import TextEmbedding
model = TextEmbedding("BAAI/bge-small-en-v1.5")   # 384-dim, local ONNX, ~130MB

@app.post("/v1/embeddings")
def embeddings(req):                               # {"input": "<text>", "model": ...}
    texts = [req.input] if isinstance(req.input, str) else req.input
    vectors = [list(v) for v in model.embed(texts)]
    return {"object": "list", "model": req.model,
            "data": [{"object": "embedding", "index": i, "embedding": v}
                     for i, v in enumerate(vectors)]}
```

### Query-time Embedding

Search queries use the same model so vector spaces are compatible (the API embeds the query locally; the SMT's output field is `embedding_text_embedding`):

```python
# Pseudocode: GET /api/search/vector/orders?q=<query>

query_vector = embedder.embed([query_text])[0]   # 384-dim float list, bge-small

results = opensearch.knn_search(
    index="orders",
    field="embedding_text_embedding",             # produced by the SMT
    vector=query_vector,
    k=10,
    filter={"order_status": status, "store_zone": zone}  # optional hybrid filters
)

# Hydrate with live fields from Materialize (price, status, timestamps)
for hit in results:
    hit.live_data = materialize.query(order_id=hit.id)
```

### Embedding Model

| Property | Value |
|----------|-------|
| Model | `BAAI/bge-small-en-v1.5` |
| Dimensions | 384 |
| Runtime | fastembed / ONNX (local CPU), served over an OpenAI-compatible HTTP shim |
| Index field | `embedding_text_embedding` (`knn_vector`) in OpenSearch |

**Replicating this pattern:** the structural insight is transport- and model-agnostic. Materialize emits a Debezium change stream; the perfect-embeddings SMT re-embeds only changed text columns; an UPSERT sink preserves untouched vectors. Swap the local shim for the real OpenAI API by changing `transforms.embed.openai.endpoint`/`api.key`; swap OpenSearch for Elasticsearch by using the Confluent ES sink (`write.method=UPSERT`).

---

## Core Components

### Embedding pipeline (Kafka / Connect / SMT)

Materialize sinks the `orders` and `inventory` views into Redpanda; Kafka Connect indexes them into OpenSearch:

- **`connect`** — Kafka Connect worker hosting the Aiven OpenSearch sink connector plus the [perfect-embeddings](https://github.com/MaterializeInc/perfect-embedding) SMT. The orders connector runs the `embed` SMT (re-embeds only when `embedding_text` changes); the inventory connector just unwraps the Debezium `after` image (no embeddings).
- **`embeddings`** (`embeddings-shim/`) — OpenAI-compatible `/v1/embeddings` endpoint wrapping local `BAAI/bge-small-en-v1.5`. This is the "cheap local model" the SMT calls.
- **`propagation-tap`** (`propagation-tap/`) — consumes the Debezium topics and computes field-level change events from the before/after image, serving the `:8083` propagation API that powers the **System Performance** card.
- **`os-bootstrap` / `connect-bootstrap`** — one-shot init containers. `os-bootstrap` installs a composable **index template** per index (knn_vector + synonym analyzer) and pre-creates the index so it materializes that mapping — the Aiven connector's auto-create bypasses templates, so the index must exist before the sink writes. `connect-bootstrap` registers the sink connectors.
- **Embedding savings metrics** — the SMT exposes diff counters (`EmbeddingsComputed` / `EmbeddingsSkipped`) as a JMX MBean; a Jolokia agent on `connect` exposes them over HTTP, the API reads them at `/api/search/embedding-metrics`, and the Vector Pipeline card shows a live "**N% embedding calls avoided**" ticker — the perfect-embeddings dedup payoff, quantified.

### API (`/api/search`)

| Endpoint | Description |
|----------|-------------|
| `GET /vector/orders` | Embed query → kNN → hydrate from Materialize. Accepts `store_zone` and `order_status` filters for hybrid search. |
| `GET /impact?since_mz_timestamp=T` | Count docs re-indexed across orders + inventory since timestamp T. Returns combined impacted/total/pct plus per-index breakdown. All four OpenSearch `_count` calls run concurrently. |
| `GET /index-stats` | Total doc count from OpenSearch |
| `GET /embedding-metrics` | Embedding SMT diff counters (computed / skipped / skip ratio) read from the Connect worker via Jolokia. Degrades to `available:false` when Connect/Jolokia is down. |

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
| **redpanda** | 19092 / 18081 | Kafka broker + Schema Registry (CDC sink target) |
| **connect** | 8086 | Kafka Connect (OpenSearch sink + perfect-embeddings SMT) |
| **embeddings** | 8087 | Local OpenAI-compatible bge-small endpoint |
| **propagation-tap** | 8083 | CDC tap + propagation events API |
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
docker compose logs -f connect propagation-tap embeddings   # or: make logs-sync

# Track write propagation (clean output)
docker compose logs -f api propagation-tap | sed 's/.*INFO - //'

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
├── embeddings-shim/            # Local OpenAI-compatible /v1/embeddings (bge-small)
│   └── app.py
├── connect/                    # Kafka Connect image + connector configs
│   ├── Dockerfile              # OpenSearch sink + perfect-embeddings SMT
│   ├── connectors/             # orders (with embed SMT) + inventory sink JSON
│   └── register-connectors.sh
├── os-bootstrap/               # OpenSearch index templates (knn_vector, synonyms)
│   └── templates/              #   orders.json, inventory.json + create-indices.sh
│   ├── orders-index.json
│   ├── inventory-index.json
│   └── create-indices.sh
├── propagation-tap/            # CDC tap → propagation events API (:8083)
│   └── src/
│       ├── tap.py              # Avro consumer, before/after field diffs
│       ├── propagation_events.py
│       └── propagation_api.py
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

### Approximate embed time in the search card

The "Hybrid Vector Search" card flashes a result when it is re-embedded (detected by the embedding vector changing) and shows the client-observed time of that change. There is no server-side per-embed timestamp, so on first sighting it shows when the result entered the view rather than a historical embed time.

### Avro ↔ OpenSearch type handling (sink views)

Materialize's Avro Debezium output doesn't map 1:1 onto OpenSearch's hand-built mappings, so the sinks read from `orders_sink_v` / `inventory_sink_v` (materialized views over the app-facing MVs) that normalize types:

- **Decimals** — `numeric`/`DECIMAL` encode as Avro `decimal` (bytes), which the sink serializes as base64 and `float` fields reject. The views cast them to `double precision`.
- **Timestamps** — some date columns are raw text, others are `timestamptz` (epoch-micros). The views `to_char(... AT TIME ZONE 'UTC', ...)` them into one ISO-8601 string the OpenSearch `date` parser accepts.
- **`line_items`** — the `jsonb` column sinks as a JSON *string*, not a nested object, so it's mapped as non-indexed `text` and parsed back to a list in the API (`_parse_line_items`).

Keeping these in `*_sink_v` views leaves the API/Zero-facing MVs untouched. The Connect image also pins the Aiven OpenSearch connector to 3.1.x (4.x needs Java 21; cp-kafka-connect 7.9.7 is Java 17), and the embeddings shim runs under hypercorn (the SMT's HTTP/2 client needs h2c, which uvicorn drops).

### kNN index maintenance (deleted-doc bloat)

The sink UPSERTs an order doc on every change — including price-only updates that don't re-embed — and each UPSERT tombstones the prior Lucene version. In a `knn_vector` index, deleted vectors stay in the per-segment HNSW graph until merged, and kNN traversal (`ef_search`-bounded) wastes its budget on tombstones, so recall collapses once the deleted ratio gets high. The index templates set `index.merge.policy.deletes_pct_allowed: 10` so background merges keep the deleted ratio low (and the graph mostly-live) automatically. Under heavy bursts you can still expunge on demand: `POST /orders/_forcemerge?only_expunge_deletes=true`.

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
