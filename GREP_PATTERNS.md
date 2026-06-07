# Quick Reference: Log Filters & Probes for the Demo

> **Architecture note:** OpenSearch is kept in sync by a Kafka pipeline:
> `Materialize CREATE SINK → Redpanda (topics orders/inventory) → Kafka Connect
> (service kafka-connect, REST :8083) → OpenSearch`. The orders connector runs an
> embedding SMT against `embedding-service` (:8085). Kafka Connect logs are
> standard log4j lines — so for propagation and throughput, prefer the REST/CLI
> probes below over grep.

## Essential Log Filters

### 1. Sink Connector Activity (kafka-connect)
```bash
docker compose logs -f kafka-connect | grep -iE "WorkerSinkTask|BulkProcessor|ERROR|RUNNING|FAILED"
```

**What you'll see:**
- `WorkerSinkTask` — poll/commit cycles consuming from Redpanda
- `BulkProcessor` — batched bulk writes to OpenSearch
- `RUNNING` / `FAILED` / `ERROR` — task health

---

### 2. Embedding Requests (embedding-service)
```bash
docker compose logs -f embedding-service | grep "POST /v1/embeddings"
```

**What you'll see:** One request line per batch the orders connector's embedding
SMT sends to the `bge-small` (384-dim) model.

---

### 3. Bootstrap (connect-init)
```bash
docker compose logs connect-init
```

**What you'll see:** Index templates applied, indices ensured, both sink
connectors registered, ending with `Pipeline bootstrap complete.`

---

### 4. Write Side + Sink Together
```bash
docker compose logs -f api kafka-connect | grep -iE "POST /triples|WorkerSinkTask|BulkProcessor|ERROR"
```

**What you'll see:** Incoming writes on the `api` service and the sink draining
them into OpenSearch. Confirm the result with the probes below.

---

### 5. Errors Only
```bash
docker compose logs -f kafka-connect | grep -iE "ERROR|FAILED|Exception"
```

---

## Essential Probes (preferred over grep)

### Connector / Task State
```bash
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq
curl -s localhost:8083/connectors/inventory-opensearch-sink/status | jq
```
`state` is `RUNNING` / `PAUSED` / `FAILED`; a failed task carries a `trace`.

### Consumer Lag (caught-up check)
```bash
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
docker compose exec redpanda rpk group describe connect-inventory-opensearch-sink
```
`LAG` back to 0 == the sink has fully drained the topic.

### Indexed Doc Counts
```bash
curl -s localhost:9200/orders/_count
curl -s localhost:9200/inventory/_count
```

### Impact of a Specific Write
```bash
# <ms> = Materialize timestamp (epoch ms), surfaced on each doc as mz_timestamp
curl -s "localhost:8080/api/search/impact?since_mz_timestamp=<ms>"
```

### Tail a Topic Directly
```bash
docker compose exec redpanda rpk topic consume orders -n 1
docker compose exec redpanda rpk topic consume inventory -n 1
```
Shows the raw Debezium-envelope Avro and the `materialize-timestamp` header that
becomes the doc's `mz_timestamp`.

---

## Common Combinations

### Debug: Why didn't my write propagate?
```bash
# 1. Is data on the topic?
docker compose exec redpanda rpk topic consume orders -n 1

# 2. Is the sink task healthy?
curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks[].state'

# 3. Has the sink caught up? (LAG -> 0)
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink

# 4. Did the doc count change?
curl -s localhost:9200/orders/_count
```

### Performance: how fast is the pipeline?
```bash
# Watch lag drain after a write
watch -n1 'docker compose exec redpanda rpk group describe connect-orders-opensearch-sink'
```

### Verification: did a specific document update?
```bash
curl -s "localhost:9200/orders/_doc/order:FM-12345?pretty" | grep -E '"order_status"|"mz_timestamp"'
```

---

## Signals Quick Reference

| Signal | Component | Command |
|--------|-----------|---------|
| Sink task state | kafka-connect | `curl -s localhost:8083/connectors/orders-opensearch-sink/status \| jq` |
| Bulk writes / commits | kafka-connect | `docker compose logs -f kafka-connect \| grep -iE "WorkerSinkTask\|BulkProcessor"` |
| Connector errors | kafka-connect | `docker compose logs -f kafka-connect \| grep -iE "ERROR\|FAILED"` |
| Embedding requests | embedding-service | `docker compose logs -f embedding-service \| grep "POST /v1/embeddings"` |
| Consumer lag | redpanda | `docker compose exec redpanda rpk group describe connect-orders-opensearch-sink` |
| Topic contents / header | redpanda | `docker compose exec redpanda rpk topic consume orders -n 1` |
| Doc counts | opensearch | `curl -s localhost:9200/orders/_count` |
| Write impact | api | `curl -s "localhost:8080/api/search/impact?since_mz_timestamp=<ms>"` |
| Bootstrap | connect-init | `docker compose logs connect-init` |

---

## Pro Tips

1. **Use `--line-buffered`** for real-time grep:
   ```bash
   docker compose logs -f kafka-connect | grep --line-buffered -iE "WorkerSinkTask|BulkProcessor|ERROR"
   ```

2. **Add color** to highlight patterns:
   ```bash
   docker compose logs -f kafka-connect | grep --color=always -iE "BulkProcessor|ERROR|FAILED"
   ```

3. **Count embedding calls**:
   ```bash
   docker compose logs embedding-service | grep -c "POST /v1/embeddings"
   ```

4. **Read a failed task's trace** instead of scraping logs:
   ```bash
   curl -s localhost:8083/connectors/orders-opensearch-sink/status | jq '.tasks[].trace'
   ```

5. **Watch a specific order land**:
   ```bash
   ORDER_ID="order:FM-12345"
   watch -n1 "curl -s localhost:9200/orders/_doc/$ORDER_ID?pretty | grep -E '\"order_status\"|\"mz_timestamp\"'"
   ```

---

## What to Demo

### Demo 1: A Write Propagates End-to-End
**Commands:**
```bash
# pane 1: watch the sink and embedding calls
docker compose logs -f kafka-connect embedding-service | grep --line-buffered -iE "BulkProcessor|POST /v1/embeddings|ERROR"
# pane 2: confirm it landed
docker compose exec redpanda rpk group describe connect-orders-opensearch-sink
curl -s localhost:9200/orders/_count
```
**Action:** Create an order with 3 line items via the API.
**Key Insight:** Lag returns to 0 and the orders count increases; the order and
its lines share one `mz_timestamp`.

### Demo 2: Update Propagation (UPSERT)
**Commands:**
```bash
curl -s "localhost:9200/orders/_doc/order:FM-XXXXX?pretty" | grep -E '"order_status"|"mz_timestamp"'
```
**Action:** Update the order status in PostgreSQL.
**Key Insight:** The sink upserts the same doc (key `order_id`); `mz_timestamp`
advances.

### Demo 3: Semantic Search Stays Fresh
**Commands:**
```bash
docker compose logs -f embedding-service | grep "POST /v1/embeddings"
```
**Action:** Create/update an order.
**Key Insight:** The embedding SMT re-embeds the changed text so vector search
reflects the new state.
</content>
