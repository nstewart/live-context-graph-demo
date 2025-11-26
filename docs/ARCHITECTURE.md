# Architecture

This document describes the architecture of the FreshMart Digital Twin system.

## Overview

The system implements a **knowledge graph** architecture for representing FreshMart's same-day delivery operations. It combines:

1. **Triple Store** - Generic subject-predicate-object data model (PostgreSQL)
2. **Ontology Layer** - Schema validation and semantic structure
3. **Materialized Views** - Denormalized operational queries (Materialize)
4. **Real-time Sync** - Zero (hosted service at zero.rocicorp.dev) for live client updates
5. **Search Index** - Full-text search for discovery (OpenSearch)
6. **Agent Layer** - AI-powered operations assistance

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Admin UI (React + Zero)    │  Agent CLI (LangGraph)                        │
│  - Ontology management      │  - Natural language queries                   │
│  - Triple browser           │  - Status updates                             │
│  - Operations dashboards    │  - Tool-based reasoning                       │
│  - Real-time WebSocket sync │                                               │
└─────────────────────────────────────────────────────────────────────────────┘
                     │ WebSocket                    │ REST
                     ▼                              ▼
┌─────────────────────────┐   ┌───────────────────────────────────────────────┐
│   Zero (Hosted Service) │   │              API Layer (FastAPI)               │
│   (zero.rocicorp.dev)   │   ├───────────────────────────────────────────────┤
│   - Sync Materialize    │   │  Ontology Service  │  Triple Service          │
│     views to clients    │   │  - Class CRUD      │  - CRUD operations       │
│   - ZQL query filtering │   │  - Property CRUD   │  - Validation layer      │
│   - Differential sync   │   │  - Schema queries  │  - Batch operations      │
└─────────────────────────┘   └───────────────────────────────────────────────┘
           │ Connects to                           │
           ▼                                        ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         Materialize (Streaming SQL)                        │
│  Materialized Views (auto-updated via CDC from PostgreSQL):                │
│  - orders_with_lines_mv    - stores_mv          - courier_schedule_mv     │
│  - orders_search_source_mv - customers_mv       - store_inventory_mv      │
└───────────────────────────────────────────────────────────────────────────┘
           │ CDC (Logical Replication)
           ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL (Source of Truth)                       │
│  - ontology_classes        - triples            - sync_cursors            │
│  - ontology_properties     - order_line_items                             │
└───────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Write Path

1. Client sends triple to API
2. API validates against ontology
3. Triple inserted into PostgreSQL
4. Materialize views auto-refresh via CDC (Change Data Capture)
5. Zero syncs changes to connected clients
6. Documents upserted to OpenSearch with event consolidation

### Read Path (Operational via Zero)

1. Admin UI connects to Zero hosted service (zero.rocicorp.dev)
2. Client subscribes to views with optional ZQL filters (WHERE clauses)
3. Zero syncs data from Materialize views
4. Initial data snapshot sent to client
5. Subsequent changes streamed as differential updates
6. Client state automatically updated in real-time

```typescript
// Example: Filtered real-time subscription
const [orders] = useQuery(
  z.query.orders_with_lines_mv
    .where("order_status", "=", "PICKING")
    .where("store_id", "=", "store:BK-01")
    .orderBy("order_number", "asc")
);
// orders automatically updates when matching data changes
```

### Read Path (Search)

1. Client searches for orders
2. Query sent to OpenSearch
3. Matching documents returned with scores

### SUBSCRIBE Event Consolidation

The Search Sync Worker implements event consolidation to handle Materialize UPDATE operations correctly:

**The Challenge**: Materialize emits UPDATEs as DELETE (diff=-1) + INSERT (diff=+1) pairs at the **same timestamp**. Broadcasting these separately causes records to disappear temporarily from OpenSearch.

**The Solution**: Events are accumulated by timestamp and only broadcast when the timestamp **increases** (not just changes). The timestamp check happens **before** adding events to the batch, ensuring all events at timestamp X are consolidated before broadcasting.

**Key Implementation Points**:
- Check: `if (timestamp > lastTimestamp)` not `if (timestamp != lastTimestamp)`
- Order: Check timestamp advancement BEFORE adding event to pending batch
- Result: DELETE + INSERT at same timestamp → consolidated into single UPDATE operation

**Files**:
- `search-sync/src/mz_client_subscribe.py:334-350` (Python implementation)
- `search-sync/tests/test_subscribe_consolidation.py` (Consolidation tests)

This pattern ensures consistency across downstream systems and prevents spurious deletes during status updates.

## Service Responsibilities

### API Service

**Technology**: FastAPI (Python)

**Responsibilities**:
- RESTful API for all operations
- Ontology schema management
- Triple CRUD with validation
- FreshMart convenience endpoints
- Health/readiness checks

**Key Design Decisions**:
- Hexagonal architecture (ports & adapters)
- Async throughout (asyncpg, httpx)
- Pydantic v2 for validation
- Single write entrypoint for data integrity

### Zero (Hosted Service)

**Technology**: Zero by Rocicorp (hosted at zero.rocicorp.dev)

**Responsibilities**:
- Real-time sync of Materialize views to web clients
- WebSocket connection management
- ZQL query parsing and filtering
- Differential sync (only changed data sent)

**Key Design Decisions**:
- Hosted service eliminates need for local Zero server
- Schema-driven type safety via `web/src/schema.ts`
- Client connects directly to zero.rocicorp.dev

**Files**:
- `web/src/schema.ts` - Zero schema definition (maps to Materialize views)
- `web/src/zero.ts` - Zero client initialization

### Search Sync Worker

**Technology**: Python with asyncio

**Responsibilities**:
- Poll Materialize views for changes
- Transform documents for OpenSearch
- Bulk upsert to search index
- Track sync cursor for incremental updates

**Key Design Decisions**:
- Cursor-based incremental sync
- Batch processing (configurable size)
- Dead letter handling for failures
- Graceful shutdown support

### Admin UI

**Technology**: React with Vite

**Responsibilities**:
- Ontology management interface
- Triple browser and editor
- Operations dashboards (Orders, Stores, Couriers)
- Ontology visualization graph
- Settings and health display

**Key Design Decisions**:
- **Zero (@rocicorp/zero)** for real-time data sync via WebSocket
- ZQL (Zero Query Language) for declarative, filterable queries
- TanStack Query for non-real-time API calls (mutations, ontology CRUD)
- Tailwind CSS for styling
- Component-based architecture

**Zero Integration**:
The Admin UI uses Zero for real-time sync of operational data from Materialize views:

```typescript
// Zero client setup (web/src/zero.ts)
const zero = new Zero({
  userID: 'anon',
  server: 'https://zero.rocicorp.dev',
  schema,
})

// Schema maps to Materialize views (web/src/schema.ts)
const orders_with_lines_mv = table('orders_with_lines_mv')
  .columns({
    order_id: string(),
    order_status: string().optional(),
    // ... embedded line_items as JSON
  })
  .primaryKey('order_id')
```

**ZQL Queries with Filters**:
Zero queries support SQL-compatible filtering that pushes predicates to the server:

```typescript
// Build filtered query inline - state changes trigger re-render
let query = z.query.orders_with_lines_mv;

if (statusFilter) {
  query = query.where("order_status", "=", statusFilter);
}
if (storeFilter) {
  query = query.where("store_id", "=", storeFilter);
}
if (searchQuery) {
  query = query.where("order_number", "ILIKE", `%${searchQuery}%`);
}

const [orders] = useQuery(query.orderBy("order_number", "asc"));
```

Supported ZQL operators: `=`, `!=`, `<`, `>`, `<=`, `>=`, `LIKE`, `ILIKE`, `IN`, `IS`, `IS NOT`

### Agent Service

**Technology**: LangGraph with OpenAI/Anthropic

**Responsibilities**:
- Natural language operations interface
- Tool-based reasoning
- Multi-step task execution
- Context-aware responses

**Key Design Decisions**:
- State machine graph architecture
- Async tool execution
- Iteration limits for safety
- Support for multiple LLM providers

## Database Schema

### Core Tables

```sql
-- Ontology schema
ontology_classes (id, class_name, prefix, description, parent_class_id)
ontology_properties (id, prop_name, domain_class_id, range_kind, range_class_id, ...)

-- Triple store
triples (id, subject_id, predicate, object_value, object_type, timestamps)
```

### Materialize Three-Tier Architecture

Materialize uses a three-tier architecture for optimal resource allocation:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Three-Tier Architecture                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  INGEST CLUSTER (25cc)                                                       │
│  • pg_source - Replicates triples table via PostgreSQL logical replication  │
├─────────────────────────────────────────────────────────────────────────────┤
│  COMPUTE CLUSTER (25cc)                                                      │
│  • Materialized views that persist transformation results:                   │
│    - orders_flat_mv, store_inventory_mv, orders_search_source_mv            │
├─────────────────────────────────────────────────────────────────────────────┤
│  SERVING CLUSTER (25cc)                                                      │
│  • Indexes on materialized views for low-latency queries:                    │
│    - orders_flat_idx, store_inventory_idx, orders_search_source_idx         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Regular Views** (intermediate transformations, no cluster):
```sql
-- Helper views used by materialized views
customers_flat, stores_flat, delivery_tasks_flat
```

**Materialized Views** (IN CLUSTER compute):
```sql
-- Topmost views that persist results for serving
CREATE MATERIALIZED VIEW orders_flat_mv IN CLUSTER compute AS ...
CREATE MATERIALIZED VIEW store_inventory_mv IN CLUSTER compute AS ...
CREATE MATERIALIZED VIEW orders_search_source_mv IN CLUSTER compute AS ...
```

**Indexes** (IN CLUSTER serving ON materialized views):
```sql
-- Indexes make materialized views queryable with low latency
CREATE INDEX orders_flat_idx IN CLUSTER serving ON orders_flat_mv (order_id);
CREATE INDEX store_inventory_idx IN CLUSTER serving ON store_inventory_mv (inventory_id);
CREATE INDEX orders_search_source_idx IN CLUSTER serving ON orders_search_source_mv (order_id);
```

Access the Materialize Console at http://localhost:6874 to monitor clusters, sources, views, and indexes.

## Validation Layer

The triple validator enforces:

1. **Class existence**: Subject prefix maps to ontology class
2. **Property existence**: Predicate defined in ontology
3. **Domain constraint**: Property applies to subject's class
4. **Range constraint**: Object type matches property range
5. **Literal validation**: Type-specific value validation

## Scalability Considerations

### Current Architecture (Development)

- Single PostgreSQL instance with logical replication enabled
- Materialize Emulator with admin console (http://localhost:6874)
- Single-node OpenSearch
- In-process sync worker

### Production Scaling

1. **Database**: Switch to managed PostgreSQL (Neon, RDS, Supabase)
2. **Materialize**: Use cloud Materialize for true streaming
3. **OpenSearch**: Use managed OpenSearch with replication
4. **Sync Worker**: Run as separate deployments with partitioning
5. **API**: Horizontal scaling behind load balancer

## Security Considerations

- API authentication (add JWT/OAuth for production)
- Database connection pooling with SSL
- OpenSearch authentication
- Environment-based secrets management
- CORS configuration for production domains
