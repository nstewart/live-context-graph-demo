# OpenSearch Sync Operations Runbook

## Overview

This runbook provides operational guidance for the OpenSearch search-ingest pipeline. Search indexing is driven by a Materialize Kafka sink plus a Kafka Connect pipeline that streams CDC changes from Materialize into the `orders` and `inventory` OpenSearch indices.

### Architecture Summary

**Data Flow**:
```
PostgreSQL → Materialize (CDC) → CREATE SINK (Avro/Debezium) → Redpanda topics → Kafka Connect (sink + SMTs) → OpenSearch
   (source)     (real-time)        (orders / inventory)         (orders/inventory)     (transform + index)        (index)
```

**Key Components**:
- **Materialize sinks**: `orders_sink` (from `orders_with_lines_mv`, key `order_id`) and `inventory_sink` (from `inventory_items_with_dynamic_pricing_mv`, key `inventory_id`). Both `FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY ... ENVELOPE DEBEZIUM`, in cluster `serving`.
- **Redpanda**: Kafka broker (internal `redpanda:9092`, external host port `19092`) plus Confluent-compatible Schema Registry (internal `redpanda:8081`, external `18081`). Carries the `orders` and `inventory` topics.
- **Kafka Connect** (`kafka-connect`): Connect runtime, REST API on `:8083`. Custom image (`kafka-connect/Dockerfile`) bundles the Aiven OpenSearch sink connector (`io.aiven.kafka.connect.opensearch.OpensearchSinkConnector`), the embedding SMT, and the Debezium transforms.
- **embedding-service**: OpenAI-compatible facade (`POST /v1/embeddings`) over a local fastembed `BAAI/bge-small-en-v1.5` model (384-dim) on `:8085`, served by Hypercorn. Used by both ingest (the embedding SMT) and query time (the `api` service).
- **connect-init**: one-shot bootstrap that applies the OpenSearch index templates (`kafka-connect/opensearch-templates/orders.json`, `inventory.json`), pre-creates the `orders`/`inventory` indices (the Aiven connector's auto-create bypasses composable templates), then registers the two sink connectors (`kafka-connect/connectors/`).
- **OpenSearch**: `orders` and `inventory` indices. The `orders` index has a `knn_vector` field `embedding_text_embedding` (dim 384) for semantic search.

**Sink connectors and transform chains**:
- `orders-opensearch-sink` (topic `orders`): `extractKey` (ExtractField$Key `order_id`) → `embed` (EmbeddingDiffTransform: diffs the Debezium before/after, calls embedding-service only when the `embedding_text` column changed, writes vector field `embedding_text_embedding`) → `cast` (Cast$Value: `order_total_amount`/`computed_total`/`total_weight_kg` → float64) → `tsHeader` (Debezium HeaderToValue: copies the Kafka header `materialize-timestamp` into doc field `mz_timestamp`).
- `inventory-opensearch-sink` (topic `inventory`): `extractKey` (`inventory_id`) → `unwrap` (ExtractField$Value `after`) → `cast` (the decimal pricing fields → float64) → `tsHeader`. No embedding (inventory is text-only).
- Both connectors: `key.ignore=false`, `schema.ignore=true`, `index.write.method=UPSERT`, `behavior.on.null.values=delete` (CDC deletes become tombstones → doc deleted), `behavior.on.version.conflict=ignore`, Avro converters pointed at `http://redpanda:8081`.

**Re-embedding**: handled entirely by the `embed` SMT, which diffs the Debezium before/after image and only calls the embedding service when `embedding_text` actually changed. There is no separate hash/dedup cache.

**Performance Characteristics**:
- **Latency**: typically a few seconds end-to-end (PostgreSQL write → searchable in OpenSearch), gated by Materialize compute, Connect poll/flush, and embedding latency for changed orders.
- **Recovery**: Connect tasks are restartable; consumer offsets are tracked per connector consumer group, so a restarted task resumes where it left off. Upserts are idempotent, so replays are safe.

---

## 1. Monitoring

### Health Checks

The pipeline has no bespoke HTTP health endpoint for sync; monitor it through Connect's REST API, Materialize sink statuses, and container health.

**Check containers are running**:
```bash
docker compose ps redpanda kafka-connect embedding-service opensearch
# All should show "Up" (kafka-connect and embedding-service report (healthy))
```

**Check connectors are registered and running**:
```bash
curl -s localhost:8083/connectors
# Expected: ["orders-opensearch-sink","inventory-opensearch-sink"]

curl -s localhost:8083/connectors/orders-opensearch-sink/status   | jq
curl -s localhost:8083/connectors/inventory-opensearch-sink/status | jq
# connector.state and every tasks[].state should be "RUNNING"
```

**Check the Materialize sinks are healthy**:
```bash
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
  "SELECT name, status, error FROM mz_internal.mz_sink_statuses;"
# orders_sink / inventory_sink should be status = running, error = NULL
```

**Check the embedding service**:
```bash
curl -s localhost:8085/health
# Used by both ingest (the SMT) and query-time (the api).
```

### Key Signals to Monitor

#### 1. End-to-end freshness

**Definition**: Time from a PostgreSQL/Materialize write to the document being searchable in OpenSearch.

**How to Measure**:
```bash
# Create a test order via the app, then poll OpenSearch for it.
START=$(date +%s)
# ... POST an order through the application API ...
while ! curl -s "http://localhost:9200/orders/_search?q=order_number:TEST-$START" | grep -q "TEST-$START"; do
  sleep 0.5
done
END=$(date +%s)
echo "Latency: $((END - START)) seconds"
```

**Alert Threshold**: freshness consistently > 10 seconds while there is write activity.

#### 2. Connector consumer-group lag

**Definition**: How far behind the sink connector is on its source topic. This is the modern equivalent of the old in-process "buffer size" — backpressure now shows up as growing consumer lag, not an in-memory queue.

**How to Measure**:
```bash
# Each connector runs its own consumer group named connect-<connector-name>.
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
docker compose exec redpanda rpk group describe connect-inventory-opensearch-sink
# Watch the LAG column. Steady, near-zero lag is healthy; persistently growing lag
# means OpenSearch / the embedding service can't keep up with the topic.
```

**Alert Threshold**: lag continuously increasing for > 5 minutes.

#### 3. Task failures / errors

**Definition**: A Connect task transitioning to `FAILED`, or repeated errors in the Connect log.

**How to Measure**:
```bash
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks[].state'
docker compose logs --since 1h kafka-connect | grep -iE "error|exception|failed" | wc -l
```

**Alert Threshold**: any task in `FAILED` state, or a sustained error rate in the logs.

#### 4. Embedding service health

**Definition**: The SMT calls embedding-service over HTTP/2 on every order whose `embedding_text` changed. If it is down or slow, the orders connector task stalls or fails.

**How to Measure**:
```bash
curl -s localhost:8085/health
docker compose logs --since 15m embedding-service | grep -iE "error|timeout"
```

### Log Patterns

Watch the three services that make up the pipeline:
```bash
docker compose logs -f kafka-connect      # connector tasks, SMTs, OpenSearch writes
docker compose logs -f embedding-service   # embedding requests from the SMT and the api
docker compose logs -f connect-init        # one-shot bootstrap (templates + connector registration)
```

#### Healthy State
```log
# connect-init
Applying OpenSearch index templates...
  applied template: orders
  ensured index: orders
  applied template: inventory
  ensured index: inventory
Registering sink connectors...
  -> orders-opensearch-sink
  -> inventory-opensearch-sink
Pipeline bootstrap complete.

# kafka-connect
INFO ... task RUNNING (orders-opensearch-sink-0)
INFO ... task RUNNING (inventory-opensearch-sink-0)
```

#### Unhealthy State
```log
ERROR WorkerSinkTask{id=orders-opensearch-sink-0} Task threw an uncaught and unrecoverable exception ...
ERROR ... Connection refused: opensearch:9200
ERROR ... failed to call embedding endpoint http://embedding-service:8085/v1/embeddings
WARN  ... Schema registry request failed: redpanda:8081
```

> Observability comes from the Connect REST API, `rpk group describe`, and `mz_internal.mz_sink_statuses` — see the probes below.

---

## 2. Common Operations

### Starting the Pipeline

```bash
# Bring up the infra and ingest pipeline
docker compose up -d redpanda opensearch embedding-service kafka-connect connect-init

# Watch bootstrap finish
docker compose logs -f connect-init
# Wait for "Pipeline bootstrap complete."

# Confirm connectors are running
curl -s localhost:8083/connectors
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.connector.state'

# Confirm documents are flowing
curl -s localhost:9200/orders/_count
curl -s localhost:9200/inventory/_count
```

**Startup Sequence**:
1. Materialize creates `orders_sink`/`inventory_sink`, publishing CDC to the `orders`/`inventory` Redpanda topics (Avro + Debezium envelope).
2. `connect-init` applies the OpenSearch index templates and pre-creates both indices.
3. `connect-init` registers the two sink connectors via the Connect REST API.
4. Each connector consumes its topic from the beginning, applies its SMT chain, and upserts into OpenSearch.

### Stopping the Pipeline

```bash
# Stopping kafka-connect halts ingest; offsets are committed so it resumes on restart.
docker compose stop kafka-connect

# The sinks in Materialize keep producing to the topics regardless; Redpanda buffers them.
```

### Restarting the Pipeline

```bash
# Restart the Connect runtime (does not lose offsets)
docker compose restart kafka-connect

# Restart a single failed connector/task without restarting the runtime
curl -X POST localhost:8083/connectors/orders-opensearch-sink/restart?includeTasks=true
curl -X POST localhost:8083/connectors/inventory-opensearch-sink/restart?includeTasks=true
```

### Re-registering / Updating a Connector

```bash
# Connector configs live in kafka-connect/connectors/. Re-applying is idempotent.
curl -X PUT localhost:8083/connectors/orders-opensearch-sink/config \
  -H 'Content-Type: application/json' \
  --data-binary @kafka-connect/connectors/orders-opensearch-sink.json

# Or just re-run the one-shot bootstrap (applies templates + re-registers both connectors):
docker compose up connect-init
```

### Checking Sync Status / Consistency

```bash
# Compare Materialize row counts to OpenSearch doc counts.
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SELECT COUNT(*) FROM orders_with_lines_mv;"
curl -s 'http://localhost:9200/orders/_count' | jq '.count'

PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SELECT COUNT(*) FROM inventory_items_with_dynamic_pricing_mv;"
curl -s 'http://localhost:9200/inventory/_count' | jq '.count'
# Counts should match within in-flight drift (< consumer lag).
```

### Inspecting the Topics

```bash
docker compose exec redpanda rpk topic list
docker compose exec redpanda rpk topic consume orders    -n 1
docker compose exec redpanda rpk topic consume inventory -n 1
# Note the Debezium envelope (before/after) and the materialize-timestamp header.
```

### Inspecting OpenSearch Mappings

```bash
curl -s localhost:9200/orders/_mapping    | jq
curl -s localhost:9200/inventory/_mapping | jq
# orders should show embedding_text_embedding as knn_vector (dimension 384) and mz_timestamp.
```

---

## 3. Troubleshooting Guide

### Issue: Connector or task is FAILED

**Symptoms**:
```bash
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq
# .tasks[].state == "FAILED" with a trace in .tasks[].trace
```

**Possible Causes**:
1. OpenSearch unreachable or unhealthy.
2. embedding-service down/slow (orders connector only).
3. Schema Registry (`redpanda:8081`) unavailable, so Avro deserialization fails.
4. A mapping conflict in OpenSearch.

**Resolution Steps**:
1. Read the failing task's trace:
   ```bash
   curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq -r '.tasks[].trace'
   ```
2. Check the dependencies the trace points at:
   ```bash
   curl -s localhost:9200/_cluster/health | jq '.status'
   curl -s localhost:8085/health
   curl -s localhost:18081/subjects     # Schema Registry (external port)
   ```
3. Once the dependency is healthy, restart the task:
   ```bash
   curl -X POST localhost:8083/connectors/orders-opensearch-sink/restart?includeTasks=true
   ```

**Expected Recovery**: task returns to `RUNNING` and consumer lag drains.

---

### Issue: Slow Sync / Growing Consumer Lag

**Symptoms**:
- Documents take a long time to appear; `rpk group describe` shows growing `LAG`.

**Possible Causes**:
1. OpenSearch indexing pressure.
2. embedding-service latency (every changed `embedding_text` triggers a synchronous embedding call).
3. Materialize compute lag upstream of the sink.

**Resolution Steps**:
1. Check lag per connector:
   ```bash
   docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
   ```
2. Check OpenSearch health and indexing stats:
   ```bash
   curl -s localhost:9200/_cluster/health | jq '.status'
   curl -s localhost:9200/_nodes/stats/indices/indexing | jq '.nodes[].indices.indexing'
   ```
3. Check embedding latency:
   ```bash
   docker compose logs --since 10m embedding-service | tail -50
   ```
4. Check the Materialize sink isn't stalled:
   ```bash
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
     "SELECT name, status, error FROM mz_internal.mz_sink_statuses;"
   ```

**Expected Recovery**: lag trends back toward zero once the bottleneck clears.

---

### Issue: OpenSearch Index Drift

**Symptoms**:
- Document count mismatch between a Materialize view and its OpenSearch index.
- Missing or stale documents in search results.

**Possible Causes**:
1. Connector was stopped/failed and has not caught up (check lag first).
2. A doc was indexed with an unexpected mapping (e.g. index created without the template).
3. A Debezium tombstone wasn't applied (delete not propagated).

**Resolution Steps**:
1. Confirm it isn't just lag:
   ```bash
   docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
   ```
2. Compare counts (see "Checking Sync Status" above).
3. Spot-check a specific key:
   ```bash
   curl -s "http://localhost:9200/orders/_doc/<order_id>" | jq '.found, ._source.mz_timestamp'
   ```
4. If genuine drift, reseed the index (see Disaster Recovery → Force Resync).

---

### Issue: Wrong Mapping (vector field is a plain float array, dates wrong)

**Symptoms**:
- kNN search fails, or `embedding_text_embedding` is mapped as `float[]` instead of `knn_vector`.

**Cause**: The index was auto-created by the Aiven connector instead of from the composable template (the connector's auto-create bypasses templates). `connect-init` pre-creates the indices precisely to avoid this.

**Resolution**: delete and recreate the index from the template, then let the connector backfill (see Force Resync).

---

## 4. Disaster Recovery

### Procedure: Force Resync (rebuild an index)

**When to Use**: significant drift, wrong mapping, or corruption.

**Steps** (example for `orders`; substitute `inventory` as needed):

1. **Pause ingest** for that index:
   ```bash
   curl -X PUT localhost:8083/connectors/orders-opensearch-sink/pause
   ```

2. **Delete the index**:
   ```bash
   curl -X DELETE http://localhost:9200/orders
   ```

3. **Recreate it from the template** (re-running connect-init applies templates and pre-creates indices):
   ```bash
   docker compose up connect-init
   # or manually:
   curl -X PUT "http://localhost:9200/_index_template/orders_template" \
     -H 'Content-Type: application/json' \
     --data-binary @kafka-connect/opensearch-templates/orders.json
   curl -X PUT "http://localhost:9200/orders"
   ```

4. **Replay the topic** by resetting the connector's consumer offsets so it re-reads from the beginning:
   ```bash
   # Stop the connector first so the group has no active members.
   curl -X PUT localhost:8083/connectors/orders-opensearch-sink/stop
   docker compose exec redpanda rpk group seek connect-orders-opensearch-sink --to start
   curl -X PUT localhost:8083/connectors/orders-opensearch-sink/resume
   ```
   Upserts are idempotent and `embedding_text` diffing still applies, so replays converge to the correct state. (If the topic's retention has dropped older records, restart the Materialize sink to re-emit a fresh snapshot instead.)

5. **Verify counts** (see "Checking Sync Status").

---

### Procedure: Rebuild the Whole Search Layer

**When to Use**: schema changes to a template, or full reset.

```bash
# 1. Remove connectors and indices
curl -X DELETE localhost:8083/connectors/orders-opensearch-sink
curl -X DELETE localhost:8083/connectors/inventory-opensearch-sink
curl -X DELETE http://localhost:9200/orders
curl -X DELETE http://localhost:9200/inventory

# 2. (If template changed) edit kafka-connect/opensearch-templates/*.json

# 3. Re-run the one-shot bootstrap: applies templates, pre-creates indices, re-registers connectors
docker compose up connect-init

# 4. Verify
curl -s localhost:8083/connectors
curl -s localhost:9200/orders/_count
```

---

## 5. Configuration Reference

### Materialize sinks (`db/materialize/init.sh`)

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

### Connector configs (`kafka-connect/connectors/`)

| Setting | orders-opensearch-sink | inventory-opensearch-sink |
|---|---|---|
| `topics` | `orders` | `inventory` |
| `connection.url` | `http://opensearch:9200` | `http://opensearch:9200` |
| `key.converter` / `value.converter` | Avro (`http://redpanda:8081`) | Avro (`http://redpanda:8081`) |
| `key.ignore` | `false` | `false` |
| `schema.ignore` | `true` | `true` |
| `index.write.method` | `UPSERT` | `UPSERT` |
| `behavior.on.null.values` | `delete` | `delete` |
| `behavior.on.version.conflict` | `ignore` | `ignore` |
| `transforms` | `extractKey,embed,cast,tsHeader` | `extractKey,unwrap,cast,tsHeader` |

The embedding SMT (`orders` only):
```
transforms.embed.type              = com.materialize.connect.smt.embedding.EmbeddingDiffTransform
transforms.embed.embedded.columns  = embedding_text
transforms.embed.provider          = openai
transforms.embed.openai.endpoint   = http://embedding-service:8085/v1/embeddings
transforms.embed.openai.model      = bge-small
```

The timestamp header SMT (both):
```
transforms.tsHeader.type      = io.debezium.transforms.HeaderToValue
transforms.tsHeader.headers   = materialize-timestamp   # epoch millis Kafka header
transforms.tsHeader.fields    = mz_timestamp            # destination doc field
transforms.tsHeader.operation = copy
```

> `mz_timestamp` (consumed by `GET /api/search/impact`) is derived from the `materialize-timestamp` Kafka header via this HeaderToValue transform — not computed in any sync worker.

### Service endpoints

| Service | Internal | External (host) |
|---|---|---|
| Redpanda broker | `redpanda:9092` | `localhost:19092` |
| Redpanda Schema Registry | `redpanda:8081` | `localhost:18081` |
| Kafka Connect REST | `kafka-connect:8083` | `localhost:8083` |
| embedding-service | `embedding-service:8085` | `localhost:8085` |
| OpenSearch | `opensearch:9200` | `localhost:9200` |

---

## 6. Query-Time Path (for context)

Search reads do **not** go through the connectors. The `api` service:
1. Embeds the user query by calling embedding-service `POST /v1/embeddings` (same model the SMT uses, so vectors are comparable).
2. Runs an OpenSearch kNN search on `embedding_text_embedding`.
3. Hydrates live order data — including `line_items` with live pricing — from Materialize `orders_with_lines_mv`.

This matters operationally: a degraded embedding-service breaks **both** ingest (the SMT) and query-time search.

---

## 7. Related Documentation

- **Implementation doc**: `OPENSEARCH_SINK_IMPLEMENTATION.md`
- **Connector configs**: `kafka-connect/connectors/orders-opensearch-sink.json`, `kafka-connect/connectors/inventory-opensearch-sink.json`
- **Index templates**: `kafka-connect/opensearch-templates/orders.json`, `inventory.json`
- **Bootstrap**: `kafka-connect/init.sh`, `kafka-connect/Dockerfile`
- **Sink DDL**: `db/materialize/init.sh`
- **Materialize Kafka sink docs**: https://materialize.com/docs/sql/create-sink/kafka/

---

## 8. Incident Response Template

**Incident Title**: [e.g., "orders-opensearch-sink task FAILED"]

**Detected**: [timestamp]

**Severity**: [P0-Critical / P1-High / P2-Medium / P3-Low]

**Symptoms**:
- [Connector status, consumer lag, log lines, user reports]

**Impact**:
- [e.g., "Search results stale", "kNN search returning errors"]

**Timeline**:
- [HH:MM] Incident detected
- [HH:MM] Investigation started
- [HH:MM] Root cause identified
- [HH:MM] Mitigation applied
- [HH:MM] Service restored

**Root Cause**:
- [Technical explanation]

**Resolution**:
- [Steps taken]

**Prevention**:
- [Changes / monitoring improvements]

**Action Items**:
- [ ] [Task] (Owner, Due Date)

---

## Contact

For questions or issues not covered in this runbook:
- **Slack**: #data-infrastructure
- **On-call**: PagerDuty rotation
- **Escalation**: Platform Engineering Team Lead
