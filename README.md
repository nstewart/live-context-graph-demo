# FreshMart Digital Twin Agent Starter

A forkable, batteries-included repository demonstrating how to build a **digital twin** of FreshMart's same-day grocery delivery operations using:

- **PostgreSQL** as a triple store with ontology validation
- **Materialize** for real-time materialized views with admin console
- **Zero WebSocket Server** for real-time UI updates via Materialize SUBSCRIBE
- **OpenSearch** for full-text search and discovery (orders + inventory indexes)
- **LangGraph Agents** with tools for AI-powered operations (search, create customers/orders, update status)
- **React Admin UI** with real-time updates for managing operations

## Architecture Pattern: CQRS

This system implements **CQRS (Command Query Responsibility Segregation)** to separate write and read concerns:

**Commands (Writes)**:
- All modifications flow through the **PostgreSQL triple store** as RDF-style subject-predicate-object statements
- Writes are validated against the **ontology schema** (classes, properties, ranges, domains)
- This ensures data integrity and semantic consistency at write time

**Queries (Reads)**:
- Read operations use **Materialize materialized views** that are pre-computed, denormalized, and indexed
- Views are maintained in real-time via **Change Data Capture (CDC)** from PostgreSQL
- Optimized for fast queries without impacting write performance

**Benefits**:
- **Write model**: Enforces schema through ontology, maintains graph relationships
- **Read model**: Optimized for specific query patterns (orders, inventory, customer lookups)
- **Real-time consistency**: CDC ensures views reflect writes within milliseconds
- **Scalability**: Independent scaling of write (PostgreSQL) and read (Materialize) workloads

## Adding Ontological Elements: A Complete Guide

This guide explains how to extend the FreshMart ontology with new entity types and create corresponding Materialize views to support different use cases.

### Core Concepts You Need to Know

#### 1. **The Triple Store Foundation**

All data is stored as subject-predicate-object triples:

```
subject_id: "customer:123"
predicate: "customer_name"
object_value: "Alex Thompson"
object_type: "string"
```

The triple store is your **governed source of truth** - all writes flow through it with ontology validation.

#### 2. **Ontology = Your Schema**

The ontology defines:
- **Classes**: Entity types (Customer, Order, Store) with a unique prefix
- **Properties**: Allowed predicates with domain (which class) and range (data type or target class)
- **Validation Rules**: Domain constraints, range constraints, required fields

#### 3. **CQRS Pattern**

- **Writes**: Triple store (PostgreSQL) → validated, governed, normalized
- **Reads**: Materialized views (Materialize) → denormalized, indexed, optimized

#### 4. **Materialize Three-Tier Architecture**

```
Ingest Cluster  → CDC from PostgreSQL (pg_source)
Compute Cluster → Materialized views (transform triples into entities)
Serving Cluster → Indexes (fast lookups for queries)
```

### When to Materialize Views in Materialize

Following the **Materialize MCP policy**, here's when to create different view types:

#### **Base Entity Views (Regular Views)**

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

#### **Materialized Views (IN CLUSTER compute)**

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

#### **Indexes (IN CLUSTER serving ON materialized views)**

**Always create indexes** on materialized views when:
- The view is queried by applications/APIs
- You need low-latency lookups
- The view powers a user-facing feature

```sql
-- Example: Make orders queryable with low latency
CREATE INDEX orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);
```

### Step-by-Step: Adding a New Entity Type

Let's walk through adding a new **"Promotion"** entity to support marketing campaigns.

#### Step 1: Define the Ontology

**1a. Create the Class**

Choose a unique prefix and create the class:

```sql
-- Via SQL
INSERT INTO ontology_classes (class_name, prefix, description)
VALUES ('Promotion', 'promo', 'A marketing promotion or discount campaign');

-- Or via API
POST /ontology/classes
{
  "class_name": "Promotion",
  "prefix": "promo",
  "description": "A marketing promotion or discount campaign"
}
```

**1b. Define Properties**

Think about what attributes promotions need:

```sql
-- Promotion name (required string)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'promo_code', id, 'string', TRUE, 'Unique promotion code (e.g., SUMMER25)'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Discount percentage (required float)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'discount_percent', id, 'float', TRUE, 'Discount percentage (0.0 to 100.0)'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Valid dates (required timestamps)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'valid_from', id, 'timestamp', TRUE, 'Promotion start date'
FROM ontology_classes WHERE class_name = 'Promotion';

INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'valid_until', id, 'timestamp', TRUE, 'Promotion end date'
FROM ontology_classes WHERE class_name = 'Promotion';

-- Applicable store (optional entity reference)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_required, description)
SELECT 'promo_store', p.id, 'entity_ref', s.id, FALSE, 'Store where promotion is valid (NULL = all stores)'
FROM ontology_classes p, ontology_classes s
WHERE p.class_name = 'Promotion' AND s.class_name = 'Store';

-- Active status (required boolean)
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, is_required, description)
SELECT 'is_active', id, 'bool', TRUE, 'Whether promotion is currently active'
FROM ontology_classes WHERE class_name = 'Promotion';
```

**1c. Extend Existing Classes (if needed)**

If orders can use promotions, add a relationship:

```sql
-- Add promo_applied property to Order class
INSERT INTO ontology_properties (prop_name, domain_class_id, range_kind, range_class_id, is_required, description)
SELECT 'promo_applied', o.id, 'entity_ref', p.id, FALSE, 'Promotion code applied to this order'
FROM ontology_classes o, ontology_classes p
WHERE o.class_name = 'Order' AND p.class_name = 'Promotion';
```

#### Step 2: Write Triples

Now you can create promotion entities:

```bash
# Via API
POST /triples/batch
[
  {"subject_id": "promo:SUMMER25", "predicate": "promo_code", "object_value": "SUMMER25", "object_type": "string"},
  {"subject_id": "promo:SUMMER25", "predicate": "discount_percent", "object_value": "15.0", "object_type": "float"},
  {"subject_id": "promo:SUMMER25", "predicate": "valid_from", "object_value": "2025-06-01T00:00:00Z", "object_type": "timestamp"},
  {"subject_id": "promo:SUMMER25", "predicate": "valid_until", "object_value": "2025-08-31T23:59:59Z", "object_type": "timestamp"},
  {"subject_id": "promo:SUMMER25", "predicate": "promo_store", "object_value": "store:BK-01", "object_type": "entity_ref"},
  {"subject_id": "promo:SUMMER25", "predicate": "is_active", "object_value": "true", "object_type": "bool"}
]

# Apply promotion to an order
POST /triples
{
  "subject_id": "order:FM-1001",
  "predicate": "promo_applied",
  "object_value": "promo:SUMMER25",
  "object_type": "entity_ref"
}
```

The ontology validator will ensure:
- ✅ Subject prefix `promo:` matches the Promotion class
- ✅ All predicates are defined for the Promotion class
- ✅ Data types match (string, float, timestamp, bool, entity_ref)
- ✅ Entity references point to valid classes (Store)
- ✅ Required fields are present

#### Step 3: Create Materialize Views

**3a. Create Base View (Regular View)**

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

**3b. Create Enriched View with Store Details**

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
    -- Computed: Is promotion currently valid?
    CASE
        WHEN p.is_active
             AND mz_now() >= p.valid_from
             AND mz_now() <= p.valid_until
        THEN TRUE
        ELSE FALSE
    END AS is_currently_valid,
    p.effective_updated_at
FROM promotions_flat p
LEFT JOIN stores_flat s ON s.store_id = p.store_id;

-- Materialize the enriched view (no duplication!)
CREATE MATERIALIZED VIEW promotions_mv IN CLUSTER compute AS
SELECT * FROM promotions_enriched;
```

**3c. Create Index (IN CLUSTER serving)**

Make it queryable with low latency:

```sql
CREATE INDEX promotions_idx IN CLUSTER serving ON promotions_mv (promo_id);
```

**3d. Enrich Existing Views (Optional)**

If orders reference promotions, enrich the orders view:

```sql
-- Drop and recreate with promotion enrichment
DROP MATERIALIZED VIEW orders_search_source_mv CASCADE;

CREATE MATERIALIZED VIEW orders_search_source_mv IN CLUSTER compute AS
SELECT
    o.order_id,
    o.order_number,
    o.order_status,
    o.order_total_amount,
    c.customer_name,
    s.store_name,
    -- Promotion enrichment
    promo.promo_id,
    promo.promo_code,
    promo.discount_percent,
    GREATEST(o.effective_updated_at, promo.effective_updated_at) AS effective_updated_at
FROM orders_flat_mv o
LEFT JOIN customers_flat c ON c.customer_id = o.customer_id
LEFT JOIN stores_flat s ON s.store_id = o.store_id
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

-- Recreate index
CREATE INDEX orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);
```

#### Step 4: Add API Endpoints

Create service methods to query promotions:

```python
# api/src/freshmart/service.py

async def list_promotions(
    store_id: Optional[str] = None,
    active_only: bool = False,
    valid_now: bool = False
) -> List[dict]:
    """List promotions with optional filters."""
    query = """
        SELECT
            promo_id,
            promo_code,
            discount_percent,
            valid_from,
            valid_until,
            store_id,
            store_name,
            is_active,
            is_currently_valid
        FROM promotions_mv
        WHERE 1=1
    """
    params = {}

    if store_id:
        query += " AND (store_id = %(store_id)s OR store_id IS NULL)"
        params['store_id'] = store_id

    if active_only:
        query += " AND is_active = TRUE"

    if valid_now:
        query += " AND is_currently_valid = TRUE"

    query += " ORDER BY valid_from DESC"

    return await execute_query(query, params, db='materialize')
```

Add the route:

```python
# api/src/routes/freshmart.py

@router.get("/promotions")
async def get_promotions(
    store_id: Optional[str] = Query(None),
    active_only: bool = Query(False),
    valid_now: bool = Query(False)
):
    """List promotions with optional filters."""
    return await freshmart_service.list_promotions(
        store_id=store_id,
        active_only=active_only,
        valid_now=valid_now
    )
```

#### Step 5: Use in Applications

Now you can query promotions:

```bash
# Get all promotions
GET /freshmart/promotions

# Get active promotions for Brooklyn store
GET /freshmart/promotions?store_id=store:BK-01&active_only=true

# Get currently valid promotions (within date range)
GET /freshmart/promotions?valid_now=true
```

The Admin UI can display promotions in real-time using Zero:

```typescript
// web/src/schema.ts - Add to schema
const promotions_mv = table('promotions_mv')
  .columns({
    promo_id: string(),
    promo_code: string(),
    discount_percent: number(),
    valid_from: string(),
    valid_until: string(),
    is_active: boolean(),
    is_currently_valid: boolean(),
    // ... other fields
  })
  .primaryKey('promo_id');

// In a React component
const [activePromos] = useQuery(
  z.query.promotions_mv
    .where("is_active", "=", true)
    .where("is_currently_valid", "=", true)
);
```

### Using the Ontology to Create Business Objects

The ontology allows you to **automatically discover** how to create entities:

#### Query the Ontology

```bash
# Get all properties for the Order class
GET /ontology/class/Order/properties

# Response shows:
[
  {"prop_name": "order_number", "range_kind": "string", "is_required": true},
  {"prop_name": "order_status", "range_kind": "string", "is_required": true},
  {"prop_name": "placed_by", "range_kind": "entity_ref", "range_class": "Customer", "is_required": true},
  {"prop_name": "order_store", "range_kind": "entity_ref", "range_class": "Store", "is_required": true},
  // ... more properties
]
```

#### Generate Forms Dynamically

The Admin UI uses the ontology to build forms:

```typescript
// Fetch properties for a class
const properties = await api.getClassProperties('Order');

// Generate form fields dynamically
properties.forEach(prop => {
  if (prop.range_kind === 'entity_ref') {
    // Render dropdown with entities from range_class
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

#### Validate Before Submitting

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

### Common Patterns

#### Pattern 1: Time-Sensitive Data (Active Promotions, Scheduled Tasks)

Use `mz_now()` for time-based logic:

```sql
CREATE MATERIALIZED VIEW active_promotions_mv IN CLUSTER compute AS
SELECT
    promo_id,
    promo_code,
    discount_percent
FROM promotions_flat
WHERE is_active = TRUE
  AND mz_now() >= valid_from
  AND mz_now() <= valid_until;
```

**Important**: `mz_now()` can only appear in `WHERE` or `HAVING` clauses, never in `SELECT`.

#### Pattern 2: Aggregations (Order Counts, Inventory Summaries)

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

#### Pattern 3: Graph Traversal (Orders → Order Lines → Products)

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
LEFT JOIN (
    SELECT
        subject_id AS line_id,
        MAX(CASE WHEN predicate = 'line_of_order' THEN object_value END) AS order_id,
        MAX(CASE WHEN predicate = 'line_product' THEN object_value END) AS product_id,
        MAX(CASE WHEN predicate = 'quantity' THEN object_value END)::INT AS quantity,
        MAX(CASE WHEN predicate = 'unit_price' THEN object_value END)::DECIMAL(10,2) AS unit_price,
        MAX(CASE WHEN predicate = 'line_amount' THEN object_value END)::DECIMAL(10,2) AS line_amount,
        MAX(CASE WHEN predicate = 'line_sequence' THEN object_value END)::INT AS line_sequence
    FROM triples
    WHERE subject_id LIKE 'orderline:%'
    GROUP BY subject_id
) ol ON ol.order_id = o.order_id
LEFT JOIN products_flat p ON p.product_id = ol.product_id
GROUP BY o.order_id, o.order_number, o.order_status;
```

### Summary: The Complete Workflow

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

   **Tip**: Always define transformation logic in regular views first, then materialize them. This avoids duplication and makes testing easier.

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
- ✅ Real-time updates through CDC and Zero sync
- ✅ Semantic relationships preserved in the graph
- ✅ Flexibility to add new entity types without breaking existing code

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/your-org/freshmart-digital-twin-agent-starter.git
cd freshmart-digital-twin-agent-starter

# 2. Configure environment
cp .env.example .env
# Edit .env to add your LLM API keys if using the agent

# 3. Start all services (with Materialize auto-initialization)
make up

# Or start with agents included
make up-agent

# 4. Access the services
# - Admin UI: http://localhost:5173
# - API Docs: http://localhost:8080/docs
# - Materialize Console: http://localhost:6874
# - OpenSearch: http://localhost:9200
```

The system will automatically:
- Create persistent Docker network
- Run database migrations
- Seed demo data (5 stores, 15 products, 15 customers, 20 orders)
- Initialize Materialize (sources, views, indexes)
- Sync orders and inventory to OpenSearch

**Note:** `zero-server` and `search-sync` start immediately and automatically connect to Materialize when it's ready. You may see retry messages in the logs - this is normal during initialization. Services will be fully operational within 30 seconds.

For load testing with larger datasets (~700K triples), see [Load Test Data Generation](#load-test-data-generation).

### Using Docker Compose Directly

If you prefer to use `docker-compose` directly instead of `make`:

```bash
# Create persistent network
docker network create freshmart-network

# Start services
docker-compose up -d
# or with agents
docker-compose --profile agent up -d

# Initialize Materialize manually
./db/materialize/init.sh
```

You can verify the setup by visiting the Materialize Console at http://localhost:6874 and checking that sources and views exist.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Admin UI (React)                                    │
│                      Port: 5173                                          │
│  • Real-time updates via WebSocket                                       │
│  • Orders, Couriers, Stores/Inventory dashboards                         │
└──────────────┬──────────────────────────────────┬────────────────────────┘
               │ REST API (writes/reads)          ▲ WebSocket (real-time)
               ▼                                  │
┌──────────────────────────┐         ┌─────────────────────────────────────┐
│  Graph/Ontology API      │         │    Zero WebSocket Server            │
│  (FastAPI) Port: 8080    │         │    Port: 8090                       │
│  • Ontology CRUD         │         │  • SUBSCRIBE to Materialize MVs     │
│  • Triple CRUD           │         │  • Broadcast changes to clients     │
│  • FreshMart endpoints   │         │  • Collections: orders, stores,     │
│  • Query logging         │         │    couriers, inventory              │
└───────┬──────────────────┘         └────────────▲────────────────────────┘
        │ writes                                  │ SUBSCRIBE
        ▼                                         │ (differential updates)
┌──────────────────────────┐         ┌───────────┴─────────────────────────┐
│     PostgreSQL           │         │      Materialize                     │
│     Port: 5432           │────────▶│  Console: 6874 SQL: 6875             │
│  • ontology_classes      │ (CDC)   │  Three-Tier Architecture:            │
│  • ontology_properties   │         │  • ingest: pg_source (CDC)           │
│  • triples               │         │  • compute: MVs (aggregation)        │
└──────────────────────────┘         │  • serving: indexes (queries)        │
                                     │  SUBSCRIBE: differential updates     │
                                     └────────────┬────────────────────────┘
                                                  │ SUBSCRIBE
                                                  │ (real-time streaming)
                                     ┌────────────▼────────────────────────┐
                                     │    Search Sync Worker                │
                                     │  SUBSCRIBE streaming                 │
                                     │  • OrdersSyncWorker (orders)         │
                                     │  • InventorySyncWorker (inventory)   │
                                     │  • BaseSubscribeWorker pattern       │
                                     │  • Event consolidation               │
                                     │  • < 2s latency                      │
                                     └────────────┬────────────────────────┘
                                                  │ Bulk index
                                                  ▼
                    ┌─────────────────────────────────────┐
                    │      OpenSearch                     │
           ┌───────▶│       Port: 9200                    │
           │        │  • orders index (real-time)         │
           │        │  • inventory index (real-time)      │
           │        │  • Full-text search                 │
           │        └─────────────────────────────────────┘
           │
┌──────────┴───────────────┐
│    LangGraph Agents       │
│      Port: 8081           │
│  • search_orders  ────────┘ (search orders index)
│  • search_inventory ─────┘ (search inventory index)
│  • fetch_order_context ─────▶ Graph API (read triples)
│  • write_triples ───────────▶ Graph API (write triples → PostgreSQL)
└──────────────────────────┘
```

### Real-Time Data Flow

1. **Writes**: All data modifications go through the FastAPI backend → PostgreSQL
2. **CDC**: PostgreSQL changes stream to Materialize via Change Data Capture
3. **Compute**: Materialize maintains materialized views with pre-aggregated data
4. **SUBSCRIBE**: Zero server subscribes to Materialize MVs using SUBSCRIBE command
5. **WebSocket**: Zero broadcasts differential updates to connected UI clients
6. **UI Updates**: React components receive real-time updates and re-render automatically

The Zero WebSocket server uses Materialize's `SUBSCRIBE` command with the `PROGRESS` option to receive differential updates (inserts/deletes) as they happen, providing sub-second latency for UI updates.

### Automatic Reconnection & Resilience

Both `zero-server` and `search-sync` services include automatic retry and reconnection logic:

**Connection Retry:**
- Services start even if Materialize isn't ready yet
- Automatically retry connection every 30 seconds until successful
- No manual intervention needed when Materialize is initializing

**Stream Reconnection:**
- If a SUBSCRIBE stream ends or errors, automatically reconnect
- Handles network interruptions and Materialize restarts gracefully
- Each view maintains its own reconnection loop independently

**What this means:**
- Start services in any order - they'll connect when ready
- If Materialize restarts, services automatically reconnect
- No need to manually restart `zero-server` or `search-sync`
- Real-time updates continue flowing even after connection issues

**Configuration:**
- `zero-server`: Fixed 30-second retry delay per subscription
- `search-sync`: Exponential backoff (1s → 2s → 4s → 8s → 16s → 30s max)
  - Configurable via `RETRY_INITIAL_DELAY`, `RETRY_MAX_DELAY`, `RETRY_BACKOFF_MULTIPLIER`

## Graph/Ontology API

The Graph API (FastAPI, Port 8080) is the primary interface for interacting with the FreshMart digital twin knowledge graph. It provides three main categories of endpoints:

### 1. Ontology Management (`/ontology`)

Define and manage the schema (classes and properties) for the knowledge graph:

**Classes:**
- `GET /ontology/classes` - List all entity classes
- `GET /ontology/classes/{id}` - Get specific class
- `POST /ontology/classes` - Create new class (e.g., Order, Customer, Store)
- `PATCH /ontology/classes/{id}` - Update class metadata
- `DELETE /ontology/classes/{id}` - Delete class
- `GET /ontology/class/{name}/properties` - Get all properties for a class

**Properties:**
- `GET /ontology/properties` - List all properties (optionally filter by domain class)
- `GET /ontology/properties/{id}` - Get specific property
- `POST /ontology/properties` - Create new property (e.g., order_status, customer_name)
- `PATCH /ontology/properties/{id}` - Update property metadata
- `DELETE /ontology/properties/{id}` - Delete property

**Schema:**
- `GET /ontology/schema` - Get complete ontology (all classes and properties)

### 2. Triple Store CRUD (`/triples`)

Manage knowledge graph data as subject-predicate-object triples:

**Triple Operations:**
- `GET /triples` - List triples (filter by subject, predicate, object, type)
  - Query params: `subject_id`, `predicate`, `object_value`, `object_type`, `limit`, `offset`
- `GET /triples/{id}` - Get specific triple by ID
- `POST /triples` - Create new triple (with optional ontology validation)
  - Query param: `validate=true` (default) validates against ontology
- `POST /triples/batch` - Bulk create triples (atomic operation)
- `PATCH /triples/{id}` - Update triple's object value
- `DELETE /triples/{id}` - Delete triple

**Subject Operations:**
- `GET /triples/subjects/list` - List distinct subjects (filter by class/prefix)
- `GET /triples/subjects/counts` - Get entity counts by type
- `GET /triples/subjects/{subject_id}` - Get ALL triples for an entity
- `DELETE /triples/subjects/{subject_id}` - Delete ALL triples for an entity

**Validation:**
- `POST /triples/validate` - Validate triple without creating it

**Example Triple:**
```json
{
  "subject_id": "order:FM-1001",
  "predicate": "order_status",
  "object_value": "OUT_FOR_DELIVERY",
  "object_type": "string"
}
```

### 3. FreshMart Operations (`/freshmart`)

Query pre-computed, denormalized views (powered by Materialize):

**Orders:**
- `GET /freshmart/orders` - List orders with filters
  - Filters: `status`, `store_id`, `customer_id`, `window_start_before`, `window_end_after`
- `GET /freshmart/orders/{order_id}` - Get enriched order details

**Stores & Inventory:**
- `GET /freshmart/stores` - List all stores
- `GET /freshmart/stores/{store_id}` - Get store details
- `GET /freshmart/stores/inventory` - List inventory across stores
  - Filters: `store_id`, `low_stock_only`

**Customers:**
- `GET /freshmart/customers` - List all customers

**Products:**
- `GET /freshmart/products` - List all products

**Couriers:**
- `GET /freshmart/couriers` - List couriers with schedules
  - Filters: `status`, `store_id`
- `GET /freshmart/couriers/{courier_id}` - Get courier with assigned tasks

### 4. Health & Monitoring

- `GET /health` - Basic health check
- `GET /ready` - Readiness check (verifies DB connectivity)
- `GET /stats` - Query execution statistics (PostgreSQL & Materialize)
  - Shows query counts, execution times, slow queries by operation type

### Data Flow & Architecture

**Writes:** All modifications go through the triple store:
1. Client → `POST /triples` (or `/triples/batch`)
2. Triple validated against ontology
3. Saved to PostgreSQL `triples` table
4. CDC streams to Materialize
5. Materialized views update automatically
6. Zero WebSocket broadcasts to UI

**Reads:** Two modes depending on query:
- **Entity Graph Queries:** `GET /triples/subjects/{id}` → PostgreSQL
  - Returns raw triples for an entity (agents use this)
- **Operational Queries:** `GET /freshmart/*` → Materialize
  - Returns denormalized, indexed views (UI uses this)

### Interactive API Docs

Visit **http://localhost:8080/docs** for interactive Swagger UI with:
- All endpoints documented
- Request/response schemas
- "Try it out" functionality
- Example payloads

### Real-Time Search Sync

The search-sync worker uses **Materialize SUBSCRIBE streaming** to maintain real-time synchronization between PostgreSQL (source of truth) and OpenSearch (search indexes). It syncs two materialized views to OpenSearch:

- **orders_search_source_mv** → `orders` index (enriched order data with customer, store, delivery details, and line items)
- **store_inventory_mv** → `inventory` index (denormalized inventory with product and store details, ingredient-aware search)

**Architecture Pattern**:
```
PostgreSQL → Materialize CDC → SUBSCRIBE Stream → Search Sync Worker → OpenSearch
   (write)      (real-time)      (differential)      (bulk ops)       (orders + inventory indexes)
```

**Unified BaseSubscribeWorker Architecture**:

Both workers extend a common `BaseSubscribeWorker` abstract class that provides:
- SUBSCRIBE connection management with exponential backoff retry
- Initial hydration via SELECT query
- Real-time streaming with timestamp-based batching
- Event consolidation for efficient UPDATE handling
- Bulk upsert/delete operations to OpenSearch
- Backpressure monitoring and metrics

Workers customize behavior through 5 abstract methods:
```python
def get_view_name() -> str          # Materialize view to subscribe to
def get_index_name() -> str         # OpenSearch index name
def get_index_mapping() -> dict     # Index mapping configuration
def get_doc_id(data: dict) -> str   # Extract document ID
def transform_event_to_doc(data: dict) -> dict  # Transform to OpenSearch doc
def should_consolidate_events() -> bool  # Enable UPDATE consolidation
```

**How SUBSCRIBE Streaming Works**:

1. **Initial Hydration**: On startup, query all existing records from Materialize and bulk load into OpenSearch
2. **SUBSCRIBE Connection**: Establish persistent connection to materialized view
3. **Snapshot Handling**: Discard initial snapshot (index already hydrated)
4. **Differential Updates**: Stream inserts (`mz_diff=+1`) and deletes (`mz_diff=-1`)
5. **Timestamp Batching**: Accumulate events until timestamp advances
6. **Event Consolidation**: DELETE + INSERT at same timestamp → single UPDATE operation
7. **Bulk Flush**: Execute bulk upsert/delete to OpenSearch
8. **Result**: < 2 second end-to-end latency for all changes

**Event Consolidation Pattern**:

Both workers use consolidation to handle UPDATEs efficiently. When Materialize emits a DELETE + INSERT at the same timestamp (e.g., product price update affecting inventory):

```python
# Without consolidation: 2 operations
DELETE inventory:INV-001  # Remove old record
INSERT inventory:INV-001  # Add new record

# With consolidation: 1 operation
net_diff = -1 + 1 = 0     # DELETE + INSERT = UPDATE
→ UPSERT inventory:INV-001 (only latest data sent to OpenSearch)
```

This prevents spurious deletes and reduces OpenSearch operations by 50% for updates.

**Performance Improvements**:
- **Latency**: < 2 seconds end-to-end (PostgreSQL write → OpenSearch search)
- **Efficiency**: UPDATE = 1 upsert (not delete + upsert)
- **Resource Usage**: 50% reduction in CPU/memory vs polling loops
- **Consistency**: Guaranteed eventual consistency via Materialize's differential dataflow
- **Scalability**: Single worker handles 10,000+ events/second with sub-second latency

**Key Features**:
- **Dual Index Sync**: Orders and inventory indexes maintained independently
- **Automatic Recovery**: Exponential backoff reconnection (1s → 30s max)
- **Backpressure Handling**: Monitors buffer size, warns when exceeds 5000 events
- **Idempotent Operations**: Safe to replay events, no duplicate index entries
- **Structured Logging**: JSON logs with operation metrics for monitoring

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL - primary triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **zero-server** | 8090 | WebSocket server for real-time UI updates |
| **opensearch** | 9200 | Search engine for orders |
| **api** | 8080 | FastAPI backend |
| **search-sync** | - | Dual SUBSCRIBE workers (orders + inventory) for OpenSearch sync (< 2s latency) |
| **web** | 5173 | React admin UI with real-time updates |
| **agents** | 8081 | LangGraph agent runner (optional) |

## Data Model

### Ontology Classes

The FreshMart ontology defines these entity types:

| Class | Prefix | Description |
|-------|--------|-------------|
| Customer | `customer` | People who place orders |
| Store | `store` | FreshMart store locations |
| Product | `product` | Items for sale |
| InventoryItem | `inventory` | Store-product stock records |
| Order | `order` | Customer orders |
| OrderLine | `order_line` | Line items within orders |
| Courier | `courier` | Delivery personnel |
| DeliveryTask | `task` | Tasks assigned to couriers |

### Subject ID Format

All entities use the format `prefix:id`:
- `customer:123`
- `order:FM-1001`
- `store:BK-01`
- `courier:C01`

### Order Statuses

- `CREATED` - New order placed
- `PICKING` - Items being picked in store
- `OUT_FOR_DELIVERY` - Dispatched with courier
- `DELIVERED` - Successfully delivered
- `CANCELLED` - Order cancelled

## API Endpoints

### Ontology Management

```bash
# List classes
GET /ontology/classes

# Create class
POST /ontology/classes
{"class_name": "Zone", "prefix": "zone", "description": "Delivery zone"}

# List properties
GET /ontology/properties

# Get properties for a class
GET /ontology/class/Order/properties

# Create property
POST /ontology/properties
{
  "prop_name": "zone_name",
  "domain_class_id": 9,
  "range_kind": "string",
  "is_required": true,
  "description": "Zone name"
}

# Update property
PATCH /ontology/properties/{id}
{"description": "Updated description"}

# Delete property
DELETE /ontology/properties/{id}
```

### Triple Store

```bash
# Create triple (with validation)
POST /triples
{
  "subject_id": "order:FM-1001",
  "predicate": "order_status",
  "object_value": "DELIVERED",
  "object_type": "string"
}

# Create multiple triples
POST /triples/batch
[
  {"subject_id": "order:FM-1001", "predicate": "order_status", "object_value": "CREATED", "object_type": "string"},
  {"subject_id": "order:FM-1001", "predicate": "order_store", "object_value": "store:BK-01", "object_type": "entity_ref"}
]

# Update triple value
PATCH /triples/{id}
{"object_value": "DELIVERED"}

# Delete triple
DELETE /triples/{id}

# Get subject with all triples
GET /triples/subjects/order:FM-1001

# List subjects by class
GET /triples/subjects/list?class_name=Order

# Delete all triples for a subject
DELETE /triples/subjects/order:FM-1001
```

### FreshMart Operations

```bash
# List orders with filters
GET /freshmart/orders?status=OUT_FOR_DELIVERY

# Get order details
GET /freshmart/orders/order:FM-1001

# List stores (includes inventory items)
GET /freshmart/stores

# Get store with inventory
GET /freshmart/stores/store:BK-01

# List inventory (with optional filters)
GET /freshmart/stores/inventory?store_id=store:BK-01&low_stock_only=true

# List customers
GET /freshmart/customers

# List products
GET /freshmart/products

# List couriers
GET /freshmart/couriers?status=AVAILABLE
```

### Health & Stats

```bash
# Health check
GET /health

# Readiness check (verifies DB connectivity)
GET /ready

# Query statistics (execution times, slow queries, by operation)
GET /stats
```

## Using the Agent

The LangGraph-powered ops assistant provides AI-powered operations support with these capabilities:

**Order Management:**
- **Search orders** by customer name, address, order number, or status (searches OpenSearch `orders` index)
- **Fetch order details** with full context including line items, customer info, delivery tasks
- **Update order status** (CREATED → PICKING → OUT_FOR_DELIVERY → DELIVERED)

**Inventory & Product Discovery:**
- **Search inventory** by product name, category, store, or availability (searches OpenSearch `inventory` index)
- Find products across stores with real-time stock levels
- Ingredient-aware search with synonyms (e.g., "milk" finds whole milk, 2% milk, skim milk)

**Customer & Order Creation:**
- **Create new customers** with name, email, address, and phone
- **Create complete orders** with customer selection, store selection, and multiple line items
- Automatically validates product availability and inventory at selected store

**Knowledge Graph Operations:**
- **Query the ontology** to understand entity types and properties
- **Write triples** directly to the knowledge graph for custom updates
- Read any entity's full context from the triple store

**Conversational Memory:**
- **Remember conversation context** across multiple messages using PostgreSQL-backed checkpointing
- Maintains session state for natural follow-up questions
- References previous searches and entities mentioned in conversation

### Prerequisites

The agent requires an LLM API key. Add one to your `.env` file:

```bash
# Option 1: Anthropic (recommended)
ANTHROPIC_API_KEY=sk-ant-...

# Option 2: OpenAI
OPENAI_API_KEY=sk-...
```

### Starting the Agent Service

```bash
# Option 1: Using make (recommended - handles network, Materialize, and checkpointer init)
make up-agent

# Option 2: Using docker-compose directly
docker network create freshmart-network  # if not already created
docker-compose --profile agent up -d
./db/materialize/init.sh  # if not already initialized
docker-compose exec agents python -m src.init_checkpointer  # initialize conversation memory

# Check agent configuration
docker-compose exec agents python -m src.main check
```

**Note:** `make up-agent` automatically:
- Starts all services including the agent
- Initializes Materialize sources and views
- Creates PostgreSQL checkpointer tables for conversation memory

### Interactive Mode

```bash
# Start interactive chat (creates a unique session with memory)
docker-compose exec -it agents python -m src.main chat

# Example conversation with memory:

# Search and update existing orders
> Find orders for Lisa
Assistant: I found 2 orders for customers named Lisa...

> Show me her orders that are out for delivery
Assistant: Based on the previous search for Lisa, here are her OUT_FOR_DELIVERY orders...

> Mark order FM-1001 as DELIVERED
Assistant: I'll update order FM-1001 to DELIVERED status...

# Search inventory
> Find stores with milk in stock
Assistant: I found milk available at 5 stores: FreshMart Brooklyn 1 (87 units), FreshMart Manhattan 2 (52 units)...

# Create new customer and order
> Create a new customer named John Smith, email john@example.com
Assistant: I've created customer John Smith with ID customer:12345

> Create an order for John at Brooklyn store with 2 gallons of milk and 1 dozen eggs
Assistant: I've created order FM-1235 for John Smith at FreshMart Brooklyn 1 with 2 items totaling $15.98
```

**Memory Features:**
- Each interactive session maintains a unique `thread_id` displayed on startup
- All messages in the session share conversation history
- The agent remembers context for follow-up questions ("her orders", "that order", "the status now")

### Single Command

```bash
# Single query (creates a one-time thread_id)
docker-compose exec agents python -m src.main chat "Show all orders at BK-01 that are out for delivery"

# Search inventory
docker-compose exec agents python -m src.main chat "Find stores with organic milk in stock"

# Create customer and order
docker-compose exec agents python -m src.main chat "Create a customer named Jane Doe with email jane@example.com"
docker-compose exec agents python -m src.main chat "Create an order for Jane at Manhattan store with milk and eggs"

# Continue a conversation across multiple commands with --thread-id
docker-compose exec agents python -m src.main chat --thread-id my-session "Find orders for Lisa"
docker-compose exec agents python -m src.main chat --thread-id my-session "Show me her orders"
```

### HTTP API

The agent also exposes an HTTP API on port 8081:

```bash
# Health check
curl http://localhost:8081/health

# Search orders
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show all OUT_FOR_DELIVERY orders"}'

# Search inventory
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find stores with organic milk in stock"}'

# Create customer and order
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a customer named John Smith with email john@example.com"}'

curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create an order for John at Brooklyn store with milk and eggs",
    "thread_id": "user-123-session"
  }'

# Conversational context with thread_id
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find orders for Lisa",
    "thread_id": "user-123-session"
  }'

curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me her orders that are out for delivery",
    "thread_id": "user-123-session"
  }'
```

The API response includes the `thread_id` for continuing the conversation:
```json
{
  "response": "I found 2 orders for Lisa...",
  "thread_id": "user-123-session"
}
```

## Operations

### Service Management

Using **make** (recommended):
```bash
# Start all services with auto-initialization
make up

# Start with agents
make up-agent

# Stop all services (network persists)
make down

# View all available commands
make help
```

Using **docker-compose** directly:
```bash
# Restart the API service
docker-compose restart api

# Restart all services
docker-compose restart

# Rebuild and restart API (after code changes)
docker-compose up -d --build api

# Stop all services (network persists)
docker-compose down

# Stop and remove volumes (full reset, network still persists)
docker-compose down -v

# To also remove the persistent network
make clean-network
# or
docker network rm freshmart-network
```

### Viewing Logs

```bash
# View API logs (with query timing)
docker-compose logs -f api

# View last 100 lines of API logs
docker-compose logs --tail=100 api

# View logs for multiple services
docker-compose logs -f api mz

# View Materialize logs
docker-compose logs -f mz

# View all service logs
docker-compose logs -f
```

### Query Logging

All database queries are logged with execution time. The logs show:
- **Database**: `[PostgreSQL]` or `[Materialize]`
- **Operation**: `[SELECT]`, `[INSERT]`, `[UPDATE]`, `[DELETE]`, or `[SET]`
- **Execution time**: in milliseconds
- **Query**: SQL statement (truncated if > 200 chars)
- **Parameters**: query parameters

Example log output:
```
[Materialize] [SET] 1.23ms: SET CLUSTER = serving | params={}
[Materialize] [SELECT] 15.67ms: SELECT order_id, order_number, order_status... | params={'limit': 100, 'offset': 0}
[PostgreSQL] [INSERT] 3.45ms: INSERT INTO triples (subject_id, predicate...) | params={'subject_id': 'order:FM-1001', ...}
[PostgreSQL] [UPDATE] 2.89ms: UPDATE triples SET object_value = ... | params={'id': 123, 'value': 'DELIVERED'}
```

**Slow Query Warnings**: Queries exceeding 100ms are logged as warnings:
```
[Materialize] [SELECT] SLOW QUERY 150.23ms (threshold: 100ms): SELECT...
```

To see query logs in real-time:
```bash
docker-compose logs -f api | grep -E "\[Materialize\]|\[PostgreSQL\]"
```

Filter by operation type:
```bash
# Only show writes (go to PostgreSQL, then CDC to Materialize)
docker-compose logs -f api | grep -E "\[INSERT\]|\[UPDATE\]|\[DELETE\]"

# Only show reads (all from Materialize serving cluster)
docker-compose logs -f api | grep "\[SELECT\]"

# Only show slow queries
docker-compose logs -f api | grep "SLOW QUERY"
```

### Query Statistics API

The `/stats` endpoint provides aggregated query statistics:

```bash
curl http://localhost:8080/stats
```

Response:
```json
{
  "postgresql": {
    "total_queries": 50,
    "total_time_ms": 125.5,
    "avg_time_ms": 2.51,
    "slow_queries": 0,
    "slowest_query_ms": 15.2,
    "slowest_query": "SELECT * FROM...",
    "by_operation": {
      "SELECT": { "count": 30, "total_ms": 75.2, "avg_ms": 2.5 },
      "INSERT": { "count": 20, "total_ms": 50.3, "avg_ms": 2.5 }
    }
  },
  "materialize": {
    "total_queries": 25,
    "total_time_ms": 45.2,
    "avg_time_ms": 1.81,
    "slow_queries": 0,
    "slowest_query_ms": 8.5,
    "slowest_query": "SELECT order_id...",
    "by_operation": {
      "SET": { "count": 5, "total_ms": 3.2, "avg_ms": 0.64 },
      "SELECT": { "count": 20, "total_ms": 42.0, "avg_ms": 2.1 }
    }
  }
}
```

### Materialize Three-Tier Architecture

All UI read queries are routed through Materialize's **serving cluster** for low-latency indexed access:

```
UI → API → Materialize (serving cluster) → Indexed Materialized Views
```

The architecture uses three clusters:
- **ingest**: PostgreSQL source replication via CDC
- **compute**: Materialized view computation (pre-aggregates triples)
- **serving**: Indexes for low-latency queries

#### Materialized Views

All FreshMart endpoints query precomputed, indexed materialized views - no on-the-fly aggregation:

| API Endpoint | Materialized View | Index |
|--------------|-------------------|-------|
| `/freshmart/orders` | `orders_search_source_mv` | `orders_search_source_idx` |
| `/freshmart/stores/inventory` | `store_inventory_mv` | `store_inventory_idx` |
| `/freshmart/couriers` | `courier_schedule_mv` | `courier_schedule_idx` |
| `/freshmart/stores` | `stores_mv` | `stores_idx` |
| `/freshmart/customers` | `customers_mv` | `customers_idx` |
| `/freshmart/products` | `products_mv` | `products_idx` |

The materialized views flatten the triple store into denormalized structures in the **compute cluster**, then indexes in the **serving cluster** provide sub-millisecond lookups.

To verify queries are hitting the serving cluster:
```bash
# Watch query logs - should show [Materialize]
docker-compose logs -f api | grep -E "\[Materialize\]"

# Example output:
# [Materialize] [SET] 0.68ms: SET CLUSTER = serving | params=()
# [Materialize] [SELECT] 4.30ms: SELECT order_id, order_number... | params=(100, 0)
```

### Troubleshooting OpenSearch Sync

#### Check SUBSCRIBE Connection Status

```bash
# View search-sync logs for SUBSCRIBE activity
docker-compose logs -f search-sync | grep "SUBSCRIBE"

# Expected healthy output:
# "Starting SUBSCRIBE for view: orders_search_source_mv"
# "Starting SUBSCRIBE for view: store_inventory_mv"
# "Broadcasting N changes for orders_search_source_mv"
# "Broadcasting N changes for store_inventory_mv"

# View zero-server logs for SUBSCRIBE activity
docker-compose logs -f zero-server | grep -E "Starting SUBSCRIBE|Broadcasting"

# Expected healthy output:
# "[orders_flat_mv] Starting SUBSCRIBE (attempt 1)..."
# "[orders_flat_mv] Connected, setting up SUBSCRIBE stream..."
# "[orders_flat_mv] Broadcasting N changes"
```

#### Verify Sync Latency

```bash
# Test orders sync - Create a test order
curl -X POST http://localhost:8080/freshmart/orders ...

# Search for it (should appear within 2 seconds)
curl 'http://localhost:9200/orders/_search?q=order_number:FM-1234'

# Test inventory sync - Update a product price
curl -X PATCH http://localhost:8080/triples/{triple_id} -d '{"object_value": "9.99"}'

# Search for updated inventory (should appear within 2 seconds)
curl 'http://localhost:9200/inventory/_search?q=product_name:Milk'

# Check timestamp of last sync
docker-compose logs --tail=50 search-sync | grep "Broadcasting"
```

#### Common Issues

**SUBSCRIBE Connection Failures**:
```bash
# Symptom: "Connection refused" or "unknown catalog item 'orders_search_source_mv'"
# These are automatically retried - services will reconnect when Materialize is ready

# Check if Materialize is running
docker-compose ps mz

# Check if views exist (if "unknown catalog item" error)
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -d materialize \
  -c "SET CLUSTER = serving; SHOW MATERIALIZED VIEWS;"

# Should see both: orders_search_source_mv, store_inventory_mv

# If views missing, initialize Materialize
make init-mz

# Watch automatic retry attempts
docker-compose logs -f search-sync | grep "Retrying"
docker-compose logs -f zero-server | grep "Retrying"

# Services will auto-connect within 30 seconds - no restart needed!
```

**High Sync Latency (> 5 seconds)**:
```bash
# Check for backpressure warnings
docker-compose logs search-sync | grep "backpressure"

# Check OpenSearch bulk operation performance
docker-compose logs search-sync | grep "bulk_upsert"

# Verify Materialize view is updating
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;"
```

**OpenSearch Index Drift**:
```bash
# Compare counts between Materialize and OpenSearch

# Orders index
MZ_ORDERS=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;")
OS_ORDERS=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
echo "Orders - Materialize: $MZ_ORDERS, OpenSearch: $OS_ORDERS"

# Inventory index
MZ_INVENTORY=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM store_inventory_mv;")
OS_INVENTORY=$(curl -s 'http://localhost:9200/inventory/_count' | jq '.count')
echo "Inventory - Materialize: $MZ_INVENTORY, OpenSearch: $OS_INVENTORY"

# If drift detected, restart search-sync to re-hydrate
docker-compose restart search-sync
```

**Memory/Buffer Issues**:
```bash
# Check buffer size metrics in logs
docker-compose logs search-sync | grep "buffer"

# If buffer exceeds 5000, backpressure should activate
# Check for memory usage spikes
docker stats search-sync
```

For detailed recovery procedures, see [OpenSearch Sync Operations Runbook](docs/OPENSEARCH_SYNC_RUNBOOK.md).

## Development

### Load Test Data Generation

Generate realistic operational data to demonstrate PostgreSQL vs Materialize performance differences.

```bash
# Install dependencies (if running outside Docker)
pip install -r db/scripts/requirements.txt

# Generate full dataset (~700K triples, ~150MB)
# Represents 6 months of FreshMart operations
./db/scripts/generate_data.sh

# Or with scale factor (0.1 = ~70K triples for quick testing)
./db/scripts/generate_data.sh --scale 0.1

# Preview without inserting
./db/scripts/generate_data.sh --dry-run

# Clear existing data and regenerate
./db/scripts/generate_data.sh --clear
```

**Generated Data (scale=1.0):**

| Entity | Count | Triples |
|--------|-------|---------|
| Stores | 50 | 300 |
| Products | 500 | 2,500 |
| Customers | 5,000 | 20,000 |
| Couriers | 200 | 1,000 |
| Orders | 25,000 | 200,000 |
| Order Lines | 75,000 | 300,000 |
| Delivery Tasks | 23,500 | 125,000 |
| Inventory | 10,000 | 50,000 |
| **Total** | | **~700,000** |

Materialize views update automatically via CDC - no rebuild needed. You can verify data is flowing:
```bash
# Check triple count in Materialize
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_flat_mv;"
```

### Running Tests

```bash
# API unit tests (no database required)
cd api
python -m pytest tests/ -v

# Or run inside container
docker-compose exec api python -m pytest tests/ -v

# Search-sync tests
cd search-sync
python -m pytest tests/ -v

# Web tests
cd web
npm test -- --run

# Agent tests
cd agents
python -m pytest tests/ -v
```

### Integration Tests

The API includes integration tests that verify both PostgreSQL and Materialize read paths work correctly. These tests require running database connections.

```bash
cd api

# Run all integration tests (requires both PG and MZ)
PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DATABASE=freshmart \
MZ_HOST=localhost MZ_PORT=6875 MZ_USER=materialize MZ_PASSWORD=materialize MZ_DATABASE=materialize \
python -m pytest tests/test_freshmart_service_integration.py -v
```

The integration tests include:

| Test Class | Tests | Description |
|------------|-------|-------------|
| `TestPostgreSQLReadPath` | 9 | Verifies FreshMart queries using PostgreSQL views |
| `TestMaterializeReadPath` | 9 | Verifies FreshMart queries using Materialize MVs |
| `TestCrossBackendConsistency` | 6 | Confirms both backends return identical data |
| `TestViewMapping` | 2 | Unit tests for view name mapping |

**Key tests:**
- `test_list_stores_includes_inventory` - Verifies stores include inventory items
- `test_list_products_returns_data` - Verifies products API works
- `test_stores_match_between_backends` - Confirms PG and MZ return same stores
- `test_inventory_match_between_backends` - Confirms PG and MZ return same inventory

Run specific test classes:
```bash
# PostgreSQL only
PG_HOST=localhost ... python -m pytest tests/test_freshmart_service_integration.py::TestPostgreSQLReadPath -v

# Materialize only
MZ_HOST=localhost ... python -m pytest tests/test_freshmart_service_integration.py::TestMaterializeReadPath -v

# Cross-backend consistency
python -m pytest tests/test_freshmart_service_integration.py::TestCrossBackendConsistency -v
```

### Environment Variables

See `.env.example` for all available configuration:

```bash
# Database (use external URL to connect to managed Postgres)
PG_EXTERNAL_URL=postgresql://user:pass@host:5432/db

# Materialize (use external URL for cloud Materialize)
MZ_EXTERNAL_URL=postgresql://user:pass@host:6875/materialize

# LLM API keys for agents
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Feature flags
USE_MATERIALIZE_FOR_READS=true  # Set to false to query PostgreSQL instead of Materialize
```

#### Running Against PostgreSQL

By default, FreshMart read queries (`/freshmart/*` endpoints) use Materialize's indexed materialized views for low-latency access. To query PostgreSQL directly instead:

```bash
# Set in .env or docker-compose.yml
USE_MATERIALIZE_FOR_READS=false
```

This is useful for:
- Development without Materialize
- Debugging query differences
- Environments where Materialize isn't available

### Extending the Ontology

1. Add a new class via the API or seed SQL
2. Add properties for the class
3. Create triples using the new class prefix
4. Update Materialize views if needed for new operational queries

## Project Structure

```
freshmart-digital-twin-agent-starter/
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Common commands
├── .env.example                # Environment template
│
├── db/
│   ├── migrations/             # SQL migrations (run on startup)
│   ├── seed/                   # Demo data (small dataset)
│   ├── materialize/            # Materialize emulator init
│   └── scripts/
│       ├── generate_data.sh    # Load test data generator wrapper
│       ├── generate_load_test_data.py  # Python data generator (~700K triples)
│       └── requirements.txt    # Generator dependencies
│
├── api/                        # FastAPI backend
│   ├── src/
│   │   ├── ontology/          # Ontology CRUD
│   │   ├── triples/           # Triple store + validation
│   │   ├── freshmart/         # FreshMart operational endpoints
│   │   └── routes/            # HTTP routes
│   └── tests/
│       ├── test_freshmart_service_integration.py  # PG/MZ integration tests
│       └── ...                # Unit and API tests
│
├── search-sync/               # OpenSearch sync workers
│   └── src/
│       ├── base_subscribe_worker.py  # Abstract base class (619 lines)
│       ├── orders_sync.py     # Orders sync worker (extends base)
│       ├── inventory_sync.py  # Inventory sync worker (extends base)
│       ├── mz_client_subscribe.py  # Materialize SUBSCRIBE client
│       └── opensearch_client.py    # OpenSearch bulk operations
│
├── zero-server/               # WebSocket server for real-time UI updates
│   └── src/
│       ├── server.ts          # WebSocket server with Zero protocol
│       ├── materialize-backend.ts  # SUBSCRIBE to Materialize MVs
│       └── index.ts           # Entry point
│
├── web/                       # React admin UI with real-time updates
│   └── src/
│       ├── api/               # API client
│       ├── context/           # Zero WebSocket context
│       ├── hooks/             # useZeroQuery for real-time data
│       └── pages/             # UI pages (Orders, Couriers, Stores)
│
├── agents/                    # LangGraph agents
│   └── src/
│       ├── tools/             # Agent tools
│       └── graphs/            # LangGraph definitions
│
└── docs/                      # Documentation
    ├── ARCHITECTURE.md
    ├── ONTOLOGY.md
    ├── DATA_MODEL.md
    ├── SEARCH.md
    └── AGENTS.md
```

## Admin UI Features

The React Admin UI (`web/`) provides full CRUD operations with **real-time updates** for managing FreshMart entities:

### Real-Time Updates

All operational dashboards (Orders, Couriers, Stores/Inventory) feature **live data synchronization**:

- **WebSocket Connection**: Direct connection to Zero server at `ws://localhost:8090`
- **Connection Indicator**: Visual badge showing real-time connection status
- **Instant Updates**: Changes from any source (UI, API, database) appear immediately across all connected clients
- **Differential Updates**: Only changed data is transmitted, minimizing bandwidth
- **Automatic Reconnection**: Handles network interruptions gracefully

### Orders Dashboard
- **Real-time order status updates** - See orders move through workflow stages instantly
- View all orders with status badges and filtering
- Create new orders with dropdown selectors for customers and stores
- Edit existing orders with pre-populated form fields
- Delete orders with confirmation dialog

### Couriers & Schedule
- **Real-time courier availability and task updates**
- View all couriers with their assigned tasks and current status
- Create new couriers with dropdown selector for home store
- Edit courier details including status and vehicle type
- Delete couriers with confirmation dialog

### Stores & Inventory
- **Real-time inventory level updates** - Stock changes appear instantly
- View stores with their current inventory levels (sorted by inventory ID for stability)
- Create/edit stores with zone and capacity settings
- Manage inventory items per store with real-time propagation
- Expandable inventory view with edit capabilities

### Ontology Properties
- View all ontology properties with domain/range information
- Create new properties with dropdowns for:
  - **Domain Class**: Select from existing ontology classes
  - **Range Kind**: string, integer, decimal, boolean, datetime, entity_ref
  - **Range Class**: (for entity_ref) Select target class
- Edit/delete properties with confirmation dialogs

### Triples Browser
- Browse all entities in the knowledge graph with filtering by entity type
- View entity details with all associated triples
- **Create triples** with ontology-powered dropdowns:
  - **Subject ID**: Class prefix dropdown + ID input
  - **Predicate**: Filtered by subject's class from ontology
  - **Value**: Smart input based on range_kind (dropdown for entity_ref/boolean, datetime picker, number input)
- **Edit triples**: Update values with type-appropriate inputs
- **Delete triples**: Individual triples or entire subjects
- Navigate between related entities via entity_ref links

All dropdown data is fetched from Materialize's serving cluster for low-latency access.

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed guidelines.
