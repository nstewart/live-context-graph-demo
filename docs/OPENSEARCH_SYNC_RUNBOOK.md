# OpenSearch Sync Operations Runbook

## Overview

This runbook provides operational guidance for managing the OpenSearch sync service, which uses Materialize SUBSCRIBE streaming to maintain real-time synchronization between PostgreSQL and OpenSearch.

### Architecture Summary

**Data Flow**:
```
PostgreSQL → Materialize (CDC) → SUBSCRIBE Stream → Search Sync Worker → OpenSearch
   (source)     (real-time)        (differential)       (bulk ops)          (index)
```

**Key Components**:
- **Materialize View**: `orders_search_source_mv` (computed from triples)
- **SUBSCRIBE Client**: Python async client using `psycopg` with streaming
- **Sync Worker**: Accumulates events by timestamp, performs bulk operations
- **OpenSearch Index**: `orders` index with full-text search capabilities

**Performance Characteristics**:
- **Latency**: < 2 seconds end-to-end (PostgreSQL write → OpenSearch searchable)
- **Throughput**: 10,000+ events/second capacity (single worker)
- **Memory**: < 500MB steady state under normal load
- **Recovery**: Automatic reconnection with exponential backoff (1s → 30s max)

---

## 1. Monitoring

### Health Check Endpoints

The search-sync service does not expose HTTP endpoints. Monitor health through logs and system metrics.

**Check Service Status**:
```bash
# Verify container is running
docker-compose ps search-sync

# Expected output:
# NAME              STATUS    PORTS
# search-sync       Up 5 minutes
```

**Check SUBSCRIBE Connection**:
```bash
# Look for successful connection message
docker-compose logs --tail=100 search-sync | grep "Starting SUBSCRIBE"

# Expected output:
# [INFO] Starting SUBSCRIBE for view: orders_search_source_mv
# [INFO] SUBSCRIBE started for orders_search_source_mv, receiving snapshot...
```

### Key Metrics to Monitor

#### 1. Sync Latency

**Definition**: Time from PostgreSQL write to OpenSearch indexing completion

**Target**: p95 < 2 seconds, p99 < 5 seconds

**How to Measure**:
```bash
# Create test order and measure search availability
START=$(date +%s)
curl -X POST http://localhost:8080/freshmart/orders -d '{"order_number":"TEST-'$START'", ...}'
sleep 1
while ! curl -s "http://localhost:9200/orders/_search?q=order_number:TEST-$START" | grep -q "TEST-$START"; do
  sleep 0.5
done
END=$(date +%s)
echo "Latency: $((END - START)) seconds"
```

**Alert Threshold**: Latency > 5 seconds for 2 consecutive measurements

#### 2. Event Throughput

**Definition**: Number of events processed per second

**Target**: Should match database write rate (typically 10-100 events/second)

**How to Measure**:
```bash
# Count "Broadcasting" messages in last minute
docker-compose logs --since 1m search-sync | grep "Broadcasting.*changes" | \
  awk '{sum+=$2} END {print sum " events in last minute"}'
```

**Alert Threshold**: No events for > 60 seconds when database activity exists

#### 3. Buffer Size

**Definition**: Number of pending events waiting to be flushed to OpenSearch

**Target**: < 1000 under normal load, automatic backpressure at 5000

**How to Measure**:
```bash
# Look for buffer size in logs (if implemented)
docker-compose logs --tail=50 search-sync | grep "buffer"

# Expected output:
# [INFO] Buffer size: 245 events (backpressure: inactive)
```

**Alert Threshold**:
- Warning: Buffer > 2500 for > 5 minutes
- Critical: Buffer > 5000 (backpressure activated)

#### 4. Error Rate

**Definition**: Percentage of operations that fail

**Target**: < 0.1% error rate

**How to Measure**:
```bash
# Count errors in last hour
docker-compose logs --since 1h search-sync | grep -i "error" | wc -l

# Count total operations
docker-compose logs --since 1h search-sync | grep "Broadcasting" | wc -l
```

**Alert Threshold**:
- Warning: > 1% error rate
- Critical: > 5% error rate or any unrecoverable errors

### Log Patterns

#### Healthy State

```log
[INFO] Connected to Materialize for SUBSCRIBE
[INFO] Starting SUBSCRIBE for view: orders_search_source_mv
[INFO] SUBSCRIBE started for orders_search_source_mv, receiving snapshot...
[INFO] Snapshot complete for orders_search_source_mv: 1234 rows (discarding snapshot, streaming changes only)
[INFO] Broadcasting 15 changes for orders_search_source_mv
[INFO] Synced 15 documents, 0 errors
[DEBUG] Progress update: orders_search_source_mv at ts=1701234567890
```

#### Unhealthy State

```log
[ERROR] Connection refused to Materialize
[WARNING] SUBSCRIBE failed, retrying in 2s: connection timeout
[ERROR] Error processing SUBSCRIBE row for orders_search_source_mv: invalid data format
[WARNING] OpenSearch bulk operation failed: timeout
[ERROR] Buffer overflow: 5001 events pending (backpressure activated)
```

### Prometheus Metrics (If Implemented)

If your deployment exposes Prometheus metrics, monitor:

```promql
# Sync latency (p95)
histogram_quantile(0.95, rate(opensearch_sync_latency_seconds_bucket[5m]))

# Event throughput
rate(opensearch_sync_events_total[5m])

# Error rate
rate(opensearch_sync_errors_total[5m]) / rate(opensearch_sync_events_total[5m])

# Buffer size
opensearch_sync_buffer_size
```

---

## 2. Common Operations

### Starting the Service

```bash
# Start search-sync service
docker-compose up -d search-sync

# Verify startup
docker-compose logs -f search-sync
# Wait for "Starting SUBSCRIBE for view: orders_search_source_mv"

# Check OpenSearch index exists
curl http://localhost:9200/orders/_count
# Should return: {"count": <number>, "_shards": {...}}
```

**Startup Sequence**:
1. Connect to Materialize (with retry logic)
2. Set cluster to `serving`
3. Execute `SUBSCRIBE (SELECT * FROM orders_search_source_mv) WITH (PROGRESS)`
4. Receive and discard snapshot (upserts are idempotent)
5. Stream real-time differential updates

### Stopping the Service

```bash
# Graceful shutdown (allows pending events to flush)
docker-compose stop search-sync

# Check logs for clean shutdown
docker-compose logs --tail=20 search-sync
# Should see: "Orders sync worker stopped"

# Force stop (if graceful shutdown hangs)
docker-compose kill search-sync
```

### Restarting the Service

```bash
# Restart after configuration change
docker-compose restart search-sync

# Rebuild and restart after code change
docker-compose up -d --build search-sync

# Watch logs during restart
docker-compose logs -f search-sync
```

### Checking Sync Status

```bash
# Check last sync activity
docker-compose logs --tail=100 search-sync | grep "Broadcasting"

# Verify data consistency between Materialize and OpenSearch
MZ_COUNT=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;")
OS_COUNT=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
echo "Materialize: $MZ_COUNT, OpenSearch: $OS_COUNT"
# Counts should match (allow for < 1% drift due to in-flight operations)
```

### Verifying Data Freshness

```bash
# Get most recent order from Materialize
LATEST_MZ=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT order_id FROM orders_search_source_mv ORDER BY effective_updated_at DESC LIMIT 1;")

# Search for it in OpenSearch
curl -s "http://localhost:9200/orders/_search" \
  -H 'Content-Type: application/json' \
  -d '{"query": {"term": {"order_id": "'$LATEST_MZ'"}}}' | jq '.hits.total.value'

# Should return 1 (order is indexed)
```

---

## 3. Troubleshooting Guide

### Issue: SUBSCRIBE Connection Failures

**Symptoms**:
```log
[ERROR] Connection refused to Materialize
[WARNING] SUBSCRIBE failed, retrying in 2s: connection timeout
```

**Possible Causes**:
1. Materialize service is down
2. Network connectivity issues
3. Incorrect connection configuration
4. Materialize cluster not ready

**Resolution Steps**:

1. **Verify Materialize is running**:
   ```bash
   docker-compose ps mz
   # Should show: Up <duration>

   # Check Materialize logs
   docker-compose logs --tail=50 mz
   ```

2. **Test connection manually**:
   ```bash
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c "SELECT 1;"
   # Should return: 1
   ```

3. **Verify view exists**:
   ```bash
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
     "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;"
   ```

4. **Check connection configuration**:
   ```bash
   docker-compose exec search-sync env | grep MZ_
   # Verify MZ_HOST, MZ_PORT, MZ_USER, MZ_PASSWORD, MZ_DATABASE
   ```

5. **Restart search-sync** (exponential backoff will retry):
   ```bash
   docker-compose restart search-sync
   ```

**Expected Recovery**: Service should reconnect within 30 seconds

---

### Issue: Slow Sync (High Latency)

**Symptoms**:
- Orders take > 5 seconds to appear in search
- Backpressure warnings in logs

**Possible Causes**:
1. OpenSearch performance degradation
2. Network latency between search-sync and OpenSearch
3. Large batch sizes causing slow bulk operations
4. Materialize view computation lag

**Resolution Steps**:

1. **Check OpenSearch health**:
   ```bash
   curl http://localhost:9200/_cluster/health
   # Should return: "status": "green" or "yellow"

   curl http://localhost:9200/_cat/indices/orders?v
   # Check: docs.count, store.size
   ```

2. **Check bulk operation performance**:
   ```bash
   docker-compose logs --tail=100 search-sync | grep "bulk_upsert"
   # Look for: "Synced N documents, 0 errors"
   # If N is large (> 1000), bulk operations may be slow
   ```

3. **Monitor Materialize view lag**:
   ```bash
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
     "SET CLUSTER = compute; SHOW MATERIALIZED VIEWS;"
   # Check for "BEHIND" status
   ```

4. **Check network latency**:
   ```bash
   docker-compose exec search-sync ping -c 5 opensearch
   # Should show: < 1ms average
   ```

5. **Reduce batch size** (if configured):
   ```bash
   # Edit docker-compose.yml or config
   # Set: MAX_BATCH_SIZE=500 (default: 1000)
   docker-compose up -d --build search-sync
   ```

**Expected Recovery**: Latency should return to < 2 seconds within 5 minutes

---

### Issue: OpenSearch Index Drift

**Symptoms**:
- Document count mismatch between Materialize and OpenSearch
- Missing orders in search results
- Duplicate orders in search results

**Possible Causes**:
1. Failed bulk operations not retried
2. Network partitions during sync
3. OpenSearch index corruption
4. SUBSCRIBE connection interrupted during event processing

**Resolution Steps**:

1. **Compare counts**:
   ```bash
   MZ_COUNT=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
     "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;")
   OS_COUNT=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
   DIFF=$((MZ_COUNT - OS_COUNT))
   echo "Materialize: $MZ_COUNT, OpenSearch: $OS_COUNT, Diff: $DIFF"
   ```

2. **Check for failed operations**:
   ```bash
   docker-compose logs --since 24h search-sync | grep -i "error"
   # Look for: bulk operation failures, connection drops
   ```

3. **Identify missing documents** (sample):
   ```bash
   # Get 10 order IDs from Materialize
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
     "SET CLUSTER = serving; SELECT order_id FROM orders_search_source_mv LIMIT 10;"

   # Check each in OpenSearch
   for order_id in <order_ids>; do
     curl -s "http://localhost:9200/orders/_doc/$order_id" | jq '.found'
   done
   ```

4. **Force resync** (see Disaster Recovery section below)

**Expected Resolution Time**: 5-30 minutes depending on data volume

---

### Issue: Memory/Buffer Overflow

**Symptoms**:
```log
[WARNING] Buffer size exceeds threshold: 5001 events
[WARNING] Backpressure activated: pausing SUBSCRIBE stream
```

**Possible Causes**:
1. OpenSearch is too slow to keep up with event rate
2. Network congestion
3. Memory leak in sync worker
4. Sudden spike in database write activity

**Resolution Steps**:

1. **Check memory usage**:
   ```bash
   docker stats search-sync
   # Note: MEM USAGE and MEM %
   # Normal: < 500MB
   # Warning: > 1GB
   ```

2. **Check event rate**:
   ```bash
   # Count broadcasts in last 5 minutes
   docker-compose logs --since 5m search-sync | grep "Broadcasting" | wc -l
   ```

3. **Check OpenSearch load**:
   ```bash
   curl http://localhost:9200/_nodes/stats/indices/indexing
   # Look for: indexing_throttle_time, rejected requests
   ```

4. **Restart search-sync** (clears buffer):
   ```bash
   docker-compose restart search-sync
   # Buffer will be cleared, snapshot discarded, streaming resumes
   ```

5. **Scale OpenSearch** (if persistent):
   ```bash
   # Increase OpenSearch memory
   # Edit docker-compose.yml:
   # opensearch:
   #   environment:
   #     - "ES_JAVA_OPTS=-Xms2g -Xmx2g"
   docker-compose up -d opensearch
   ```

**Expected Recovery**: Buffer should clear within 2 minutes after restart

---

## 4. Disaster Recovery

### Procedure: Force Resync

**When to Use**:
- Significant index drift (> 5% difference)
- Data corruption suspected
- After restoring from backup

**Steps**:

1. **Stop search-sync**:
   ```bash
   docker-compose stop search-sync
   ```

2. **Delete OpenSearch index**:
   ```bash
   curl -X DELETE http://localhost:9200/orders
   # Response: {"acknowledged": true}
   ```

3. **Recreate index with mapping**:
   ```bash
   curl -X PUT http://localhost:9200/orders \
     -H 'Content-Type: application/json' \
     -d '{
       "mappings": {
         "properties": {
           "order_id": {"type": "keyword"},
           "order_number": {"type": "keyword"},
           "order_status": {"type": "keyword"},
           "customer_name": {"type": "text"},
           "customer_email": {"type": "keyword"},
           "customer_address": {"type": "text"},
           "store_name": {"type": "text"},
           "store_zone": {"type": "keyword"},
           "order_total_amount": {"type": "float"},
           "delivery_window_start": {"type": "date"},
           "delivery_window_end": {"type": "date"},
           "delivery_eta": {"type": "date"},
           "effective_updated_at": {"type": "date"}
         }
       }
     }'
   ```

4. **Bulk index from Materialize** (one-time full sync):
   ```bash
   # Export all orders to JSON
   PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -A -F"," -c \
     "SET CLUSTER = serving; SELECT row_to_json(t) FROM orders_search_source_mv t;" \
     > /tmp/orders.json

   # Bulk index to OpenSearch
   curl -X POST http://localhost:9200/orders/_bulk \
     -H 'Content-Type: application/x-ndjson' \
     --data-binary @/tmp/orders.json
   ```

5. **Start search-sync**:
   ```bash
   docker-compose start search-sync
   docker-compose logs -f search-sync
   # Wait for "Starting SUBSCRIBE for view: orders_search_source_mv"
   ```

6. **Verify counts**:
   ```bash
   MZ_COUNT=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
     "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;")
   OS_COUNT=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
   echo "Materialize: $MZ_COUNT, OpenSearch: $OS_COUNT"
   # Should match within 1%
   ```

**Expected Duration**: 5-30 minutes depending on data volume

---

### Procedure: Recreate Index

**When to Use**:
- Schema changes (new fields, field type changes)
- Index corruption
- Performance optimization (reindexing)

**Steps**:

1. **Create new index with updated mapping**:
   ```bash
   curl -X PUT http://localhost:9200/orders_v2 \
     -H 'Content-Type: application/json' \
     -d '{ "mappings": { ... new schema ... } }'
   ```

2. **Reindex from old to new** (if preserving data):
   ```bash
   curl -X POST http://localhost:9200/_reindex \
     -H 'Content-Type: application/json' \
     -d '{
       "source": {"index": "orders"},
       "dest": {"index": "orders_v2"}
     }'
   ```

3. **Update search-sync configuration** (if index name changed):
   ```bash
   # Edit docker-compose.yml or config
   # Set: OS_INDEX_NAME=orders_v2
   ```

4. **Switch alias** (zero downtime):
   ```bash
   curl -X POST http://localhost:9200/_aliases \
     -H 'Content-Type: application/json' \
     -d '{
       "actions": [
         {"remove": {"index": "orders", "alias": "orders_current"}},
         {"add": {"index": "orders_v2", "alias": "orders_current"}}
       ]
     }'
   ```

5. **Restart search-sync**:
   ```bash
   docker-compose restart search-sync
   ```

6. **Delete old index** (after verification):
   ```bash
   curl -X DELETE http://localhost:9200/orders
   ```

---

### Procedure: Rollback to Polling (Emergency)

**When to Use**:
- SUBSCRIBE streaming has critical bug
- Materialize upgrade breaks compatibility
- Need to reduce system complexity temporarily

**Steps**:

1. **Stop current search-sync**:
   ```bash
   docker-compose stop search-sync
   ```

2. **Checkout polling implementation**:
   ```bash
   cd /Users/natestewart/Projects/live-agent-ontology-demo
   git log --oneline | grep "polling"
   # Find commit before SUBSCRIBE migration
   git checkout <commit_hash> -- search-sync/
   ```

3. **Update configuration**:
   ```bash
   # Edit .env or docker-compose.yml
   # Set: USE_SUBSCRIBE=false
   # Set: POLL_INTERVAL=5  # seconds
   ```

4. **Rebuild and restart**:
   ```bash
   docker-compose up -d --build search-sync
   ```

5. **Monitor latency** (will be higher):
   ```bash
   docker-compose logs -f search-sync
   # Expect: 5-20 second latency (polling interval + batch processing)
   ```

6. **File incident report** (for post-mortem):
   ```bash
   # Document:
   # - Reason for rollback
   # - Error messages
   # - Steps to reproduce issue
   # - Timeline of events
   ```

**Expected Latency**: 5-20 seconds (degraded from < 2 seconds)

---

## 5. Configuration Reference

### Environment Variables

```bash
# Materialize Connection
MZ_HOST=mz                              # Materialize hostname
MZ_PORT=6875                            # Materialize SQL port
MZ_USER=materialize                     # Materialize user
MZ_PASSWORD=materialize                 # Materialize password
MZ_DATABASE=materialize                 # Materialize database

# OpenSearch Connection
OS_HOST=opensearch                      # OpenSearch hostname
OS_PORT=9200                            # OpenSearch port
OS_INDEX_NAME=orders                    # Index name for orders

# SUBSCRIBE Mode (default: true)
USE_SUBSCRIBE=true                      # Enable SUBSCRIBE streaming
DISCARD_SNAPSHOT=true                   # Discard initial snapshot (recommended)

# Batching Configuration
MAX_BATCH_SIZE=1000                     # Max events per batch
MAX_BATCH_AGE_SECONDS=5                 # Max time before flush

# Backpressure Configuration
BACKPRESSURE_THRESHOLD=5000             # Pause at this buffer size
BACKPRESSURE_RESUME=2500                # Resume at this buffer size

# Retry Configuration
RETRY_INITIAL_BACKOFF=1                 # Initial backoff (seconds)
RETRY_MAX_BACKOFF=30                    # Max backoff (seconds)
RETRY_BACKOFF_MULTIPLIER=2              # Backoff multiplier

# Logging
LOG_LEVEL=INFO                          # DEBUG, INFO, WARNING, ERROR
LOG_FORMAT=json                         # json or text
```

### Materialize View Schema

The `orders_search_source_mv` view provides these fields:

```sql
CREATE MATERIALIZED VIEW orders_search_source_mv AS
SELECT
    order_id,                   -- Primary key (keyword)
    order_number,               -- Human-readable ID (keyword)
    order_status,               -- Status enum (keyword)
    store_id,                   -- Reference to store (keyword)
    customer_id,                -- Reference to customer (keyword)
    delivery_window_start,      -- Delivery window (date)
    delivery_window_end,        -- Delivery window (date)
    order_total_amount,         -- Total amount (float)
    customer_name,              -- Customer name (text)
    customer_email,             -- Customer email (keyword)
    customer_address,           -- Delivery address (text)
    store_name,                 -- Store name (text)
    store_zone,                 -- Store zone (keyword)
    store_address,              -- Store address (text)
    assigned_courier_id,        -- Assigned courier (keyword, nullable)
    delivery_task_status,       -- Task status (keyword, nullable)
    delivery_eta,               -- Estimated delivery (date, nullable)
    effective_updated_at        -- Last update timestamp (date)
FROM ...;  -- (joins triples)
```

---

## 6. Performance Tuning

### Optimization: Reduce Sync Latency

**Current**: p95 < 2 seconds
**Target**: p95 < 1 second

**Tuning Options**:

1. **Reduce batch timeout**:
   ```bash
   # Edit config: MAX_BATCH_AGE_SECONDS=2 (from 5)
   # Trade-off: More frequent bulk operations (higher CPU)
   ```

2. **Enable HTTP keep-alive for OpenSearch**:
   ```python
   # In opensearch_client.py:
   # session = aiohttp.ClientSession(
   #     connector=aiohttp.TCPConnector(limit=10, keepalive_timeout=30)
   # )
   ```

3. **Use OpenSearch bulk API v2** (if available):
   ```python
   # Better performance for large batches
   ```

### Optimization: Increase Throughput

**Current**: 10,000+ events/second capacity
**Target**: 50,000+ events/second

**Scaling Options**:

1. **Horizontal scaling** (multiple workers):
   ```yaml
   # docker-compose.yml:
   search-sync:
     deploy:
       replicas: 3
   # Note: Requires partitioning strategy (e.g., by order_id hash)
   ```

2. **Increase batch size**:
   ```bash
   # Edit config: MAX_BATCH_SIZE=5000 (from 1000)
   # Trade-off: Higher memory usage
   ```

3. **Tune OpenSearch**:
   ```bash
   # Increase bulk thread pool
   curl -X PUT http://localhost:9200/_cluster/settings \
     -H 'Content-Type: application/json' \
     -d '{"transient": {"thread_pool.write.queue_size": 1000}}'
   ```

### Optimization: Reduce Memory Usage

**Current**: < 500MB steady state
**Target**: < 250MB

**Options**:

1. **Reduce batch size**:
   ```bash
   # Edit config: MAX_BATCH_SIZE=500 (from 1000)
   ```

2. **Enable streaming JSON parsing** (if large documents):
   ```python
   # Use ijson for incremental parsing
   ```

3. **Reduce backpressure threshold**:
   ```bash
   # Edit config: BACKPRESSURE_THRESHOLD=2500 (from 5000)
   ```

---

## 7. Related Documentation

- **Architecture Spec**: `OPENSEARCH_SUBSCRIBE_IMPLEMENTATION.md`
- **SUBSCRIBE Client Code**: `search-sync/src/mz_client_subscribe.py`
- **Materialize SUBSCRIBE Docs**: https://materialize.com/docs/sql/subscribe/

---

## 8. Incident Response Template

**Incident Title**: [e.g., "OpenSearch sync latency spike"]

**Detected**: [timestamp]

**Severity**: [P0-Critical / P1-High / P2-Medium / P3-Low]

**Symptoms**:
- [e.g., "Latency exceeded 30 seconds for 10 minutes"]
- [Logs, metrics, user reports]

**Impact**:
- [e.g., "Search results stale by 30+ seconds"]
- [Number of users affected]

**Timeline**:
- [HH:MM] Incident detected
- [HH:MM] Investigation started
- [HH:MM] Root cause identified
- [HH:MM] Mitigation applied
- [HH:MM] Service restored

**Root Cause**:
- [Technical explanation]

**Resolution**:
- [Steps taken to resolve]

**Prevention**:
- [Changes to prevent recurrence]
- [Monitoring improvements]
- [Documentation updates]

**Action Items**:
- [ ] [Task] (Owner, Due Date)
- [ ] [Task] (Owner, Due Date)

---

## Contact

For questions or issues not covered in this runbook:
- **Slack**: #data-infrastructure
- **On-call**: PagerDuty rotation
- **Escalation**: Platform Engineering Team Lead
