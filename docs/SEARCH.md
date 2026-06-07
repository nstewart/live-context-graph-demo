# Search Integration

This document describes the OpenSearch integration for full-text search capabilities.

## Overview

OpenSearch provides:
- Full-text search across orders
- Fuzzy matching for typos
- Multi-field search (customer name, address, order number)
- Fast retrieval for the agent's search tools

## Index Schema

### Orders Index

```json
{
  "mappings": {
    "properties": {
      "order_id": { "type": "keyword" },
      "order_number": { "type": "keyword", "copy_to": "search_text" },
      "order_status": { "type": "keyword" },
      "store_id": { "type": "keyword" },
      "customer_id": { "type": "keyword" },
      "delivery_window_start": { "type": "date" },
      "delivery_window_end": { "type": "date" },
      "order_total_amount": { "type": "float" },
      "customer_name": {
        "type": "text",
        "copy_to": "search_text",
        "fields": { "keyword": { "type": "keyword" }}
      },
      "customer_email": { "type": "keyword" },
      "customer_address": {
        "type": "text",
        "copy_to": "search_text",
        "fields": { "keyword": { "type": "keyword" }}
      },
      "store_name": {
        "type": "text",
        "copy_to": "search_text",
        "fields": { "keyword": { "type": "keyword" }}
      },
      "store_zone": { "type": "keyword" },
      "assigned_courier_id": { "type": "keyword" },
      "delivery_task_status": { "type": "keyword" },
      "delivery_eta": { "type": "date" },
      "effective_updated_at": { "type": "date" },
      "search_text": { "type": "text" }
    }
  }
}
```

## Sync Pipeline (Kafka Sink + Kafka Connect)

OpenSearch is kept in sync by a **Materialize Kafka sink → Redpanda → Kafka Connect**
pipeline. There is no in-process sync service; Materialize emits change events to Kafka
and Kafka Connect sinks them into OpenSearch.

### Sync Flow

1. **Materialize sink**: `CREATE SINK ... FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY
   ... ENVELOPE DEBEZIUM` publishes change events to Redpanda:
   - `orders_with_lines_mv` → topic `orders` (key `order_id`)
   - `inventory_items_with_dynamic_pricing_mv` → topic `inventory` (key `inventory_id`)
2. **Kafka Connect**: the Aiven OpenSearch sink connector consumes each topic and
   applies a transform (SMT) chain, then bulk-indexes into the `orders` / `inventory`
   OpenSearch indices.
3. **Upserts and deletes**: both connectors are configured `UPSERT` with
   `behavior.on.null.values=delete`, so a Debezium delete (null value) becomes a
   tombstone that removes the OpenSearch document.

Each Kafka message carries a `materialize-timestamp` header with the Materialize
logical timestamp; the connector copies it into the `mz_timestamp` document field
(used by `GET /api/search/impact`).

### Connector Transform Chains

**orders connector:**
1. `extractKey` — Kafka key → document `_id`
2. `embed` (`EmbeddingDiffTransform`) — calls the embedding service to fill the
   `embedding_text_embedding` vector field (`knn_vector`, 384 dims); re-embeds only
   when the `embedding_text` column changes (Debezium before/after diff)
3. `cast` — decimals → `float64`
4. `tsHeader` (`HeaderToValue`) — `materialize-timestamp` header → `mz_timestamp`

**inventory connector:**
1. `extractKey`
2. `unwrap` (`ExtractField` after) — flatten the Debezium envelope
3. `cast` — decimals → `float64`
4. `tsHeader` — `materialize-timestamp` header → `mz_timestamp` (no embedding)

### Embedding Service

The `embedding-service` (port 8085) is an OpenAI-compatible `/v1/embeddings` facade
over fastembed `BAAI/bge-small-en-v1.5` (384-dim), served by Hypercorn. It is used at
**ingest time** (the orders connector's embedding SMT) and at **query time** (the API
computes the query vector for kNN search). Re-embed deduplication is handled by the
SMT's Debezium before/after diff — there is no separate MD5 hash cache.

### Configuration

Connector definitions, OpenSearch index templates, and the embedding SMT config live
under `kafka-connect/` and are applied by the one-shot `connect-init` service. The
embedding service is configured via:

```bash
EMBEDDING_SERVICE_URL=http://embedding-service:8085
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5   # 384-dim
```

## Search Queries

### Basic Search

```bash
# Search via OpenSearch directly
POST /orders/_search
{
  "query": {
    "multi_match": {
      "query": "Alex Thompson",
      "fields": ["customer_name^2", "customer_address", "order_number^3"],
      "type": "best_fields",
      "fuzziness": "AUTO"
    }
  }
}
```

### Filtered Search

```bash
# Search with status filter
POST /orders/_search
{
  "query": {
    "bool": {
      "must": [
        {"multi_match": {"query": "Brooklyn", "fields": ["search_text"]}}
      ],
      "filter": [
        {"term": {"order_status": "OUT_FOR_DELIVERY"}}
      ]
    }
  }
}
```

### Via Agent Tool

The agent's `search_orders` tool wraps OpenSearch:

```python
results = await search_orders(
    query="Alex Thompson",
    status="OUT_FOR_DELIVERY",
    limit=10
)
```

## Extending Search

### Adding New Indices

1. **Define an index template** under `kafka-connect/`
2. **Create the source materialized view** in Materialize
3. **Add a Materialize Kafka sink** for the view (Avro/Debezium → new topic)
4. **Register an OpenSearch sink connector** (transform chain) via `connect-init`
5. **Create an agent tool** for querying

### Example: Store Search

```jsonc
// kafka-connect/templates/stores.json — OpenSearch index template
{
  "mappings": {
    "properties": {
      "store_id":      { "type": "keyword" },
      "store_name":    { "type": "text" },
      "store_address": { "type": "text" },
      "store_zone":    { "type": "keyword" },
      "store_status":  { "type": "keyword" }
    }
  }
}
```

```sql
-- Materialize: sink the source view to a new Kafka topic
CREATE SINK stores_sink
  FROM stores_mv
  INTO KAFKA CONNECTION redpanda (TOPIC 'stores')
  KEY (store_id)
  FORMAT AVRO USING CONFLUENT SCHEMA REGISTRY connection
  ENVELOPE DEBEZIUM;
```

Then register a `stores-opensearch-sink` connector (with the `extractKey` / `unwrap` /
`cast` / `tsHeader` transform chain, like the inventory connector) via `connect-init`.

## Monitoring

### Check Index Health

```bash
# Get index stats
curl http://localhost:9200/orders/_stats

# Check cluster health
curl http://localhost:9200/_cluster/health
```

### Debug Sync Issues

```bash
# Check the Materialize sinks exist
docker compose exec mz psql -U materialize -d materialize -c "SHOW SINKS"

# Check connector / task status via the Kafka Connect REST API
curl -s http://localhost:8083/connectors/orders-opensearch-sink/status | jq

# Check Kafka Connect logs (sink + embedding SMT)
docker compose logs -f kafka-connect

# Check the embedding service
docker compose logs -f embedding-service
```

## Performance Tips

1. **Connector tasks**: Increase `tasks.max` / topic partitions to parallelize indexing
2. **Embedding throughput**: The orders connector's embedding SMT can be the bottleneck; scale `embedding-service` if needed
3. **Index Settings**: Single shard/replica for dev, scale for production
4. **Refresh Interval**: OpenSearch defaults to 1s refresh
