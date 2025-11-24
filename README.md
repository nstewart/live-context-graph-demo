# FreshMart Digital Twin Agent Starter

A forkable, batteries-included repository demonstrating how to build a **digital twin** of FreshMart's same-day grocery delivery operations using:

- **PostgreSQL** as a triple store with ontology validation
- **Materialize** for real-time materialized views with admin console
- **Zero WebSocket Server** for real-time UI updates via Materialize SUBSCRIBE
- **OpenSearch** for full-text search and discovery
- **LangGraph Agents** with tools for AI-powered operations assistance
- **React Admin UI** with real-time updates for managing operations

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
- Sync orders to OpenSearch

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
                                     │  • Differential updates              │
                                     │  • Bulk upsert/delete                │
                                     │  • < 2s latency                      │
                                     └────────────┬────────────────────────┘
                                                  │ Bulk index
                                                  ▼
                    ┌─────────────────────────────────────┐
                    │      OpenSearch                     │
           ┌───────▶│       Port: 9200                    │
           │        │  • orders index (real-time)         │
           │        │  • Full-text search                 │
           │        └─────────────────────────────────────┘
           │
┌──────────┴───────────────┐
│    LangGraph Agents       │
│      Port: 8081           │
│  • search_orders  ────────┘ (search OpenSearch)
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

The search-sync worker uses **Materialize SUBSCRIBE streaming** to maintain real-time synchronization between PostgreSQL (source of truth) and OpenSearch (search index). This replaces the previous inefficient polling mechanism.

**Startup Process:**
1. **Initial Hydration**: On startup, search-sync queries all existing orders from Materialize and bulk loads them into OpenSearch
2. **Real-Time Streaming**: After hydration, SUBSCRIBE takes over for incremental updates
3. **Result**: OpenSearch starts fully synced and stays up-to-date with < 2 second latency

**Architecture Pattern**:
```
PostgreSQL → Materialize CDC → SUBSCRIBE Stream → Search Sync Worker → OpenSearch
   (write)      (real-time)      (differential)      (bulk ops)          (search)
```

**How SUBSCRIBE Streaming Works**:

1. **Connection**: Worker establishes a persistent SUBSCRIBE connection to `orders_search_source_mv`
2. **Snapshot Handling**: Initial snapshot is discarded (upserts are idempotent, index already populated)
3. **Differential Updates**: Materialize streams inserts (`mz_diff=+1`) and deletes (`mz_diff=-1`)
4. **Timestamp Batching**: Events accumulate until timestamp advances, then flush in bulk
5. **Event Consolidation**: DELETE + INSERT at same timestamp → consolidated into UPDATE operation
6. **Bulk Operations**: Worker performs bulk upsert/delete operations to OpenSearch
7. **Progress Tracking**: `PROGRESS` option ensures regular timestamp updates even with no data changes

**Event Consolidation Pattern** (Critical Fix):

Materialize emits UPDATE operations as DELETE + INSERT pairs at the **same timestamp**. To prevent spurious deletes in downstream systems (Zero cache, OpenSearch), both implementations check if timestamp **increased** (`>` comparison) **BEFORE** adding events to the pending batch. This ensures all events at timestamp X are consolidated before broadcasting.

**Implementation Details**:
- TypeScript: `zero-server/src/materialize-backend.ts:147-161`
- Python: `search-sync/src/mz_client_subscribe.py:334-350`
- Tests: `search-sync/tests/test_subscribe_consolidation.py`

**Performance Improvements**:
- **Latency**: Reduced from 20+ seconds (polling every 5s) to < 2 seconds end-to-end
- **Resource Usage**: 50% reduction in CPU/memory vs polling loops
- **Consistency**: Guaranteed eventual consistency via Materialize's differential dataflow
- **Scalability**: Single worker handles 10,000+ events/second with sub-second latency

**Key Features**:
- **Automatic Recovery**: Exponential backoff reconnection (1s → 30s max)
- **Backpressure Handling**: Pauses streaming when buffer exceeds 5000 events
- **Idempotent Operations**: Safe to replay events, no duplicate index entries
- **Structured Logging**: JSON logs for monitoring and debugging

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL - primary triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **zero-server** | 8090 | WebSocket server for real-time UI updates |
| **opensearch** | 9200 | Search engine for orders |
| **api** | 8080 | FastAPI backend |
| **search-sync** | - | SUBSCRIBE streaming worker for OpenSearch sync (< 2s latency) |
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

The LangGraph-powered ops assistant can:
- Search for orders by customer name, address, or order number
- Fetch detailed order context
- Update order status
- Query the ontology

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
# Option 1: Using make (recommended - handles network and Materialize init)
make up-agent

# Option 2: Using docker-compose directly
docker network create freshmart-network  # if not already created
docker-compose --profile agent up -d
./db/materialize/init.sh  # if not already initialized

# Check agent configuration
docker-compose exec agents python -m src.main check
```

### Interactive Mode

```bash
# Start interactive chat
docker-compose exec -it agents python -m src.main chat

# Example queries:
> Show all OUT_FOR_DELIVERY orders
> Find orders for customer Alex Thompson
> Mark order FM-1001 as DELIVERED
> What's the status of order FM-1002?
```

### Single Command

```bash
docker-compose exec agents python -m src.main chat "Show all orders at BK-01 that are out for delivery"
```

### HTTP API

The agent also exposes an HTTP API on port 8081:

```bash
# Health check
curl http://localhost:8081/health

# Chat with the agent
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show all OUT_FOR_DELIVERY orders"}'
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
# "Broadcasting N changes for orders_search_source_mv"

# View zero-server logs for SUBSCRIBE activity
docker-compose logs -f zero-server | grep -E "Starting SUBSCRIBE|Broadcasting"

# Expected healthy output:
# "[orders_flat_mv] Starting SUBSCRIBE (attempt 1)..."
# "[orders_flat_mv] Connected, setting up SUBSCRIBE stream..."
# "[orders_flat_mv] Broadcasting N changes"
```

#### Verify Sync Latency

```bash
# Create a test order
curl -X POST http://localhost:8080/freshmart/orders ...

# Immediately search for it (should appear within 2 seconds)
curl 'http://localhost:9200/orders/_search?q=order_number:FM-1234'

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
MZ_COUNT=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_search_source_mv;")
OS_COUNT=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
echo "Materialize: $MZ_COUNT, OpenSearch: $OS_COUNT"

# If drift detected, trigger manual resync (see operations runbook)
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
├── search-sync/               # OpenSearch sync worker
│   └── src/
│       ├── mz_client.py       # Materialize queries
│       ├── opensearch_client.py
│       └── orders_sync.py     # Sync logic
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
