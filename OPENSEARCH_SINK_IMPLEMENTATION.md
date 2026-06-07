# OpenSearch Search-Ingest Pipeline Implementation

## Summary

Materialize publishes two materialized views to Redpanda as Avro/Debezium CDC sinks. Kafka Connect consumes those topics and, via a chain of Single Message Transforms (SMTs), upserts documents into the `orders` and `inventory` OpenSearch indices. Order documents are enriched with a semantic embedding vector. There is no bespoke sync process — the moving parts are declarative Materialize sinks and declarative Connect connector configs.

## Architecture

```
PostgreSQL → Materialize (CDC) → CREATE SINK (Avro/Debezium) → Redpanda → Kafka Connect (sink + SMTs) → OpenSearch
```

```
┌────────────────────────────────────────┐         ┌──────────────────────────┐
│ Materialize (cluster: serving)          │         │ Redpanda                 │
│  orders_with_lines_mv ── orders_sink ───┼────────▶│  topic: orders           │
│  inventory_items_with_                  │ Avro /  │  topic: inventory        │
│    dynamic_pricing_mv ── inventory_sink ┼────────▶│  (Confluent SR @ :8081)  │
└────────────────────────────────────────┘ Debezium└─────────────┬────────────┘
                                                                  │
                                                                  ▼
                                              ┌───────────────────────────────────┐
                                              │ Kafka Connect (:8083)              │
                                              │  orders-opensearch-sink            │
                                              │    extractKey→embed→cast→tsHeader  │
                                              │  inventory-opensearch-sink         │
                                              │    extractKey→unwrap→cast→tsHeader │
                                              └─────────┬───────────────┬──────────┘
                                                        │               │ (orders only)
                                                        ▼               ▼
                                          ┌──────────────────┐  ┌───────────────────────┐
                                          │ OpenSearch       │  │ embedding-service      │
                                          │  orders index    │  │  POST /v1/embeddings   │
                                          │  inventory index │  │  bge-small-en (384d)   │
                                          └──────────────────┘  └───────────────────────┘
```

## Components

### 1. Materialize sinks (`db/materialize/init.sh`)

Two `CREATE SINK` statements in cluster `serving` publish CDC to Redpanda:

```sql
CREATE SINK IF NOT EXISTS orders_sink
    IN CLUSTER serving
    FROM orders_with_lines_mv
    INTO KAFKA CONNECTION kafka_conn (TOPIC 'orders')
    KEY (order_id) NOT ENFORCED
    FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY CONNECTION csr_conn
    ENVELOPE DEBEZIUM;

CREATE SINK IF NOT EXISTS inventory_sink
    IN CLUSTER serving
    FROM inventory_items_with_dynamic_pricing_mv
    INTO KAFKA CONNECTION kafka_conn (TOPIC 'inventory')
    KEY (inventory_id) NOT ENFORCED
    FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY CONNECTION csr_conn
    ENVELOPE DEBEZIUM;
```

- **`ENVELOPE DEBEZIUM`**: each record carries a `before`/`after` image. The connectors use this for both delete handling (null/tombstone → doc delete) and, for orders, the before/after diff that gates re-embedding.
- **Avro + Confluent Schema Registry**: schemas are registered in Redpanda's Schema Registry (`redpanda:8081`); the connectors deserialize with matching Avro converters.
- **`KEY (...)`**: keys the Kafka record by `order_id` / `inventory_id`, which the connectors extract for the OpenSearch document ID.
- **`materialize-timestamp` header**: Materialize attaches its logical timestamp as a Kafka header on every record; the connectors copy it into the document.

### 2. Redpanda

Single broker + Confluent-compatible Schema Registry:
- Broker: internal `redpanda:9092`, external host port `19092`.
- Schema Registry: internal `redpanda:8081`, external `18081`.

Topics `orders` and `inventory` carry the sink output.

### 3. Kafka Connect (`kafka-connect/Dockerfile`)

Connect runtime on REST port `:8083`. The custom image bundles:
- The **Aiven OpenSearch sink connector** (`io.aiven.kafka.connect.opensearch.OpensearchSinkConnector`).
- The **embedding SMT** (`com.materialize.connect.smt.embedding.EmbeddingDiffTransform`).
- The **Debezium transforms** (`io.debezium.transforms.HeaderToValue`, etc.).

#### orders-opensearch-sink (`kafka-connect/connectors/orders-opensearch-sink.json`)

Transform chain `extractKey → embed → cast → tsHeader`:
1. **extractKey** (`ExtractField$Key`, field `order_id`) — sets the OpenSearch document ID from the Kafka key.
2. **embed** (`EmbeddingDiffTransform`) — diffs the Debezium `before`/`after` and calls the embedding service **only when the `embedding_text` column changed**, writing the result to vector field `embedding_text_embedding` (knn_vector, dim 384). Re-embedding is gated by an actual value diff, in-stream, with no external cache — a price- or status-only change does not recompute the vector.
3. **cast** (`Cast$Value`) — casts decimal fields `order_total_amount`, `computed_total`, `total_weight_kg` to `float64` so OpenSearch maps them as numbers.
4. **tsHeader** (`HeaderToValue`) — copies the `materialize-timestamp` Kafka header into doc field `mz_timestamp`.

#### inventory-opensearch-sink (`kafka-connect/connectors/inventory-opensearch-sink.json`)

Transform chain `extractKey → unwrap → cast → tsHeader`:
1. **extractKey** (`ExtractField$Key`, field `inventory_id`).
2. **unwrap** (`ExtractField$Value`, field `after`) — takes the Debezium `after` image as the document body.
3. **cast** (`Cast$Value`) — casts the decimal pricing fields (`base_price`, `live_price`, `price_change`, `zone_adjustment`, `perishable_adjustment`, `local_stock_adjustment`, `popularity_adjustment`, `scarcity_adjustment`, `demand_multiplier`, `demand_premium`, `basket_adjustment`) to `float64`.
4. **tsHeader** (`HeaderToValue`) — copies `materialize-timestamp` → `mz_timestamp`.

There is **no embedding** for inventory — it is text-only.

#### Shared connector settings (both)

| Setting | Value | Why |
|---|---|---|
| `key.ignore` | `false` | Use the Kafka key (`order_id` / `inventory_id`) as the doc ID. |
| `schema.ignore` | `true` | Don't let the connector create mappings; the index templates own the mapping (so `embedding_text_embedding` is a `knn_vector`, dates are correct). |
| `index.write.method` | `UPSERT` | Idempotent writes; safe to replay. |
| `behavior.on.null.values` | `delete` | A CDC delete is a Debezium tombstone (null value) → delete the OpenSearch doc. |
| `behavior.on.version.conflict` | `ignore` | Tolerate out-of-order/duplicate deliveries. |
| Avro converters | `http://redpanda:8081` | Key and value deserialized against the Schema Registry. |

### 4. embedding-service (`embedding-service/`)

An OpenAI-compatible facade exposing `POST /v1/embeddings` over a local **fastembed `BAAI/bge-small-en-v1.5`** model (384-dim) on port `:8085`. Served by **Hypercorn** (the embedding SMT uses an HTTP/2 client, which Hypercorn handles). Used by **both** sides of the system:
- **Ingest**: the orders SMT embeds `embedding_text` for changed orders.
- **Query-time**: the `api` service embeds the user's query before the kNN search.

Because the same model is used on both sides, the query vector and the document vectors live in the same space.

### 5. connect-init (one-shot bootstrap, `kafka-connect/init.sh`)

Runs once at startup and is idempotent:
1. **Applies the OpenSearch index templates** (`kafka-connect/opensearch-templates/orders.json`, `inventory.json`).
2. **Pre-creates the `orders` and `inventory` indices.** The Aiven connector's own auto-create bypasses composable index templates (it would land a default/dynamic mapping — wrong date format, a plain float array instead of `knn_vector`), so the indices are created explicitly here so they pick up the template mapping.
3. **Registers the two sink connectors** via `PUT /connectors/<name>/config` (idempotent).

### 6. Query-time path (`api/`)

Search reads bypass the connectors entirely:
1. The `api` service embeds the query via embedding-service `POST /v1/embeddings`.
2. It runs an OpenSearch kNN search on `embedding_text_embedding`.
3. It hydrates live order data — including `line_items` with live pricing — from Materialize `orders_with_lines_mv`.

`GET /api/search/impact` reads `mz_timestamp` from the indexed documents, which originates from the `materialize-timestamp` Kafka header (copied in by the `tsHeader` SMT).

## Design Decisions

- **Declarative, not a worker.** Ingest is two `CREATE SINK` statements and two connector JSON files. There is no long-running Python process to babysit, no in-process buffer, no exponential-backoff reconnect loop — Connect owns retries and offset management.
- **Idempotent upserts + keyed records.** Document IDs come from the Kafka key, writes are UPSERTs, and version conflicts are ignored, so replays and out-of-order delivery converge to the correct state.
- **Re-embed only on change.** The `EmbeddingDiffTransform` compares the Debezium before/after `embedding_text` and calls the embedding service only when it changed — avoiding redundant embedding calls without a separate hash cache.
- **CDC deletes via tombstones.** `ENVELOPE DEBEZIUM` + `behavior.on.null.values=delete` turns a deleted row into a deleted OpenSearch document automatically.
- **Templates own the mapping.** `schema.ignore=true` plus pre-created indices keep the `knn_vector` and date mappings under our control rather than the connector's dynamic mapping.
- **Backpressure is consumer lag.** If OpenSearch or the embedding service slows down, the effect is growing consumer-group lag on the connector, not unbounded in-memory buffering. Lag is observable via `rpk group describe connect-<connector>`.

## Operating the Pipeline

### Bring-up
```bash
docker compose up -d redpanda opensearch embedding-service kafka-connect connect-init
docker compose logs -f connect-init          # wait for "Pipeline bootstrap complete."
curl -s localhost:8083/connectors             # ["orders-opensearch-sink","inventory-opensearch-sink"]
```

### Health
```bash
# Connector / task state
curl -s localhost:8083/connectors/orders-opensearch-sink/status   | jq
curl -s localhost:8083/connectors/inventory-opensearch-sink/status | jq

# Materialize sink health
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
  "SELECT name, status, error FROM mz_internal.mz_sink_statuses;"

# Consumer lag (backpressure signal)
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink

# Indexed doc counts
curl -s localhost:9200/orders/_count
curl -s localhost:9200/inventory/_count
```

### Logs
```bash
docker compose logs -f kafka-connect
docker compose logs -f embedding-service
docker compose logs -f connect-init
```

### Restart a failed task
```bash
curl -X POST localhost:8083/connectors/orders-opensearch-sink/restart?includeTasks=true
```

### Inspect topics
```bash
docker compose exec redpanda rpk topic list
docker compose exec redpanda rpk topic consume orders -n 1   # Debezium envelope + materialize-timestamp header
```

## Testing the Implementation

### Quick validation
```bash
# 1. Start
docker compose up -d redpanda opensearch embedding-service kafka-connect connect-init

# 2. Connectors running
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.connector.state, .tasks[].state'

# 3. Create / update an order through the application; then confirm it indexes
curl -s 'http://localhost:9200/orders/_search?q=order_number:FM-1234' | jq '.hits.total.value'

# 4. Confirm the embedding field exists and is a knn_vector
curl -s localhost:9200/orders/_mapping | jq '.orders.mappings.properties.embedding_text_embedding'

# 5. Confirm mz_timestamp landed
curl -s "http://localhost:9200/orders/_doc/<order_id>" | jq '._source.mz_timestamp'
```

### Delete propagation
```bash
# Deleting a row upstream produces a Debezium tombstone; the doc should disappear.
curl -s "http://localhost:9200/orders/_doc/<deleted_order_id>" | jq '.found'   # false
```

### Re-embed gating
```bash
# Update a non-embedding field on an order and confirm no embedding call fires;
# update embedding_text and confirm exactly one embedding request appears.
docker compose logs --since 1m embedding-service
```

## References

### Implementation files
- `db/materialize/init.sh` — `orders_sink` / `inventory_sink` DDL and the source materialized views.
- `kafka-connect/Dockerfile` — Connect image bundling the Aiven sink connector, embedding SMT, and Debezium transforms.
- `kafka-connect/init.sh` — one-shot bootstrap (templates, index pre-creation, connector registration).
- `kafka-connect/connectors/orders-opensearch-sink.json` — orders connector + SMT chain.
- `kafka-connect/connectors/inventory-opensearch-sink.json` — inventory connector + SMT chain.
- `kafka-connect/opensearch-templates/orders.json`, `inventory.json` — index templates (knn_vector, date formats).
- `embedding-service/` — OpenAI-compatible embedding facade (Hypercorn + fastembed bge-small).
- `api/` — query-time embedding + kNN search + live hydration from `orders_with_lines_mv`.

### Docs
- Operations runbook: `docs/OPENSEARCH_SYNC_RUNBOOK.md`
- Materialize Kafka sink: https://materialize.com/docs/sql/create-sink/kafka/
- Aiven OpenSearch sink connector: https://github.com/Aiven-Open/opensearch-connector-for-apache-kafka
