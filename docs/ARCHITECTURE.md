# Architecture

This document explains the FreshMart Digital Twin architecture, covering the CQRS pattern, Materialize integration, and real-time data flow.

## Table of Contents

- [CQRS Pattern](#cqrs-pattern)
- [Three-Tier Architecture](#three-tier-architecture)
- [Real-Time Data Flow](#real-time-data-flow)
- [SUBSCRIBE Streaming](#subscribe-streaming)
- [Search Indexing via Kafka Sink](#search-indexing-via-kafka-sink)
- [System Architecture Diagram](#system-architecture-diagram)
- [Automatic Reconnection and Resilience](#automatic-reconnection--resilience)
- [Services](#services)

## CQRS Pattern

FreshMart implements **CQRS (Command Query Responsibility Segregation)** to separate write and read concerns for optimal performance and data integrity.

### Commands (Writes)

All modifications flow through the **PostgreSQL triple store** as RDF-style subject-predicate-object statements:

- Writes are validated against the **ontology schema** (classes, properties, ranges, domains)
- This ensures data integrity and semantic consistency at write time
- The triple store acts as the governed source of truth

**Write Flow:**
```
Client → FastAPI → PostgreSQL triple store → CDC → Materialize
```

### Queries (Reads)

Read operations use **Materialize materialized views** that are pre-computed, denormalized, and indexed:

- Views are maintained in real-time via **Change Data Capture (CDC)** from PostgreSQL
- Optimized for fast queries without impacting write performance
- All UI queries routed through Materialize's serving cluster

**Read Flow:**
```
Client → FastAPI → Materialize (serving cluster) → Indexed materialized views
```

### Benefits

- **Write model**: Enforces schema through ontology, maintains graph relationships
- **Read model**: Optimized for specific query patterns (orders, inventory, customer lookups)
- **Real-time consistency**: CDC ensures views reflect writes within milliseconds
- **Scalability**: Independent scaling of write (PostgreSQL) and read (Materialize) workloads

## Three-Tier Architecture

Materialize uses a **three-tier cluster architecture** for efficient data processing:

```
┌─────────────────────────────────────────────────────────────┐
│                    Ingest Cluster                            │
│  - PostgreSQL CDC source (pg_source)                         │
│  - Replicates triples table in real-time                     │
└────────────────────────┬────────────────────────────────────┘
                         │ (Change Data Capture)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Compute Cluster                            │
│  - Materialized views transform triples                      │
│  - Pre-aggregates and denormalizes data                      │
│  - Joins entities (orders + customers + stores)              │
└────────────────────────┬────────────────────────────────────┘
                         │ (Materialized results)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Serving Cluster                            │
│  - Indexes on materialized views                             │
│  - Sub-millisecond query latency                             │
│  - All application queries hit this cluster                  │
└─────────────────────────────────────────────────────────────┘
```

### Cluster Responsibilities

**Ingest Cluster**:
- Connects to PostgreSQL via CDC
- Replicates `triples` table changes in real-time
- No application queries hit this cluster

**Compute Cluster**:
- Maintains materialized views with transformation logic
- Flattens triples into entity-shaped records
- Performs joins and aggregations
- Examples: `orders_flat_mv`, `store_inventory_mv`, `customers_mv`

**Serving Cluster**:
- Hosts indexes on materialized views
- Provides low-latency lookups for applications
- All FreshMart API queries use this cluster
- Examples: `orders_search_source_idx`, `store_inventory_idx`

### Materialized Views in FreshMart

All FreshMart endpoints query precomputed, indexed materialized views:

| API Endpoint | Materialized View | Index |
|--------------|-------------------|-------|
| `/freshmart/orders` | `orders_search_source_mv` | `orders_search_source_idx` |
| `/freshmart/stores/inventory` | `store_inventory_mv` | `store_inventory_idx` |
| `/freshmart/couriers` | `courier_schedule_mv` | `courier_schedule_idx` |
| `/freshmart/stores` | `stores_mv` | `stores_idx` |
| `/freshmart/customers` | `customers_mv` | `customers_idx` |
| `/freshmart/products` | `products_mv` | `products_idx` |
| UI Order Creation | `inventory_items_with_dynamic_pricing` | `inventory_items_with_dynamic_pricing_idx` |

## Real-Time Data Flow

FreshMart achieves **sub-second latency** for data propagation across all components:

### Complete Data Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. WRITE: Client updates order status                               │
│     POST /triples → PostgreSQL (validated by ontology)               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ (< 100ms)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  2. CDC: Change Data Capture                                         │
│     PostgreSQL → Materialize ingest cluster                          │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ (< 200ms)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  3. COMPUTE: Materialize compute cluster                             │
│     orders_flat → orders_search_source_mv (with enrichment)          │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ (< 500ms)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  4. STREAM OUT: Real-time fan-out                                    │
│     Zero WebSocket Server SUBSCRIBEs to MV                           │
│     Materialize CREATE SINK (Avro/Debezium) → Redpanda topics        │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ (< 100ms)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│  5. DELIVER: Push to clients                                         │
│     WebSocket → UI clients (differential updates)                    │
│     Kafka Connect (embedding SMT) → OpenSearch (for search)          │
└──────────────────────────────────────────────────────────────────────┘

Total latency: < 1 second (write → UI update)
```

### Data Flow Paths

**UI Updates** (Real-time):
1. Write → PostgreSQL
2. CDC → Materialize
3. SUBSCRIBE → Zero server
4. WebSocket → UI clients
5. **Latency: < 1 second**

**Search Updates** (Real-time):
1. Write → PostgreSQL
2. CDC → Materialize
3. CREATE SINK (Avro/Debezium) → Redpanda (`orders` / `inventory` topics)
4. Kafka Connect (embedding SMT) → OpenSearch
5. **Latency: < 2 seconds**

**Direct Queries** (Indexed):
1. Client → API
2. Query → Materialize serving cluster
3. Index lookup → Response
4. **Latency: < 10ms**

## SUBSCRIBE Streaming

Materialize's **SUBSCRIBE** command enables real-time streaming of differential updates from materialized views.

### How SUBSCRIBE Works

SUBSCRIBE provides a continuous stream of changes as they occur:

```sql
SUBSCRIBE (
    SELECT * FROM orders_search_source_mv
) WITH (PROGRESS);
```

**Response Format:**
```
mz_timestamp | mz_diff | order_id | order_number | ...
-------------|---------|----------|--------------|-----
1234567890   | 1       | order:1  | FM-1001      | ... (INSERT)
1234567891   | -1      | order:1  | FM-1001      | ... (DELETE)
1234567891   | 1       | order:1  | FM-1001      | ... (INSERT with new data)
```

### SUBSCRIBE Features

**Differential Updates**:
- `mz_diff = 1`: Row inserted or updated
- `mz_diff = -1`: Row deleted
- Timestamp tracks when change occurred

**PROGRESS Option**:
- Emits progress messages showing timestamps advancing
- Enables timestamp-based batching for efficient processing
- Guarantees all changes up to timestamp T have been delivered

**Snapshot Handling**:
- Initial connection emits full snapshot of current data
- Can be skipped if initial hydration already performed
- Subsequent messages are only differential updates

### FreshMart's SUBSCRIBE Usage

FreshMart uses SUBSCRIBE for UI real-time updates:

**Zero WebSocket Server** (for UI real-time updates):
- Subscribes to multiple materialized views: `orders_flat_mv`, `stores_mv`, `courier_schedule_mv`
- Broadcasts differential updates to connected WebSocket clients
- Collections map to UI pages: orders, stores, couriers

> **Note:** Search indexing uses a separate mechanism — a Materialize Kafka sink
> + Kafka Connect pipeline. See [Search Indexing via Kafka Sink](#search-indexing-via-kafka-sink) below.

### Benefits of SUBSCRIBE

- **Real-time**: Changes stream instantly (< 100ms from MV update)
- **Efficient**: Only differential updates transmitted, not full snapshots
- **Guaranteed delivery**: PROGRESS messages ensure no missed updates

## Search Indexing via Kafka Sink

Search indexing is driven by a Materialize **Kafka sink** rather than an in-process
SUBSCRIBE worker. Materialize publishes change events to Redpanda, and Kafka Connect
sinks them into OpenSearch.

### Materialize Sinks

Materialize emits Avro change events (Confluent Schema Registry) using a Debezium
envelope:

```sql
CREATE SINK orders_sink
  FROM orders_with_lines_mv
  INTO KAFKA CONNECTION redpanda (TOPIC 'orders')
  KEY (order_id)
  FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY connection
  ENVELOPE DEBEZIUM;
```

- `orders_with_lines_mv` → Kafka topic `orders` (key `order_id`)
- `inventory_items_with_dynamic_pricing_mv` → Kafka topic `inventory` (key `inventory_id`)

Each Kafka message carries a `materialize-timestamp` header recording the Materialize
logical timestamp of the change.

### Kafka Connect Sink Connectors

Kafka Connect runs the Aiven OpenSearch sink connector with a transform chain per
topic. Both connectors are **UPSERT** with `behavior.on.null.values=delete`, so a
Debezium delete (null value) becomes a tombstone that removes the OpenSearch document.

**orders connector** (transform chain):
1. `extractKey` — promote the Kafka key to the document `_id`
2. `embed` (`EmbeddingDiffTransform`) — calls the embedding service to populate the
   `embedding_text_embedding` vector field (`knn_vector`, 384 dims); re-embeds only
   when the `embedding_text` column changes (Debezium before/after diff)
3. `cast` — decimals → `float64`
4. `tsHeader` (`HeaderToValue`) — copy the `materialize-timestamp` Kafka header into
   the `mz_timestamp` document field

**inventory connector** (transform chain):
1. `extractKey`
2. `unwrap` (`ExtractField` after) — flatten the Debezium envelope
3. `cast` — decimals → `float64`
4. `tsHeader` — `materialize-timestamp` header → `mz_timestamp` (no embedding)

### Embedding Service

A standalone `embedding-service` exposes an OpenAI-compatible `/v1/embeddings`
endpoint backed by fastembed `BAAI/bge-small-en-v1.5` (384-dim), served by Hypercorn
on port 8085. It is used both at ingest time (by the orders connector's embedding SMT)
and at query time (by the API for kNN search). Re-embed deduplication is handled by
the SMT's Debezium before/after diff — there is no separate hash cache.

### Benefits of the Kafka Sink Pipeline

- **Decoupled**: Materialize, Redpanda, and OpenSearch scale independently
- **Exactly-once-style upserts**: keyed Debezium events make indexing idempotent
- **Vector search**: embeddings computed inline via the SMT, re-embedding only on text changes
- **Operationally standard**: managed entirely through the Kafka Connect REST API

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Admin UI (React)                                    │
│                      Port: 5173                                          │
│  • Real-time updates via WebSocket                                       │
│  • Orders, Couriers, Stores/Inventory dashboards                         │
└──────────────┬──────────────────────────────────┬────────────────────────┘
               │ REST API (writes/reads)          ▲ WebSocket (real-time)
               ▼                                  │
┌──────────────────────────┐         ┌─────────────────────────────────────┐
│  Graph/Ontology API      │         │    Zero WebSocket Server            │
│  (FastAPI) Port: 8080    │         │    Port: 8090                       │
│  • Ontology CRUD         │         │  • SUBSCRIBE to Materialize MVs     │
│  • Triple CRUD           │         │  • Broadcast changes to clients     │
│  • FreshMart endpoints   │         │  • Collections: orders, stores,     │
│  • Query logging         │         │    couriers, inventory              │
└───────┬──────────────────┘         └────────────▲────────────────────────┘
        │ writes                                  │ SUBSCRIBE
        ▼                                         │ (differential updates)
┌──────────────────────────┐         ┌───────────┴─────────────────────────┐
│     PostgreSQL           │         │      Materialize                     │
│     Port: 5432           │────────▶│  Console: 6874 SQL: 6875             │
│  • ontology_classes      │ (CDC)   │  Three-Tier Architecture:            │
│  • ontology_properties   │         │  • ingest: pg_source (CDC)           │
│  • triples               │         │  • compute: MVs (aggregation)        │
└──────────────────────────┘         │  • serving: indexes (queries)        │
                                     │  CREATE SINK: Avro/Debezium → Kafka  │
                                     └────────────┬────────────────────────┘
                                                  │ CREATE SINK
                                                  │ (Avro/Debezium)
                                     ┌────────────▼────────────────────────┐
                                     │    Redpanda                          │
                                     │  Broker: 19092  SchemaReg: 18081     │
                                     │  • topic: orders                     │
                                     │  • topic: inventory                  │
                                     └────────────┬────────────────────────┘
                                                  │ consume
                                                  ▼
                                     ┌────────────────────────────────────┐
                                     │    Kafka Connect    Port: 8083       │
                                     │  Aiven OpenSearch sink connector     │
                                     │  • embedding SMT (orders) ──────────▶│ embedding-service :8085
                                     │  • Debezium unwrap / cast / tsHeader │
                                     │  • UPSERT, null → delete             │
                                     │  • < 2s latency                      │
                                     └────────────┬────────────────────────┘
                                                  │ Bulk index (UPSERT)
                                                  ▼
                    ┌─────────────────────────────────────┐
                    │      OpenSearch                     │
           ┌───────▶│       Port: 9200                    │
           │        │  • orders index (real-time)         │
           │        │  • inventory index (real-time)      │
           │        │  • Full-text + kNN vector search    │
           │        └─────────────────────────────────────┘
           │
┌──────────┴───────────────┐
│    LangGraph Agents       │
│      Port: 8081           │
│  • search_orders  ────────┘ (search orders index)
│  • search_inventory ─────┘ (search inventory index)
│  • fetch_order_context ─────▶ Graph API (read triples)
│  • write_triples ───────────▶ Graph API (write triples → PostgreSQL)
└──────────────────────────┘
```

## Automatic Reconnection & Resilience

The `zero-server` service includes automatic retry and reconnection logic for its
SUBSCRIBE streams. (The search-indexing path is now handled by Kafka Connect, which
manages connector retries and offset-based recovery itself.)

### Connection Retry

Services start even if Materialize is not ready:

- Automatically retry connection every 30 seconds until successful
- No manual intervention needed when Materialize is initializing
- Services log retry attempts for monitoring

**Startup sequence:**
```
[zero-server] Attempting connection to Materialize... (attempt 1)
[zero-server] Connection refused, retrying in 30s
[zero-server] Attempting connection to Materialize... (attempt 2)
[zero-server] Connected successfully!
```

### Stream Reconnection

If a SUBSCRIBE stream ends or errors, services automatically reconnect:

- Handles network interruptions and Materialize restarts gracefully
- Each view maintains its own reconnection loop independently
- Re-establishes SUBSCRIBE without data loss

**Reconnection flow:**
```
[orders_flat_mv] SUBSCRIBE stream ended (connection lost)
[orders_flat_mv] Retrying connection... (attempt 1)
[orders_flat_mv] Re-hydrating from current state...
[orders_flat_mv] SUBSCRIBE stream re-established
```

### Configuration

**zero-server**: Fixed 30-second retry delay per subscription

**Search indexing (Kafka Connect)**: Connector retry and recovery are managed by the
Kafka Connect runtime via consumer offsets — failed tasks resume from the last
committed offset, so no application-level backoff configuration is required.

### Benefits

- **Start services in any order** - they'll connect when ready
- **No manual restarts** - if Materialize restarts, services automatically reconnect
- **Continuous real-time updates** - even after connection issues
- **Production-ready** - handles network interruptions gracefully

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL - primary triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **zero-server** | 8090 | WebSocket server for real-time UI updates |
| **opensearch** | 9200 | Search engine for orders |
| **api** | 8080 | FastAPI backend |
| **redpanda** | 19092/18081 | Kafka broker + Schema Registry (Materialize sink target) |
| **kafka-connect** | 8083 | Kafka Connect (OpenSearch sink + embedding SMT) |
| **embedding-service** | 8085 | OpenAI-compatible embedding facade (BAAI/bge-small-en-v1.5) |
| **web** | 5173 | React admin UI with real-time updates |
| **agents** | 8081 | LangGraph agent runner (optional) |

## See Also

- [Operations Guide](OPERATIONS.md) - Service management and troubleshooting
- [Ontology Guide](ONTOLOGY_GUIDE.md) - Adding new entity types and views
- [API Reference](API_REFERENCE.md) - Complete API documentation
- [UI Guide](UI_GUIDE.md) - Dashboard features and real-time UI
- [Agents Guide](AGENTS.md) - AI agent setup and usage
