# Data Model

This document describes the FreshMart data model, including the triple store schema and materialized views.

## Triple Store

### Core Concept

The system uses a **triple store** - a generic data model where all facts are represented as subject-predicate-object triples:

```
(subject_id, predicate, object_value, object_type)
```

**Example**:
```
("order:FM-1001", "order_status", "OUT_FOR_DELIVERY", "string")
("order:FM-1001", "placed_by", "customer:123", "entity_ref")
("order:FM-1001", "order_total_amount", "64.32", "float")
```

### Schema

```sql
CREATE TABLE triples (
  id            BIGSERIAL PRIMARY KEY,
  subject_id    TEXT NOT NULL,         -- 'prefix:id' format
  predicate     TEXT NOT NULL,         -- Property name
  object_value  TEXT NOT NULL,         -- Value as string
  object_type   TEXT NOT NULL,         -- Type for parsing
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_triple UNIQUE (subject_id, predicate, object_value)
);
```

### Subject ID Convention

All subjects use the format `prefix:id`:

| Prefix | Class | Example |
|--------|-------|---------|
| customer | Customer | customer:123 |
| store | Store | store:BK-01 |
| product | Product | product:milk-1L |
| inventory | InventoryItem | inventory:BK01-milk |
| order | Order | order:FM-1001 |
| order_line | OrderLine | order_line:FM1001-1 |
| courier | Courier | courier:C01 |
| task | DeliveryTask | task:T1001 |

### Object Types

| Type | Description | Storage | Example |
|------|-------------|---------|---------|
| string | Text | As-is | "John Doe" |
| int | Integer | Numeric string | "42" |
| float | Decimal | Numeric string | "19.99" |
| bool | Boolean | "true"/"false" | "true" |
| timestamp | DateTime | ISO 8601 | "2025-11-22T14:00:00Z" |
| date | Date | ISO 8601 | "2025-11-22" |
| entity_ref | Reference | Subject ID | "store:BK-01" |

## Materialized Views

For efficient operational queries, the system maintains denormalized views. In Materialize, these are computed in the **compute cluster** and indexed in the **serving cluster** for sub-millisecond lookups.

### View Architecture

| View | Purpose | Indexed |
|------|---------|---------|
| `orders_flat_mv` | Order headers with status | `orders_flat_idx` |
| `orders_search_source_mv` | Orders enriched with customer/store/delivery | `orders_search_source_idx` |
| `store_inventory_mv` | Inventory per store/product | `store_inventory_idx` |
| `courier_schedule_mv` | Couriers with assigned tasks | `courier_schedule_idx` |
| `stores_mv` | Store details | `stores_idx` |
| `customers_mv` | Customer details | `customers_idx` |

### orders_flat_mz

Flattened order data for quick lookups.

```sql
CREATE VIEW orders_flat AS
SELECT
  os.subject_id AS order_id,
  MAX(CASE WHEN t.predicate = 'order_number' THEN t.object_value END) AS order_number,
  MAX(CASE WHEN t.predicate = 'order_status' THEN t.object_value END) AS order_status,
  MAX(CASE WHEN t.predicate = 'order_store' THEN t.object_value END) AS store_id,
  MAX(CASE WHEN t.predicate = 'placed_by' THEN t.object_value END) AS customer_id,
  MAX(CASE WHEN t.predicate = 'delivery_window_start' THEN t.object_value END) AS delivery_window_start,
  MAX(CASE WHEN t.predicate = 'delivery_window_end' THEN t.object_value END) AS delivery_window_end,
  MAX(CASE WHEN t.predicate = 'order_total_amount' THEN t.object_value END)::DECIMAL AS order_total_amount,
  MAX(t.updated_at) AS effective_updated_at
FROM order_subjects os
LEFT JOIN triples t ON t.subject_id = os.subject_id
GROUP BY os.subject_id;
```

### store_inventory_mz

Current inventory levels per store/product.

```sql
CREATE VIEW store_inventory_flat AS
SELECT
  inv.subject_id AS inventory_id,
  MAX(CASE WHEN t.predicate = 'inventory_store' THEN t.object_value END) AS store_id,
  MAX(CASE WHEN t.predicate = 'inventory_product' THEN t.object_value END) AS product_id,
  MAX(CASE WHEN t.predicate = 'stock_level' THEN t.object_value END)::INT AS stock_level,
  MAX(CASE WHEN t.predicate = 'replenishment_eta' THEN t.object_value END) AS replenishment_eta,
  MAX(t.updated_at) AS effective_updated_at
FROM inventory_subjects inv
LEFT JOIN triples t ON t.subject_id = inv.subject_id
GROUP BY inv.subject_id;
```

### courier_schedule_mz

Couriers with their assigned tasks.

```sql
CREATE VIEW courier_schedule_flat AS
SELECT
  cs.subject_id AS courier_id,
  MAX(CASE WHEN t.predicate = 'courier_name' THEN t.object_value END) AS courier_name,
  MAX(CASE WHEN t.predicate = 'courier_home_store' THEN t.object_value END) AS home_store_id,
  MAX(CASE WHEN t.predicate = 'vehicle_type' THEN t.object_value END) AS vehicle_type,
  MAX(CASE WHEN t.predicate = 'courier_status' THEN t.object_value END) AS courier_status,
  json_agg(task_info) AS tasks,
  MAX(t.updated_at) AS effective_updated_at
FROM courier_subjects cs
LEFT JOIN triples t ON t.subject_id = cs.subject_id
LEFT JOIN courier_tasks ct ON ct.courier_id = cs.subject_id
GROUP BY cs.subject_id;
```

### stores_mv

Store details flattened from triples.

```sql
CREATE MATERIALIZED VIEW stores_mv IN CLUSTER compute AS
SELECT
  subject_id AS store_id,
  MAX(CASE WHEN predicate = 'store_name' THEN object_value END) AS store_name,
  MAX(CASE WHEN predicate = 'store_zone' THEN object_value END) AS store_zone,
  MAX(CASE WHEN predicate = 'store_address' THEN object_value END) AS store_address,
  MAX(CASE WHEN predicate = 'store_status' THEN object_value END) AS store_status,
  MAX(CASE WHEN predicate = 'store_capacity_orders_per_hour' THEN object_value END)::INT AS store_capacity_orders_per_hour,
  MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'store:%'
GROUP BY subject_id;
```

### customers_mv

Customer details flattened from triples.

```sql
CREATE MATERIALIZED VIEW customers_mv IN CLUSTER compute AS
SELECT
  subject_id AS customer_id,
  MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
  MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
  MAX(CASE WHEN predicate = 'customer_address' THEN object_value END) AS customer_address,
  MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;
```

### orders_search_source

Enriched order data for OpenSearch indexing.

```sql
CREATE VIEW orders_search_source AS
SELECT
  ofm.order_id,
  ofm.order_number,
  ofm.order_status,
  ofm.store_id,
  ofm.customer_id,
  ofm.delivery_window_start,
  ofm.delivery_window_end,
  ofm.order_total_amount,
  -- Customer details
  MAX(c.customer_name) AS customer_name,
  MAX(c.customer_email) AS customer_email,
  MAX(c.customer_address) AS customer_address,
  -- Store details
  MAX(s.store_name) AS store_name,
  MAX(s.store_zone) AS store_zone,
  -- Delivery info
  MAX(dt.assigned_to) AS assigned_courier_id,
  MAX(dt.task_status) AS delivery_task_status,
  MAX(dt.eta) AS delivery_eta,
  -- Sync timestamp
  GREATEST(ofm.effective_updated_at, MAX(c.updated_at), MAX(s.updated_at)) AS effective_updated_at
FROM orders_flat_mz ofm
LEFT JOIN customer_triples c ON c.subject_id = ofm.customer_id
LEFT JOIN store_triples s ON s.subject_id = ofm.store_id
LEFT JOIN delivery_tasks dt ON dt.order_id = ofm.order_id
GROUP BY ofm.order_id, ...;
```

## Sync Cursor Tracking

The search sync worker tracks its position:

```sql
CREATE TABLE sync_cursors (
  view_name TEXT PRIMARY KEY,
  last_synced_at TIMESTAMPTZ NOT NULL,
  last_synced_id TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Managing Triples

### Via Admin UI (Triples Browser)

The web Admin UI provides a **Triples Browser** (`/triples`) for visual management:

1. **Browse Entities**
   - Filter by entity type (order, customer, store, courier, etc.)
   - Search by subject ID
   - View total count of matching entities

2. **View Entity Details**
   - Click any subject to see all its triples
   - Navigate between related entities via entity_ref links

3. **Create Triples**
   - Add new triples with ontology-powered dropdowns:
     - **Subject ID**: Class prefix dropdown + ID input
     - **Predicate**: Filtered by subject's class from ontology
     - **Value**: Smart input based on range_kind:
       - `entity_ref`: Dropdown of existing entities of the target class
       - `boolean`: true/false dropdown
       - `datetime`: Date/time picker
       - `integer/decimal`: Number input
       - `string`: Text input

4. **Edit Triples**
   - Update values with type-appropriate inputs
   - Subject and predicate are locked (only value is editable)

5. **Delete Operations**
   - Delete individual triples
   - Delete entire subjects (all triples for an entity)

### Via API

```bash
# Create triple
POST /triples
{"subject_id": "order:FM-1001", "predicate": "order_status", "object_value": "DELIVERED", "object_type": "string"}

# Create batch
POST /triples/batch
[{"subject_id": "...", "predicate": "...", "object_value": "...", "object_type": "..."}]

# Update value
PATCH /triples/{id}
{"object_value": "NEW_VALUE"}

# Delete triple
DELETE /triples/{id}

# Delete all triples for a subject
DELETE /triples/subjects/order:FM-1001
```

## Querying Triples

### Get all triples for a subject

```sql
SELECT predicate, object_value, object_type
FROM triples
WHERE subject_id = 'order:FM-1001';
```

### Find subjects by class

```sql
SELECT DISTINCT subject_id
FROM triples
WHERE subject_id LIKE 'order:%';
```

### Get related entities

```sql
-- Find all orders for a customer
SELECT subject_id
FROM triples
WHERE predicate = 'placed_by'
  AND object_value = 'customer:123';
```

### Filter by property value

```sql
-- Orders with specific status
SELECT DISTINCT subject_id
FROM triples
WHERE predicate = 'order_status'
  AND object_value = 'OUT_FOR_DELIVERY';
```

## Performance Considerations

1. **Indexes**: Key indexes on `subject_id`, `predicate`, and combined
2. **Materialized Views**: Use for operational queries, not raw triples
3. **Cursor-based Sync**: Incremental updates to search index
4. **Batch Operations**: Use batch endpoints for bulk inserts
