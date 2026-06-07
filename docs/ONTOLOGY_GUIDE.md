# Ontology Guide: Adding Ontological Elements

This comprehensive guide explains how to extend the FreshMart ontology with new entity types and create corresponding Materialize views to support different use cases.

## Table of Contents

- [Core Concepts](#core-concepts)
- [When to Materialize Views](#when-to-materialize-views-in-materialize)
- [Step-by-Step: Adding a New Entity Type](#step-by-step-adding-a-new-entity-type)
- [Using the Ontology to Create Business Objects](#using-the-ontology-to-create-business-objects)
- [Common Patterns](#common-patterns)
- [Complete Workflow Summary](#summary-the-complete-workflow)

## Core Concepts

### 1. The Triple Store Foundation

All data is stored as subject-predicate-object triples:

```
subject_id: "customer:123"
predicate: "customer_name"
object_value: "Alex Thompson"
object_type: "string"
```

The triple store is your **governed source of truth** - all writes flow through it with ontology validation.

### 2. Ontology = Your Schema

The ontology defines:

- **Classes**: Entity types (Customer, Order, Store) with a unique prefix
- **Properties**: Allowed predicates with domain (which class) and range (data type or target class)
- **Validation Rules**: Domain constraints, range constraints, required fields

### 3. CQRS Pattern

- **Writes**: Triple store (PostgreSQL) → validated, governed, normalized
- **Reads**: Materialized views (Materialize) → denormalized, indexed, optimized

### 4. Materialize Three-Tier Architecture

```
Ingest Cluster  → CDC from PostgreSQL (pg_source)
Compute Cluster → Materialized views (transform triples into entities)
Serving Cluster → Indexes (fast lookups for queries)
```

## When to Materialize Views in Materialize

Following the **Materialize MCP policy**, here's when to create different view types:

### Base Entity Views (Regular Views)

Create **regular views** for intermediate transformations when:

- Flattening triples into entity-shaped records
- The view will be consumed by other views (not directly queried)
- Used as building blocks for final materialized views

```sql
-- Example: customers_flat (intermediate view)
CREATE VIEW customers_flat AS
SELECT
    subject_id AS customer_id,
    MAX(CASE WHEN predicate = 'customer_name' THEN object_value END) AS customer_name,
    MAX(CASE WHEN predicate = 'customer_email' THEN object_value END) AS customer_email,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'customer:%'
GROUP BY subject_id;
```

### Materialized Views (IN CLUSTER compute)

Create **materialized views** when:

- This is a "topmost" view that will be directly queried by applications
- The view needs to be consumed by consumers on a **different cluster** (compute → serving)
- You want results persisted and incrementally maintained
- The view enriches base entities with joins to other entities

**Two Patterns:**

**Pattern A: Materialize the view definition directly**

```sql
-- Define transformation and materialize in one step
CREATE MATERIALIZED VIEW orders_flat_mv IN CLUSTER compute AS
SELECT
    subject_id AS order_id,
    MAX(CASE WHEN predicate = 'order_number' THEN object_value END) AS order_number,
    MAX(CASE WHEN predicate = 'order_status' THEN object_value END) AS order_status,
    MAX(CASE WHEN predicate = 'order_store' THEN object_value END) AS store_id,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;
```

**Pattern B: Materialize from a regular view (RECOMMENDED)**

```sql
-- Step 1: Define the transformation logic once in a regular view
CREATE VIEW orders_flat AS
SELECT
    subject_id AS order_id,
    MAX(CASE WHEN predicate = 'order_number' THEN object_value END) AS order_number,
    MAX(CASE WHEN predicate = 'order_status' THEN object_value END) AS order_status,
    MAX(CASE WHEN predicate = 'order_store' THEN object_value END) AS store_id,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'order:%'
GROUP BY subject_id;

-- Step 2: Materialize the view (no duplication!)
CREATE MATERIALIZED VIEW orders_flat_mv IN CLUSTER compute AS
SELECT * FROM orders_flat;
```

**Why Pattern B is better:**

- ✅ **No duplication** - Transformation logic defined once in the base view
- ✅ **Flexibility** - Can create multiple materialized views from the same base view
- ✅ **Testing** - Can query the regular view directly for development/debugging
- ✅ **Clarity** - Clear separation between transformation logic and materialization

**Example: Multiple materialized views from one base view**

```sql
-- Base view with transformation logic (defined once)
CREATE VIEW orders_flat AS
SELECT subject_id AS order_id, ...
FROM triples WHERE subject_id LIKE 'order:%' GROUP BY subject_id;

-- Materialize for general queries
CREATE MATERIALIZED VIEW orders_flat_mv IN CLUSTER compute AS
SELECT * FROM orders_flat;

-- Materialize with filters for specific use cases
CREATE MATERIALIZED VIEW active_orders_mv IN CLUSTER compute AS
SELECT * FROM orders_flat
WHERE order_status IN ('CREATED', 'PICKING', 'OUT_FOR_DELIVERY');

-- Both materialized views share the same transformation logic!
```

### Indexes (IN CLUSTER serving ON materialized views)

**Always create indexes** on materialized views when:

- The view is queried by applications/APIs
- You need low-latency lookups
- The view powers a user-facing feature

```sql
-- Example: Make orders queryable with low latency
CREATE INDEX orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);
```

## Step-by-Step: Adding a New Entity Type

Let's walk through adding a new **"Promotion"** entity to support marketing campaigns.

### Step 1: Define the Ontology

#### 1a. Create the Class

Choose a unique prefix and create the class:

```bash
# Connect to PostgreSQL
PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d freshmart

# Create the Promotion class
INSERT INTO ontology_classes (class_name, prefix, description)
VALUES ('Promotion', 'promo', 'A marketing promotion or discount campaign');
```

#### 1b. Define Properties

Think about what attributes promotions need:

```sql
-- Promotion code (required string)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'promo_code', id, 'string', TRUE, 'Unique promotion code (e.g., SUMMER25)'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Discount percentage (required float)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'discount_percent', id, 'float', TRUE, 'Discount percentage (0.0 to 100.0)'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Valid from date (required timestamp)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'valid_from', id, 'timestamp', TRUE, 'Promotion start date'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Valid until date (required timestamp)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'valid_until', id, 'timestamp', TRUE, 'Promotion end date'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Applicable store (optional entity reference to Store)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_required, description)
SELECT 'promo_store', p.id, 'entity_ref', s.id, FALSE, 'Store where promotion is valid (NULL = all stores)'
FROM ontology_classes p, ontology_classes s
WHERE p.class_name = 'Promotion' AND s.class_name = 'Store';

-- Active status (required boolean)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'is_active', id, 'bool', TRUE, 'Whether promotion is currently active'
FROM ontology_classes WHERE class_name = 'Promotion';
```

**Alternative: Use the Admin UI**

You can also use the Admin UI at http://localhost:5173:

1. Navigate to "Ontology Properties"
2. Find the "Promotion" section
3. Click "Add Property" to create each property with the form

#### 1c. Extend Existing Classes (if needed)

If orders can use promotions, add a relationship property to the Order class:

```sql
-- Add promo_applied property to Order class
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_required, description)
SELECT 'promo_applied', o.id, 'entity_ref', p.id, FALSE, 'Promotion code applied to this order'
FROM ontology_classes o, ontology_classes p
WHERE o.class_name = 'Order' AND p.class_name = 'Promotion';
```

### Step 2: Write Triples

Now you can create promotion entities:

```bash
# Create a promotion with all properties
curl -X POST http://localhost:8080/triples/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"subject_id": "promo:SUMMER25", "predicate": "promo_code", "object_value": "SUMMER25", "object_type": "string"},
    {"subject_id": "promo:SUMMER25", "predicate": "discount_percent", "object_value": "15.0", "object_type": "float"},
    {"subject_id": "promo:SUMMER25", "predicate": "valid_from", "object_value": "2025-06-01T00:00:00Z", "object_type": "timestamp"},
    {"subject_id": "promo:SUMMER25", "predicate": "valid_until", "object_value": "2025-08-31T23:59:59Z", "object_type": "timestamp"},
    {"subject_id": "promo:SUMMER25", "predicate": "promo_store", "object_value": "store:BK-01", "object_type": "entity_ref"},
    {"subject_id": "promo:SUMMER25", "predicate": "is_active", "object_value": "true", "object_type": "bool"}
  ]'

# Apply promotion to an order
curl -X POST http://localhost:8080/triples \
  -H "Content-Type: application/json" \
  -d '{
    "subject_id": "order:FM-1001",
    "predicate": "promo_applied",
    "object_value": "promo:SUMMER25",
    "object_type": "entity_ref"
  }'
```

The ontology validator will ensure:

- ✅ Subject prefix `promo:` matches the Promotion class
- ✅ All predicates are defined for the Promotion class
- ✅ Data types match (string, float, timestamp, bool, entity_ref)
- ✅ Entity references point to valid classes (Store)
- ✅ Required fields are present

### Step 3: Create Materialize Views

#### 3a. Create Base View (Regular View)

First, flatten the triples into an entity shape:

```sql
-- Intermediate view for promotions
CREATE VIEW promotions_flat AS
SELECT
    subject_id AS promo_id,
    MAX(CASE WHEN predicate = 'promo_code' THEN object_value END) AS promo_code,
    MAX(CASE WHEN predicate = 'discount_percent' THEN object_value END)::DECIMAL(5,2) AS discount_percent,
    MAX(CASE WHEN predicate = 'valid_from' THEN object_value END)::TIMESTAMPTZ AS valid_from,
    MAX(CASE WHEN predicate = 'valid_until' THEN object_value END)::TIMESTAMPTZ AS valid_until,
    MAX(CASE WHEN predicate = 'promo_store' THEN object_value END) AS store_id,
    MAX(CASE WHEN predicate = 'is_active' THEN object_value END)::BOOLEAN AS is_active,
    MAX(updated_at) AS effective_updated_at
FROM triples
WHERE subject_id LIKE 'promo:%'
GROUP BY subject_id;
```

#### 3b. Create Enriched View with Store Details

Create a view that joins promotions with store information:

```sql
-- Regular view with store enrichment (defines the logic)
CREATE VIEW promotions_enriched AS
SELECT
    p.promo_id,
    p.promo_code,
    p.discount_percent,
    p.valid_from,
    p.valid_until,
    p.store_id,
    p.is_active,
    s.store_name,
    s.store_zone,
    p.effective_updated_at
FROM promotions_flat p
LEFT JOIN stores_flat s ON s.store_id = p.store_id;

-- Materialize the enriched view (no duplication!)
-- IMPORTANT: Must be IN CLUSTER compute for cross-cluster materialization
CREATE MATERIALIZED VIEW promotions_mv IN CLUSTER compute AS
SELECT * FROM promotions_enriched;
```

**Important Notes:**

- **`IN CLUSTER compute`** is required because the serving cluster (where indexes live) will read from this materialized view
- **`mz_now()` restriction**: We **cannot** use `mz_now()` in a CASE expression or SELECT clause - it can only be used in WHERE/HAVING clauses for temporal filtering

#### 3c. Create Index (IN CLUSTER serving)

Make it queryable with low latency:

```sql
CREATE INDEX promotions_idx IN CLUSTER serving ON promotions_mv (promo_id);
```

#### 3d. Enrich Existing Views (Zero-Downtime Pattern)

If orders reference promotions, create a new enriched view without disrupting the existing one:

```sql
-- Create v2 of orders view with promotion enrichment (regular view, not materialized)
-- IMPORTANT: Includes ALL fields from original orders_search_source_mv PLUS promotion fields
CREATE VIEW orders_with_promotions AS
SELECT
    -- Order basics
    o.order_id,
    o.order_number,
    o.order_status,
    o.store_id,
    o.customer_id,
    o.delivery_window_start,
    o.delivery_window_end,
    o.order_total_amount,
    -- Customer details (denormalized)
    c.customer_name,
    c.customer_email,
    c.customer_address,
    -- Store details (denormalized)
    s.store_name,
    s.store_zone,
    s.store_address,
    -- Delivery task details
    dt.assigned_courier_id,
    dt.task_status AS delivery_task_status,
    dt.eta AS delivery_eta,
    -- Promotion enrichment (NEW!)
    promo.promo_id,
    promo.promo_code,
    promo.discount_percent,
    -- Computed: Apply discount if promo exists, otherwise use original total
    CASE
        WHEN promo.discount_percent IS NOT NULL THEN
            o.order_total_amount * (1 - promo.discount_percent / 100.0)
        ELSE
            o.order_total_amount
    END AS order_total_amount_with_discounts,
    -- Effective timestamp considering all joined entities
    GREATEST(
        o.effective_updated_at,
        c.effective_updated_at,
        s.effective_updated_at,
        dt.effective_updated_at,
        COALESCE(promo.effective_updated_at, o.effective_updated_at)
    ) AS effective_updated_at
FROM orders_flat_mv o
LEFT JOIN customers_flat c ON c.customer_id = o.customer_id
LEFT JOIN stores_flat s ON s.store_id = o.store_id
LEFT JOIN delivery_tasks_flat dt ON dt.order_id = o.order_id
LEFT JOIN (
    SELECT
        t.subject_id AS order_id,
        p.promo_id,
        p.promo_code,
        p.discount_percent,
        p.effective_updated_at
    FROM triples t
    JOIN promotions_flat p ON p.promo_id = t.object_value
    WHERE t.predicate = 'promo_applied'
) promo ON promo.order_id = o.order_id;

-- Test the view first
SELECT * FROM orders_with_promotions LIMIT 10;

-- When ready to deploy: Create new materialized view in compute cluster
CREATE MATERIALIZED VIEW orders_with_promotions_mv IN CLUSTER compute AS
SELECT * FROM orders_with_promotions;

-- Create index in serving cluster
CREATE INDEX orders_with_promotions_idx IN CLUSTER serving
ON orders_with_promotions_mv (order_id);
```

**Zero-Downtime Deployment Steps:**

1. ✅ Create the new regular view `orders_with_promotions` (no materialization)
2. ✅ Test queries against the view to validate logic
3. ✅ Materialize the view as `orders_with_promotions_mv` when ready
4. ✅ Create indexes on the new materialized view
5. ✅ Update applications to point to the new view
6. ✅ Verify production traffic works correctly
7. ✅ Deprecate and drop old view after cutover

### Step 4: Sync Enriched Orders to OpenSearch

Order documents reach OpenSearch through a Kafka pipeline, not a Python sync worker. Materialize publishes the orders view to a Kafka topic via a Debezium-envelope Avro `CREATE SINK`, and a Kafka Connect OpenSearch sink connector writes those records into the `orders` index. There is no per-change service to restart — you re-register the connector with its updated config.

To surface the new promotion fields in search, extend the view that feeds the sink, add any new embedded/mapped fields, then re-register the connector.

**4a. Feed the Sink From the Enriched View**

Make sure the view published to the `orders` Kafka topic includes the promotion fields. In this demo that is `orders_with_lines_mv` — extend it (or the view it selects from) to carry `promo_id`, `promo_code`, `discount_percent`, and `order_total_amount_with_discounts`, mirroring the enrichment you added in Step 3d. Once the view emits the new columns, the `CREATE SINK ... FORMAT AVRO ... ENVELOPE DEBEZIUM` definition picks them up automatically.

**4b. Embed New String Columns (Optional)**

The orders connector runs an embedding SMT that re-embeds the `embedding_text` column only when it changes. If you want a new string field (e.g. `promo_code`) to contribute to semantic search, add it to the connector's embedded columns in `kafka-connect/connectors/orders-opensearch-sink.json`:

```json
"transforms.embed.embedded.columns": "...,promo_code"
```

The SMT calls `embedding-service` (`/v1/embeddings`, BAAI/bge-small-en-v1.5, 384-dim) and writes the vector to `embedding_text_embedding`.

**4c. Update the OpenSearch Index Template**

If a new field needs an explicit mapping, update the composable index template at `kafka-connect/opensearch-templates/orders.json` (applied/pre-created by `connect-init`):

```json
"properties": {
  "promo_id": { "type": "keyword" },
  "promo_code": {
    "type": "text",
    "fields": { "keyword": { "type": "keyword" } }
  },
  "discount_percent": { "type": "float" },
  "order_total_amount_with_discounts": { "type": "float" }
}
```

**4d. Re-register the Connector**

Apply the updated connector config by PUTting it to the Kafka Connect REST API — no service restart is needed per change:

```bash
curl -X PUT http://localhost:8083/connectors/orders-opensearch-sink/config \
  -H "Content-Type: application/json" \
  -d @kafka-connect/connectors/orders-opensearch-sink.json

# Watch the connector pick up and index the new fields
docker compose logs -f kafka-connect
```

### Step 5: Update Agent Tools to Expose Promotion Fields

Modify `agents/src/tools/tool_search_orders.py` to include promotion fields:

**5a. Update Docstring:**

```python
"""
Search for FreshMart orders using natural language.

Use this tool to find orders by:
- Customer name (e.g., "Alex Thompson")
- Customer address (partial match)
- Order number (e.g., "FM-1001")
- Store name or zone
- Promotion code (e.g., "SUMMER25")  # ADD THIS
"""
```

**5b. Add Promo Code to Search Fields:**

```python
"multi_match": {
    "query": query,
    "fields": [
        "order_number^3",
        "customer_name^2",
        "promo_code^2",  # ADD THIS
        "customer_address",
        "store_name",
        "store_zone",
    ],
    "type": "best_fields",
    "fuzziness": "AUTO",
}
```

**5c. Return Promotion Fields:**

```python
return [
    {
        "order_id": hit["_source"]["order_id"],
        # ... existing fields ...

        # Add promotion fields
        "promo_code": hit["_source"].get("promo_code"),
        "discount_percent": hit["_source"].get("discount_percent"),
        "order_total_amount_with_discounts": hit["_source"].get("order_total_amount_with_discounts"),

        # ... rest of fields ...
    }
    for hit in hits
]
```

**5d. Restart Agent Service:**

```bash
docker compose restart agents
```

### Architecture: Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. WRITE: Create Promotion & Apply to Order                     │
│    POST /triples/batch → PostgreSQL (validated by ontology)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. CDC: Change Data Capture                                     │
│    PostgreSQL → Materialize (pg_source replicates triples)      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. TRANSFORM: Materialize Views                                 │
│    promotions_flat → promotions_mv                              │
│    orders_flat → orders_with_promotions → orders_with_prom_mv   │
│    (join orders with promotions, compute discounted total)      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. SINK: Materialize → Kafka                                    │
│    CREATE SINK (Avro, Debezium envelope) publishes the orders   │
│    view to the "orders" Kafka topic on Redpanda                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. INDEX: Kafka Connect → OpenSearch                            │
│    OpenSearch sink connector (embedding SMT) writes to the      │
│    "orders" index with promotion fields                         │
│    (promo_code, discount_percent, discounted_total)             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. AGENT TOOLS: Expose to Agents                                │
│    search_orders tool updated to:                               │
│    - Search by promo_code field                                 │
│    - Return promotion fields in results                         │
│    → Agents can now find and display promotion information      │
└─────────────────────────────────────────────────────────────────┘
```

## Using the Ontology to Create Business Objects

The ontology allows you to **automatically discover** how to create entities.

### Query the Ontology

```bash
# Get all properties for the Order class
GET /ontology/class/Order/properties

# Response shows required fields and data types
[
  {"prop_name": "order_number", "range_kind": "string", "is_required": true},
  {"prop_name": "order_status", "range_kind": "string", "is_required": true},
  {"prop_name": "placed_by", "range_kind": "entity_ref", "range_class": "Customer", "is_required": true},
  // ... more properties
]
```

### Generate Forms Dynamically

The Admin UI uses the ontology to build forms:

```typescript
// Fetch properties for a class
const properties = await api.getClassProperties('Order');

// Generate form fields dynamically
properties.forEach(prop => {
  if (prop.range_kind === 'entity_ref') {
    renderEntityRefDropdown(prop.prop_name, prop.range_class);
  } else if (prop.range_kind === 'bool') {
    renderCheckbox(prop.prop_name);
  } else if (prop.range_kind === 'timestamp') {
    renderDateTimePicker(prop.prop_name);
  } else {
    renderTextInput(prop.prop_name, prop.range_kind);
  }
});
```

### Validate Before Submitting

```bash
# Validate a triple before creating it
POST /triples/validate
{
  "subject_id": "order:FM-NEW",
  "predicate": "order_status",
  "object_value": "CREATED",
  "object_type": "string"
}

# Response:
{
  "is_valid": true,
  "errors": []
}
```

## Common Patterns

### Pattern 1: Time-Sensitive Data

Use `mz_now()` in WHERE clauses for time-based filtering:

```sql
-- Materialized view of currently valid promotions
CREATE MATERIALIZED VIEW active_promotions_mv IN CLUSTER compute AS
SELECT
    promo_id,
    promo_code,
    discount_percent,
    valid_from,
    valid_until
FROM promotions_flat
WHERE is_active = TRUE
  AND mz_now() >= valid_from
  AND mz_now() <= valid_until;

-- Index for fast queries
CREATE INDEX active_promotions_idx IN CLUSTER serving ON active_promotions_mv (promo_id);
```

**Important**: `mz_now()` can **only** appear in `WHERE` or `HAVING` clauses, not in SELECT/CASE expressions.

### Pattern 2: Aggregations

```sql
CREATE MATERIALIZED VIEW store_metrics_mv IN CLUSTER compute AS
SELECT
    s.store_id,
    s.store_name,
    COUNT(DISTINCT o.order_id) AS total_orders,
    COUNT(DISTINCT CASE WHEN o.order_status = 'DELIVERED' THEN o.order_id END) AS delivered_orders,
    SUM(i.stock_level) AS total_inventory_units,
    MAX(o.effective_updated_at) AS last_order_update
FROM stores_flat s
LEFT JOIN orders_flat_mv o ON o.store_id = s.store_id
LEFT JOIN store_inventory_mv i ON i.store_id = s.store_id
GROUP BY s.store_id, s.store_name;
```

### Pattern 3: Graph Traversal

```sql
CREATE MATERIALIZED VIEW orders_with_lines_mv IN CLUSTER compute AS
SELECT
    o.order_id,
    o.order_number,
    o.order_status,
    -- Aggregate line items as JSON
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'line_id', ol.line_id,
                'product_id', ol.product_id,
                'product_name', p.product_name,
                'quantity', ol.quantity,
                'unit_price', ol.unit_price,
                'line_amount', ol.line_amount
            ) ORDER BY ol.line_sequence
        ) FILTER (WHERE ol.line_id IS NOT NULL),
        '[]'::jsonb
    ) AS line_items
FROM orders_flat_mv o
LEFT JOIN order_lines_flat ol ON ol.order_id = o.order_id
LEFT JOIN products_flat p ON p.product_id = ol.product_id
GROUP BY o.order_id, o.order_number, o.order_status;
```

## Summary: The Complete Workflow

1. **Define Ontology** (Classes + Properties)
   - Choose unique prefix
   - Define properties with domain/range constraints
   - Mark required fields

2. **Write Governed Triples**
   - All writes validated against ontology
   - Subject prefix must match class
   - Predicates must be defined properties
   - Data types must match range

3. **Create Views in Materialize**
   - **Regular views**: Flatten triples into entity shapes (intermediate)
   - **Regular views**: Define enrichment logic (joins, computed columns)
   - **Materialized views IN CLUSTER compute**: `SELECT * FROM regular_view` (no duplication!)
   - **Indexes IN CLUSTER serving**: Make materialized views queryable

4. **Expose via API**
   - Query materialized views for fast reads
   - Use ontology to generate forms
   - Validate triples before writes

5. **Real-Time Sync**
   - CDC streams changes to Materialize automatically
   - Zero syncs Materialize views to UI clients
   - OpenSearch indexes maintain search capability

This pattern ensures:

- ✅ Data integrity through ontology validation
- ✅ Query performance through Materialize indexes
- ✅ Real-time updates through CDC, Zero SUBSCRIBE (UI), and the Kafka sink → Kafka Connect → OpenSearch pipeline (search)
- ✅ Semantic relationships preserved in the graph
- ✅ Flexibility to add new entity types without breaking existing code

## See Also

- [Architecture Guide](ARCHITECTURE.md) - CQRS, Materialize, and real-time data flow
- [API Reference](API_REFERENCE.md) - Complete endpoint documentation
- [Dynamic Pricing Guide](DYNAMIC_PRICING.md) - Real-time pricing implementation example
