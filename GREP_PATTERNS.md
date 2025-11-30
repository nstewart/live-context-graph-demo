# Quick Reference: Grep Patterns for Demo

## Essential Grep Patterns

### 1. Show PostgreSQL Transactions (API Service)
```bash
docker-compose logs -f api | grep -E "🔵|📝|✅"
```

**What you'll see:**
- 🔵 PG_TXN_START - Transaction begins
- 📝 Subject details - Each entity being written
- ✅ PG_TXN_END - Transaction commits

**Example:**
```
🔵 PG_TXN_START: Writing 28 triples across 4 subjects
  📝 order:FM-12345: 5 properties (order_number, order_status, placed_by...)
  📝 orderline:FM-12345-001: 7 properties (line_of_order, line_product, quantity...)
  📝 orderline:FM-12345-002: 7 properties (line_of_order, line_product, quantity...)
  📝 orderline:FM-12345-003: 7 properties (line_of_order, line_product, quantity...)
✅ PG_TXN_END: Successfully wrote 28 triples
```

---

### 2. Show Materialize SUBSCRIBE Events (Search-Sync Service)
```bash
docker-compose logs -f search-sync | grep -E "📦|➕|🔄|❌|💾"
```

**What you'll see:**
- 📦 BATCH @ mz_ts=X - Events from same timestamp
- ➕ Inserts - New documents
- 🔄 Updates - Consolidated updates
- ❌ Deletes - Removed documents
- 💾 FLUSH → index - Write to OpenSearch

**Example:**
```
📦 BATCH @ mz_ts=1701234567890: Processing 28 events from orders_with_lines_mv
  ➕ Inserts: ['order:FM-12345', 'orderline:FM-12345-001', 'orderline:FM-12345-002', 'orderline:FM-12345-003']
💾 FLUSH → orders: 4 upserts, 0 deletes
```

---

### 3. Show Complete Flow (PostgreSQL → Materialize → OpenSearch)
```bash
docker-compose logs -f api search-sync | grep -E "🔵|📝|✅|📦|➕|🔄|❌|💾"
```

**What you'll see:**
Complete transaction lifecycle across all services

**Example:**
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

---

### 4. Show Just Materialize Timestamps
```bash
docker-compose logs -f search-sync | grep "mz_ts="
```

**What you'll see:**
```
📦 BATCH @ mz_ts=1701234567890: Processing 28 events from orders_with_lines_mv
📦 BATCH @ mz_ts=1701234567895: Processing 2 events from orders_with_lines_mv
```

**Use case:** Verify all events from one transaction share the same timestamp

---

### 5. Show Only Specific Index
```bash
docker-compose logs -f search-sync | grep "→ orders"
docker-compose logs -f search-sync | grep "→ inventory"
```

**What you'll see:**
```
💾 FLUSH → orders: 4 upserts, 0 deletes
💾 FLUSH → orders: 1 upserts, 0 deletes
```

---

### 6. Show UPDATE Consolidation Only
```bash
docker-compose logs -f search-sync | grep "🔄"
```

**What you'll see:**
```
  🔄 Updates: ['order:FM-12345']
```

**Use case:** Prove that DELETE + INSERT at same timestamp becomes UPDATE

---

## Common Combinations

### Debug: Why didn't my transaction propagate?
```bash
# Terminal 1: Watch everything
docker-compose logs -f api search-sync | grep -E "🔵|✅|📦|💾"

# Terminal 2: Make a change
curl -X POST http://localhost:8080/triples/batch ...

# Look for:
# 1. Did PG transaction commit? (✅)
# 2. Did SUBSCRIBE receive events? (📦)
# 3. Did OpenSearch flush succeed? (💾)
```

### Performance: How fast is the pipeline?
```bash
docker-compose logs api search-sync | grep -E "PG_TXN_START|FLUSH" | tail -20
```

Compare timestamps between PG_TXN_START and FLUSH to measure latency.

### Verification: Did specific document update?
```bash
docker-compose logs search-sync | grep "order:FM-12345"
```

---

## Emoji Quick Reference

| Emoji | Meaning | Service | Grep Pattern |
|-------|---------|---------|--------------|
| 🔵 | PostgreSQL transaction start | api | `grep "🔵"` |
| 📝 | Subject being written | api | `grep "📝"` |
| ✅ | PostgreSQL transaction end | api | `grep "✅"` |
| 📦 | Materialize SUBSCRIBE batch | search-sync | `grep "📦"` |
| ➕ | Insert operations | search-sync | `grep "➕"` |
| 🔄 | Update operations | search-sync | `grep "🔄"` |
| ❌ | Delete operations | search-sync | `grep "❌"` |
| 💾 | OpenSearch flush | search-sync | `grep "💾"` |

---

## Pro Tips

1. **Use `--line-buffered`** for real-time grep:
   ```bash
   docker-compose logs -f api search-sync | grep --line-buffered -E "🔵|📦|💾"
   ```

2. **Add color** to highlight patterns:
   ```bash
   docker-compose logs -f search-sync | grep --color=always -E "mz_ts=[0-9]+"
   ```

3. **Count operations** in logs:
   ```bash
   docker-compose logs search-sync | grep -c "➕ Inserts"
   docker-compose logs search-sync | grep -c "🔄 Updates"
   ```

4. **Extract timestamps** for analysis:
   ```bash
   docker-compose logs search-sync | grep -oP 'mz_ts=\K[0-9]+'
   ```

5. **Watch specific order ID**:
   ```bash
   ORDER_ID="order:FM-12345"
   docker-compose logs -f api search-sync | grep "$ORDER_ID"
   ```

---

## What to Demo

### Demo 1: Transactional Atomicity
**Command:**
```bash
docker-compose logs -f api search-sync | grep -E "🔵|📦|mz_ts="
```

**Action:** Create order with 3 line items via API

**Key Insight:** All tuples share same `mz_ts`

---

### Demo 2: UPDATE Consolidation
**Command:**
```bash
docker-compose logs -f search-sync | grep -E "📦|🔄|💾"
```

**Action:** Update order status in PostgreSQL

**Key Insight:** Shows 🔄 instead of ➕ + ❌

---

### Demo 3: Complete Pipeline
**Command:**
```bash
docker-compose logs -f api search-sync | grep -E "🔵|📝|✅|📦|➕|💾"
```

**Action:** Create order with line items

**Key Insight:** End-to-end flow in ~1-2 seconds
