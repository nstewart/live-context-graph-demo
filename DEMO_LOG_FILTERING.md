# Demo: Observing the Search Pipeline

This guide shows how to watch the ingest pipeline that keeps OpenSearch in sync
with Materialize, and how to prove that writes propagate end-to-end.

> **The pipeline:**
>
> ```
> Materialize CREATE SINK (Avro, ENVELOPE DEBEZIUM)
>     → Redpanda topics `orders` / `inventory`
>     → Kafka Connect (service `kafka-connect`, REST :8083)
>         → embedding SMT → embedding-service (:8085, OpenAI-compatible)
>     → OpenSearch indices `orders` / `inventory`
> ```
>
> Kafka Connect emits standard log4j lines (`WorkerSinkTask`, `BulkProcessor`,
> `Committing offsets`, ...). For observing propagation and throughput, prefer
> the REST/CLI probes in the sections below over log grepping — they are exact,
> not best-effort pattern matches.

## Quick Start

Run the automated demo:
```bash
./demo-transaction-logs.sh
```

## Manual Filtering Examples

### 1. Watch Sink Connector Activity
```bash
docker compose logs -f kafka-connect | grep -iE "WorkerSinkTask|BulkProcessor|ERROR|RUNNING|FAILED"
```

**What it shows:** The sink tasks consuming from Redpanda and bulk-writing to
OpenSearch. `WorkerSinkTask` lines mark poll/commit cycles, `BulkProcessor`
lines mark batched writes, and `RUNNING`/`FAILED`/`ERROR` surface task health.

---

### 2. Watch Embedding Requests
```bash
docker compose logs -f embedding-service | grep "POST /v1/embeddings"
```

**What it shows:** The orders connector's embedding SMT calling the
`embedding-service` (fastembed `bge-small`, 384-dim) for each changed document's
`embedding_text`. One request line per batch the SMT embeds.

---

### 3. Check Connector / Task State (preferred over logs)
```bash
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq
curl -s localhost:8083/connectors/inventory-opensearch-sink/status | jq
```

**What it shows:** Connector and per-task `state` (`RUNNING`, `PAUSED`,
`FAILED`). If a task has failed, the `trace` field carries the stack trace —
far more useful than scraping logs.

---

### 4. Watch the Bootstrap (templates + connector registration)
```bash
docker compose logs connect-init
```

**What it shows:** The one-shot `connect-init` container applying the OpenSearch
index templates and registering/updating the two sink connectors. Look for
`applied template: orders`, `ensured index: ...`, and `-> orders-opensearch-sink`,
ending with `Pipeline bootstrap complete.`

---

### 5. Verify Propagation After a Write
```bash
# Doc counts in each index
curl -s localhost:9200/orders/_count
curl -s localhost:9200/inventory/_count

# Consumer lag for the orders sink (0 lag == fully caught up)
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
```

**What it shows:** Whether the sink has drained the topic. Lag dropping back to
0 after a write is the clean signal that propagation is complete.

---

### 6. Prove a Specific Write Landed (impact probe)
```bash
# After a PostgreSQL write, ask the API which docs changed at/after that timestamp.
# <ms> is the Materialize timestamp (epoch ms), surfaced on each doc as mz_timestamp.
curl -s "localhost:8080/api/search/impact?since_mz_timestamp=<ms>"
```

`mz_timestamp` is copied onto every OpenSearch doc from the Kafka header
`materialize-timestamp` (via the `tsHeader` HeaderToValue SMT). All docs from a
single Materialize transaction share the same `mz_timestamp`.

---

### 7. Tail the Topics Directly
```bash
docker compose exec redpanda rpk topic consume orders -n 1
docker compose exec redpanda rpk topic consume inventory -n 1
```

**What it shows:** The raw Debezium-envelope Avro messages Materialize sinks to
Redpanda, including the `materialize-timestamp` header. Use this to confirm the
sink upstream of OpenSearch is producing.

---

## Useful Signals Reference

| Signal | Component | How to see it |
|--------|-----------|---------------|
| Sink task state (RUNNING/FAILED) | kafka-connect | `curl -s localhost:8083/connectors/orders-opensearch-sink/status` |
| Bulk writes to OpenSearch | kafka-connect | `docker compose logs -f kafka-connect \| grep -iE "WorkerSinkTask\|BulkProcessor"` |
| Connector errors | kafka-connect | `docker compose logs -f kafka-connect \| grep -iE "ERROR\|FAILED"` |
| Embedding requests | embedding-service | `docker compose logs -f embedding-service \| grep "POST /v1/embeddings"` |
| Consumer lag (caught-up check) | redpanda | `docker compose exec redpanda rpk group describe connect-orders-opensearch-sink` |
| Topic contents / `materialize-timestamp` | redpanda | `docker compose exec redpanda rpk topic consume orders -n 1` |
| Indexed doc counts | opensearch | `curl -s localhost:9200/orders/_count` |
| Impact of a specific write | api | `curl -s "localhost:8080/api/search/impact?since_mz_timestamp=<ms>"` |
| Bootstrap (templates + connectors) | connect-init | `docker compose logs connect-init` |

---

## End-to-End Flow: PostgreSQL → Materialize → Redpanda → OpenSearch

The pipeline now spans several services. Watch the API (the write side) and the
sink (the index side) together:

```bash
docker compose logs -f api kafka-connect embedding-service
```

The API service logs the incoming write requests; `kafka-connect` logs the sink
tasks committing to OpenSearch; `embedding-service` logs the embedding calls the
orders connector makes along the way. To confirm the write actually landed,
follow up with the doc-count / consumer-lag / impact probes above rather than
relying on log lines.

**Key Insight:** All triples written in a single PostgreSQL transaction become
events at the same Materialize timestamp, sink to Redpanda with the same
`materialize-timestamp` header, and land in OpenSearch carrying the same
`mz_timestamp`.

---

## Common Demo Scenarios

### Scenario 1: Create Order with Line Items (Transactional)

**Action:**
```bash
# Use the UI or API to create an order with 3 products
curl -X POST http://localhost:8080/triples/batch -H "Content-Type: application/json" -d '[...]'
```

**How to verify:**
```bash
# Orders index count should increase
curl -s localhost:9200/orders/_count
# Orders sink lag should return to 0
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
```

**Demonstrates:** The order and its line items propagate through the sink into a
single OpenSearch `orders` doc, all carrying the same `mz_timestamp`.

---

### Scenario 2: Update Order Status

**Action:**
```bash
docker compose exec db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='DELIVERED' WHERE subject_id='order:FM-XXXXX' AND predicate='order_status';"
```

**How to verify:**
```bash
curl -s "localhost:9200/orders/_doc/order:FM-XXXXX?pretty" | grep -E '"order_status"|"mz_timestamp"'
```

**Demonstrates:** Materialize re-emits the order at a new timestamp; the sink
upserts the existing OpenSearch doc (key is `order_id`, `index.write.method` is
`UPSERT`) — a single write, not a delete + insert. `behavior.on.null.values` is
`delete`, so an actual retraction tombstone would remove the doc.

---

### Scenario 3: Update Product Price (Cascading Updates)

**Action:**
```bash
docker compose exec db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='15.99' WHERE subject_id='product:prod0001' AND predicate='base_price';"
```

**How to verify:**
```bash
# Inventory sink processes the cascade; watch lag drain and counts settle
docker compose exec redpanda rpk group describe connect-inventory-opensearch-sink
curl -s localhost:9200/inventory/_count
```

**Demonstrates:** A single product update cascades to multiple inventory records
in Materialize; the inventory sink writes them all at the same timestamp.

---

## Advanced Filtering

### Show Only the Orders Connector's Logs
Both sink tasks run in the same `kafka-connect` worker, so filter by connector
or topic name in the log line:
```bash
docker compose logs -f kafka-connect | grep -i "orders-opensearch-sink"
```

### Tail Only Errors
```bash
docker compose logs -f kafka-connect | grep -iE "ERROR|FAILED|Exception"
```

### Count Embedding Requests
```bash
docker compose logs embedding-service | grep -c "POST /v1/embeddings"
```

### Watch the Write Side and Sink Together
```bash
docker compose logs -f api kafka-connect | grep -iE "POST /triples|WorkerSinkTask|BulkProcessor|ERROR"
```

---

## Troubleshooting

### Nothing Landing in OpenSearch?

1. Check the connectors are registered and RUNNING:
   ```bash
   curl -s localhost:8083/connectors
   curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks'
   ```

2. Check the bootstrap actually completed:
   ```bash
   docker compose logs connect-init
   # expect: "Pipeline bootstrap complete."
   ```

3. Check the services are up:
   ```bash
   docker compose ps kafka-connect embedding-service redpanda
   ```

4. Check there's data on the topic at all:
   ```bash
   docker compose exec redpanda rpk topic consume orders -n 1
   ```

### A Task Is FAILED?

Read the trace directly from the REST API, then restart the task:
```bash
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks[].trace'
curl -s -X POST localhost:8083/connectors/orders-opensearch-sink/restart?includeTasks=true
```

### Embeddings Not Being Generated?

```bash
docker compose logs -f embedding-service | grep -iE "POST /v1/embeddings|ERROR"
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks[].trace'
```

---

## Performance / Throughput

### Sink Lag (how far behind is the index?)
```bash
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
docker compose exec redpanda rpk group describe connect-inventory-opensearch-sink
```
`LAG` per partition is the authoritative throughput/backlog signal.

### Index Growth
```bash
watch -n1 'curl -s localhost:9200/orders/_count; echo; curl -s localhost:9200/inventory/_count'
```

### Propagation Latency for a Specific Write
After a write, take the Materialize timestamp (epoch ms) and poll the impact
endpoint until the doc shows up:
```bash
curl -s "localhost:8080/api/search/impact?since_mz_timestamp=<ms>"
```

---

## Tips for Live Demos

1. **Split Terminal** - Logs (`kafka-connect` / `embedding-service`) in one pane,
   commands and probes in another.
2. **Lead with the probes** - `_count`, consumer lag, and the impact endpoint are
   crisp, deterministic signals; logs are supporting color.
3. **Filter Aggressively** - Connect logs are verbose; grep for
   `WorkerSinkTask|BulkProcessor|ERROR`.
4. **Pause Between Actions** - Give the sink a second or two to drain the topic.
5. **Show lag returning to 0** - The cleanest visual proof that a write fully
   propagated.

**Best Command for Demos:**
```bash
docker compose logs -f --tail=0 kafka-connect embedding-service \
  | grep --color=always -iE "WorkerSinkTask|BulkProcessor|POST /v1/embeddings|ERROR|FAILED"
```

Pair it with a `watch` on the doc counts and consumer lag for a complete picture.
</content>
</invoke>
