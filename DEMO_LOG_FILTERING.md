# Demo: Log Filtering for Transactional Consistency

This guide shows how to use `docker-compose logs` to demonstrate that SUBSCRIBE updates correctly identify which OpenSearch documents to update based on Materialize timestamps.

## Quick Start

Run the automated demo:
```bash
./demo-transaction-logs.sh
```

## Manual Filtering Examples

### 1. Show All Batches with Timestamps
```bash
docker-compose logs -f search-sync | grep "📦 BATCH"
```

**Example Output:**
```
📦 BATCH @ mz_ts=1701234567890: Processing 28 events from orders_with_lines_mv (total received: 125)
```

**What it shows:** All events in this batch happened at the same Materialize timestamp (single transaction).

---

### 2. Show Document Operations
```bash
docker-compose logs -f search-sync | grep -E "➕|🔄|❌"
```

**Example Output:**
```
  ➕ Inserts: ['order:FM-12345', 'orderline:FM-12345-001', 'orderline:FM-12345-002', 'orderline:FM-12345-003']
  🔄 Updates: ['order:FM-67890']
  ❌ Deletes: ['order:FM-11111']
```

**What it shows:**
- **➕ Inserts** - New documents being created
- **🔄 Updates** - Documents updated via consolidation (DELETE + INSERT at same timestamp)
- **❌ Deletes** - Documents being removed

---

### 3. Show Flush Operations
```bash
docker-compose logs -f search-sync | grep "💾 FLUSH"
```

**Example Output:**
```
💾 FLUSH → orders: 4 upserts, 0 deletes
💾 FLUSH → inventory: 12 upserts, 2 deletes
```

**What it shows:** Bulk operations written to OpenSearch, grouped by index.

---

### 4. Full Transaction Flow
```bash
docker-compose logs -f search-sync | grep -E "📦|➕|🔄|❌|💾"
```

**Example Output (order creation with 3 line items):**
```
📦 BATCH @ mz_ts=1701234567890: Processing 28 events from orders_with_lines_mv (total received: 125)
  ➕ Inserts: ['order:FM-12345', 'orderline:FM-12345-001', 'orderline:FM-12345-002', 'orderline:FM-12345-003']
💾 FLUSH → orders: 4 upserts, 0 deletes
```

**Key Insight:** All 4 documents (1 order + 3 line items) share the **same mz_ts** because they were created in a single transaction.

---

### 5. Show UPDATE Consolidation
```bash
# Make an update
docker-compose exec db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='OUT_FOR_DELIVERY' WHERE subject_id='order:FM-12345' AND predicate='order_status';"

# Watch logs
docker-compose logs --tail=20 search-sync | grep -E "📦|🔄|💾"
```

**Example Output:**
```
📦 BATCH @ mz_ts=1701234567895: Processing 2 events from orders_with_lines_mv (total received: 127)
  🔄 Updates: ['order:FM-12345']
💾 FLUSH → orders: 1 upserts, 0 deletes
```

**Key Insight:**
- Materialize sends DELETE + INSERT for the same order at the same timestamp
- Worker consolidates them into a single UPDATE
- Only 1 upsert sent to OpenSearch (not 1 delete + 1 insert)

---

## Log Symbols Reference

| Symbol | Meaning | Service | Color |
|--------|---------|---------|-------|
| 🔵 | PostgreSQL transaction start | api | Blue |
| 📝 | Subject being written in transaction | api | Blue |
| ✅ | PostgreSQL transaction end | api | Green |
| 📦 | Batch received from SUBSCRIBE | search-sync | Blue |
| ➕ | Insert operations | search-sync | Green |
| 🔄 | Update operations (consolidated) | search-sync | Yellow |
| ❌ | Delete operations | search-sync | Red |
| 💾 | Flush to OpenSearch | search-sync | Blue |

---

## Show PostgreSQL Transactions

### View All Tuples Being Written in a Transaction
```bash
docker-compose logs -f api | grep -E "🔵|📝|✅"
```

**Example Output:**
```
🔵 PG_TXN_START: Writing 28 triples across 4 subjects
  📝 order:FM-12345: 5 properties (order_number, order_status, placed_by...)
  📝 orderline:FM-12345-001: 7 properties (line_of_order, line_product, quantity...)
  📝 orderline:FM-12345-002: 7 properties (line_of_order, line_product, quantity...)
  📝 orderline:FM-12345-003: 7 properties (line_of_order, line_product, quantity...)
✅ PG_TXN_END: Successfully wrote 28 triples
```

**What it shows:**
- All tuples written in a single PostgreSQL transaction
- Which subjects (order, line items) are affected
- How many properties each subject has

### Show Complete Flow: PostgreSQL → Materialize → OpenSearch
```bash
docker-compose logs -f api search-sync | grep -E "🔵|📝|✅|📦|➕|🔄|💾|mz_ts="
```

**Example Output:**
```
api          | 🔵 PG_TXN_START: Writing 28 triples across 4 subjects
api          |   📝 order:FM-12345: 5 properties (order_number, order_status, placed_by...)
api          |   📝 orderline:FM-12345-001: 7 properties (line_of_order, line_product, quantity...)
api          |   📝 orderline:FM-12345-002: 7 properties (line_of_order, line_product, quantity...)
api          |   📝 orderline:FM-12345-003: 7 properties (line_of_order, line_product, quantity...)
api          | ✅ PG_TXN_END: Successfully wrote 28 triples
search-sync  | 📦 BATCH @ mz_ts=1701234567890: Processing 28 events from orders_with_lines_mv
search-sync  |   ➕ Inserts: ['order:FM-12345', 'orderline:FM-12345-001', 'orderline:FM-12345-002', 'orderline:FM-12345-003']
search-sync  | 💾 FLUSH → orders: 4 upserts, 0 deletes
```

**Key Insight:** The 28 triples written in PostgreSQL become 28 events in Materialize (all with the same `mz_ts`), which get consolidated into 4 OpenSearch documents.

---

## Common Demo Scenarios

### Scenario 1: Create Order with Line Items (Transactional)

**Action:**
```bash
# Use the UI or API to create an order with 3 products
curl -X POST http://localhost:8080/triples/batch -H "Content-Type: application/json" -d '[...]'
```

**Expected Logs:**
```
📦 BATCH @ mz_ts=XXXXX: Processing 28 events from orders_with_lines_mv
  ➕ Inserts: ['order:FM-XXXXX', 'orderline:FM-XXXXX-001', 'orderline:FM-XXXXX-002', 'orderline:FM-XXXXX-003']
💾 FLUSH → orders: 4 upserts, 0 deletes
```

**Demonstrates:** All tuples (order + line items) share the same `mz_ts`, proving they're part of the same transaction.

---

### Scenario 2: Update Order Status (Consolidated UPDATE)

**Action:**
```bash
docker-compose exec db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='DELIVERED' WHERE subject_id='order:FM-XXXXX' AND predicate='order_status';"
```

**Expected Logs:**
```
📦 BATCH @ mz_ts=YYYYY: Processing 2 events from orders_with_lines_mv
  🔄 Updates: ['order:FM-XXXXX']
💾 FLUSH → orders: 1 upserts, 0 deletes
```

**Demonstrates:**
- Different timestamp than the insert (YYYYY ≠ XXXXX)
- DELETE + INSERT consolidated into UPDATE
- Only 1 OpenSearch operation instead of 2

---

### Scenario 3: Update Product Price (Cascading Updates)

**Action:**
```bash
# Update a product's base price
docker-compose exec db psql -U postgres -d freshmart -c \
  "UPDATE triples SET object_value='15.99' WHERE subject_id='product:prod0001' AND predicate='base_price';"
```

**Expected Logs:**
```
📦 BATCH @ mz_ts=ZZZZZ: Processing 45 events from inventory_items_with_dynamic_pricing
  🔄 Updates: ['inventory:INV-001', 'inventory:INV-002', 'inventory:INV-003', ...]
💾 FLUSH → inventory: 12 upserts, 0 deletes
```

**Demonstrates:**
- Single product update cascades to multiple inventory records
- All updates at the same timestamp (denormalization)
- Smart consolidation reduces OpenSearch operations

---

## Advanced Filtering

### Show Only Specific Index
```bash
docker-compose logs -f search-sync | grep "→ orders"
```

### Show Only Timestamps
```bash
docker-compose logs -f search-sync | grep -oP 'mz_ts=\K[0-9]+'
```

### Count Events by Type
```bash
docker-compose logs search-sync | grep -c "➕ Inserts"
docker-compose logs search-sync | grep -c "🔄 Updates"
docker-compose logs search-sync | grep -c "❌ Deletes"
```

### Watch Multiple Services
```bash
docker-compose logs -f search-sync api | grep -E "📦|💾|POST /triples"
```

---

## Troubleshooting

### No Logs Appearing?

1. Check service is running:
   ```bash
   docker-compose ps search-sync
   ```

2. Check LOG_LEVEL:
   ```bash
   docker-compose exec search-sync env | grep LOG_LEVEL
   # Should be INFO or DEBUG
   ```

3. Restart with verbose logging:
   ```bash
   docker-compose up -d search-sync
   docker-compose logs -f search-sync
   ```

### Logs Too Verbose?

Filter to just transaction boundaries:
```bash
docker-compose logs -f search-sync | grep -E "BATCH|FLUSH"
```

---

## Performance Metrics from Logs

### Average Events per Batch
```bash
docker-compose logs search-sync | \
  grep "BATCH" | \
  grep -oP 'Processing \K[0-9]+' | \
  awk '{sum+=$1; n++} END {print "Average:", sum/n}'
```

### Total Events Processed
```bash
docker-compose logs search-sync | \
  grep "total received" | \
  tail -1 | \
  grep -oP 'total received: \K[0-9]+'
```

---

## Tips for Live Demos

1. **Split Terminal** - Show logs in one pane, run commands in another
2. **Use Colors** - The emojis make it easy to spot different operations
3. **Filter Aggressively** - Too many logs overwhelm the audience
4. **Pause Between Actions** - Give logs time to appear (1-2 seconds)
5. **Highlight Timestamps** - Point out when timestamps are the same vs different

**Best Command for Demos:**
```bash
docker-compose logs -f --tail=0 search-sync | grep --color=always -E "📦|➕|🔄|❌|💾|mz_ts="
```

This shows just the important events with color highlighting.
