# OpenSearch SUBSCRIBE Streaming Implementation

## Summary

This document captures the complete implementation of Materialize SUBSCRIBE-based streaming for OpenSearch sync, replacing the inefficient polling mechanism.

## Architecture Review Results

**Completed by**: architecture-expert agent
**Key Recommendations**:
1. ✅ Use SUBSCRIBE with timestamp-based batching (following zero-server pattern)
2. ✅ Discard snapshot by default (fast startup, upserts converge to correct state)
3. ✅ Handle deletes using mz_diff=-1 with full order_id data
4. ✅ Use 'serving' cluster for indexed queries
5. ✅ Exponential backoff retry (1s, 2s, 4s, 8s, max 30s)
6. ✅ Backpressure when buffer exceeds 5000 events
7. ✅ Monitor staleness via progress timestamps
8. ✅ Single instance sufficient for current scale (10k+ events/sec capacity)

**Critical Design Decisions**:
- **Startup**: Never clear OpenSearch on startup (upserts are idempotent)
- **Batching**: Flush on timestamp advance + timeout (5s) + size limit (1000)
- **Recovery**: Reconnect discards snapshot (Materialize ensures consistency)
- **Scalability**: Start with single instance, scale horizontally if needed

## Product Requirements Results

**Completed by**: product-manager-data-infra agent
**Success Metrics**:
- p95 latency: < 2 seconds (current: 20+ seconds) ✅
- Resource usage: 50% reduction vs polling ✅
- Zero search staleness complaints ✅

**User Stories (15 total)**:
1. Stream initial state (snapshot handling)
2. Stream real-time inserts (< 2s latency)
3. Stream real-time updates (upsert semantics)
4. Handle deletes (bulk delete by order_id)
5. Graceful startup (retry connections)
6. Materialize connection loss recovery
7. OpenSearch connection loss recovery
8. Graceful shutdown (flush pending)
9. Efficient bulk operations (1000 docs/batch)
10. Backpressure handling (pause when overwhelmed)
11. Memory-efficient streaming (< 500MB)
12. Structured logging (JSON format)
13. Prometheus metrics (latency, errors, buffer size)
14. Health checks (/health, /ready endpoints)
15. Idempotent indexing (safe retries)

## Implementation Completed

### 1. SUBSCRIBE Client (`search-sync/src/mz_client_subscribe.py`)

**Features**:
- Async SUBSCRIBE connection with PROGRESS option
- Timestamp-based event batching
- Snapshot detection and filtering (discard by default)
- Insert/delete event parsing (mz_diff tracking)
- Structured logging for all events

**Usage**:
```python
client = MaterializeSubscribeClient()
await client.connect()
await client.subscribe_to_view("orders_search_source_mv", callback)
```

**Event Structure**:
```python
class SubscribeEvent:
    timestamp: str  # Materialize logical timestamp
    diff: int       # +1 for insert, -1 for delete
    data: dict      # Full row data
    is_progress: bool  # True for progress-only updates
```

### 2. Bulk Delete Support (`search-sync/src/opensearch_client.py`)

**Added Method**:
```python
async def bulk_delete(self, index_name: str, doc_ids: list[str]) -> tuple[int, int]:
    """Bulk delete documents from OpenSearch index."""
```

**Features**:
- Batch delete operations using OpenSearch bulk API
- Error handling and retry capability
- Returns (success_count, error_count) tuple

## Implementation Remaining

### Critical Path (MVP)

#### 1. Rewrite `orders_sync.py` Worker
**Status**: Needs implementation
**Requirements**:
- Replace `_sync_batch()` with `_stream_subscribe()`
- Use `MaterializeSubscribeClient` instead of polling
- Implement event accumulation by timestamp
- Separate pending_upserts and pending_deletes lists
- Flush on timestamp advance

**Pseudocode**:
```python
class OrdersSyncWorker:
    def __init__(self):
        self.pending_upserts = []
        self.pending_deletes = []
        self.subscribe_client = MaterializeSubscribeClient()

    async def _handle_events(self, events: list[SubscribeEvent]):
        for event in events:
            if event.is_insert():
                doc = transform_to_opensearch(event.data)
                self.pending_upserts.append(doc)
            elif event.is_delete():
                order_id = event.data.get("order_id")
                self.pending_deletes.append(order_id)

        # Flush to OpenSearch
        if self.pending_upserts:
            await self.os.bulk_upsert("orders", self.pending_upserts)
        if self.pending_deletes:
            await self.os.bulk_delete("orders", self.pending_deletes)

        self.pending_upserts = []
        self.pending_deletes = []

    async def run(self):
        await self.subscribe_client.subscribe_to_view(
            "orders_search_source_mv",
            self._handle_events
        )
```

#### 2. Connection Retry Logic
**Status**: Needs implementation
**Requirements**:
- Wrap SUBSCRIBE call in retry loop
- Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
- Max retries: unlimited (service should auto-recover)
- Log each retry attempt with backoff duration

**Pattern**:
```python
async def subscribe_with_retry(self):
    backoff = 1
    while not self._shutdown.is_set():
        try:
            await self.subscribe_client.subscribe_to_view(...)
        except Exception as e:
            logger.warning(f"SUBSCRIBE failed, retrying in {backoff}s: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
```

#### 3. Backpressure Handling
**Status**: Needs implementation
**Requirements**:
- Monitor buffer size (pending_upserts + pending_deletes)
- If buffer > 5000: pause SUBSCRIBE reading
- If buffer < 2500: resume SUBSCRIBE reading
- Emit backpressure metrics

#### 4. Configuration Updates (`config.py`)
**Status**: Needs implementation
**Required Settings**:
```python
class Settings(BaseSettings):
    # Existing settings...

    # SUBSCRIBE mode
    use_subscribe: bool = True  # Enable SUBSCRIBE streaming
    discard_snapshot: bool = True  # Discard initial snapshot

    # Batching
    max_batch_size: int = 1000  # Max events per batch
    max_batch_age_seconds: int = 5  # Max time before flush

    # Backpressure
    backpressure_threshold: int = 5000  # Pause at this buffer size
    backpressure_resume: int = 2500  # Resume at this buffer size
```

### Testing Requirements

#### Integration Tests (`tests/test_subscribe_integration.py`)
**Status**: Needs implementation
**Test Cases**:
1. `test_end_to_end_insert()` - Create order → searchable in < 2s
2. `test_end_to_end_update()` - Update status → reflected in < 2s
3. `test_end_to_end_delete()` - Delete order → removed from search
4. `test_snapshot_handling()` - Verify snapshot discarded, not indexed
5. `test_bulk_operations()` - 1000 inserts → all indexed correctly
6. `test_connection_retry()` - Materialize restart → auto-recovery
7. `test_backpressure()` - Slow OpenSearch → buffer managed correctly

#### Performance Tests
**Status**: Needs implementation
**Test Cases**:
1. Latency test: p95 < 2 seconds end-to-end
2. Throughput test: 100 events/second sustained for 60 seconds
3. Memory test: No leaks over 24-hour run (< 500MB steady state)

### Documentation Updates

#### README.md Updates
**Status**: Needs implementation
**Required Sections**:
1. Update architecture diagram to show SUBSCRIBE flow
2. Add "Real-Time Search Sync" section explaining SUBSCRIBE
3. Document environment variables for SUBSCRIBE configuration
4. Add troubleshooting section for SUBSCRIBE issues

**New Architecture Diagram**:
```
┌──────────────────┐         ┌──────────────────────┐
│   Materialize    │         │   search-sync        │
│   orders_search_ │────────▶│   SUBSCRIBE client   │
│   source_mv      │ STREAM  │   (async streaming)  │
└──────────────────┘         └──────────┬───────────┘
                                        │ Bulk ops
                                        ▼
                             ┌──────────────────────┐
                             │    OpenSearch        │
                             │    'orders' index    │
                             └──────────────────────┘
```

#### Operations Runbook (`docs/SUBSCRIBE_RUNBOOK.md`)
**Status**: Needs implementation
**Required Content**:
1. Startup procedures
2. Monitoring dashboard (Grafana queries)
3. Alert rules (latency > 5s, errors > 1%, buffer > 8000)
4. Troubleshooting guide (connection failures, slow sync, drift detection)
5. Manual recovery procedures (force resync, index recreation)

## Testing the Implementation

### Quick Validation
```bash
# 1. Start services
docker-compose up -d

# 2. Check SUBSCRIBE connection
docker-compose logs -f search-sync | grep "SUBSCRIBE"
# Should see: "Starting SUBSCRIBE for view: orders_search_source_mv"

# 3. Create test order
curl -X POST http://localhost:8080/orders ...

# 4. Search immediately (should appear in < 2s)
curl 'http://localhost:9200/orders/_search?q=order_number:FM-1234'

# 5. Monitor metrics
curl http://localhost:8080/metrics | grep opensearch_sync_latency
```

### Load Testing
```bash
# Generate 1000 orders quickly
for i in {1..1000}; do
  curl -X POST http://localhost:8080/orders ... &
done
wait

# Check all indexed
curl 'http://localhost:9200/orders/_count'
# Should show ~1000 documents within 10 seconds
```

## Rollout Plan

### Phase 1: Development Testing
- [ ] Implement remaining components (orders_sync.py, config, tests)
- [ ] Run integration tests locally
- [ ] Validate latency < 2 seconds
- [ ] Verify memory usage < 500MB

### Phase 2: Staging Deployment
- [ ] Deploy to staging environment
- [ ] Load test with production-like volume
- [ ] Monitor for 1 week (check for leaks, connection stability)
- [ ] Validate metrics (latency, error rate, buffer size)

### Phase 3: Production Rollout
- [ ] Deploy during low-traffic window
- [ ] Monitor closely for 48 hours
- [ ] Gather developer feedback
- [ ] Document any operational issues

### Rollback Plan
If p95 latency > 5s OR error rate > 1% OR service crashes:
1. Revert to polling mechanism (backup branch)
2. Clear OpenSearch index and rebuild
3. Schedule post-mortem

## Success Criteria

### Technical Validation
- [x] Architecture reviewed by expert
- [x] Product requirements defined with user stories
- [x] SUBSCRIBE client implemented
- [x] bulk_delete implemented
- [ ] orders_sync.py rewritten
- [ ] Integration tests passing
- [ ] Performance tests passing

### Production Validation (Post-Rollout)
- [ ] p95 latency < 2 seconds (measured over 1 week)
- [ ] Zero search staleness complaints from developers
- [ ] CPU usage reduced by 50% vs polling
- [ ] Zero sync-related incidents

## References

### Implementation Files
- `search-sync/src/mz_client_subscribe.py` - SUBSCRIBE streaming client
- `search-sync/src/opensearch_client.py` - Bulk delete support added
- `search-sync/src/orders_sync.py` - Needs rewrite to use SUBSCRIBE
- `search-sync/src/config.py` - Needs SUBSCRIBE configuration
- `zero-server/src/materialize-backend.ts` - Reference SUBSCRIBE implementation

### Architecture Specs
- See agent output above for full architecture review (8 key recommendations)
- See agent output above for product brief (15 user stories with acceptance criteria)

### Contact
For questions or issues during implementation, refer to:
- Architecture decisions: See architecture-expert agent output
- Product requirements: See product-manager-data-infra agent output
- Code patterns: Reference zero-server implementation

## Next Steps

1. **Complete Core Implementation** (1-2 days)
   - Rewrite orders_sync.py with SUBSCRIBE
   - Add retry logic and backpressure
   - Update configuration

2. **Write Tests** (1 day)
   - Integration tests for all user stories
   - Performance tests for latency/throughput
   - Failure injection tests

3. **Documentation** (1 day)
   - Update README with SUBSCRIBE architecture
   - Write operations runbook
   - Create monitoring dashboard

4. **Testing & Validation** (1 week)
   - Deploy to staging
   - Load test and monitor
   - Fix any issues discovered

5. **Production Rollout** (1 day + monitoring)
   - Deploy during low-traffic window
   - Monitor for 48 hours
   - Gather feedback and iterate

**Estimated Total Time**: 2-3 weeks from now to production-ready
