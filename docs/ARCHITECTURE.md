# Architecture

This document describes the architecture of the FreshMart Digital Twin system.

## Overview

The system implements a **knowledge graph** architecture for representing FreshMart's same-day delivery operations. It combines:

1. **Triple Store** - Generic subject-predicate-object data model
2. **Ontology Layer** - Schema validation and semantic structure
3. **Materialized Views** - Denormalized operational queries
4. **Search Index** - Full-text search for discovery
5. **Agent Layer** - AI-powered operations assistance

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client Layer                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Admin UI (React)           │  Agent CLI (LangGraph)                        │
│  - Ontology management      │  - Natural language queries                   │
│  - Triple browser           │  - Status updates                             │
│  - Operations dashboards    │  - Tool-based reasoning                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer (FastAPI)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Ontology Service           │  Triple Service          │  FreshMart Service │
│  - Class CRUD               │  - CRUD operations       │  - Order queries   │
│  - Property CRUD            │  - Validation layer      │  - Store queries   │
│  - Schema queries           │  - Batch operations      │  - Courier queries │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
┌───────────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│     PostgreSQL        │ │    Materialize    │ │    OpenSearch     │
│                       │ │    Emulator       │ │                   │
│  Source of Truth      │ │  Operational      │ │  Search Index     │
│  - ontology_classes   │ │  Views            │ │  - orders index   │
│  - ontology_properties│ │  - orders_flat    │ │                   │
│  - triples            │ │  - inventory      │ │                   │
│                       │ │  - couriers       │ │                   │
└───────────────────────┘ └───────────────────┘ └───────────────────┘
```

## Data Flow

### Write Path

1. Client sends triple to API
2. API validates against ontology
3. Triple inserted into PostgreSQL
4. Materialize views auto-refresh via CDC (Change Data Capture)
5. SUBSCRIBE streams differential updates to Zero and Search Sync workers
6. Documents upserted to OpenSearch with event consolidation

### Read Path (Operational)

1. Client requests operational data (e.g., orders)
2. API queries Materialize flattened view
3. Denormalized data returned directly

### Read Path (Search)

1. Client searches for orders
2. Query sent to OpenSearch
3. Matching documents returned with scores

### SUBSCRIBE Event Consolidation

Both Zero WebSocket Server and Search Sync Worker implement a critical event consolidation pattern to handle Materialize UPDATE operations correctly:

**The Challenge**: Materialize emits UPDATEs as DELETE (diff=-1) + INSERT (diff=+1) pairs at the **same timestamp**. Broadcasting these separately causes records to disappear temporarily from Zero cache and OpenSearch.

**The Solution**: Events are accumulated by timestamp and only broadcast when the timestamp **increases** (not just changes). The timestamp check happens **before** adding events to the batch, ensuring all events at timestamp X are consolidated before broadcasting.

**Key Implementation Points**:
- Check: `if (timestamp > lastTimestamp)` not `if (timestamp != lastTimestamp)`
- Order: Check timestamp advancement BEFORE adding event to pending batch
- Result: DELETE + INSERT at same timestamp → consolidated into single UPDATE operation

**Files**:
- `zero-server/src/materialize-backend.ts:147-161` (TypeScript implementation)
- `search-sync/src/mz_client_subscribe.py:334-350` (Python implementation)
- `search-sync/tests/test_subscribe_consolidation.py` (Consolidation tests)

This pattern ensures consistency across all downstream systems and prevents spurious deletes during status updates.

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
- Operations dashboards
- Settings and health display

**Key Design Decisions**:
- TanStack Query for data fetching
- Tailwind CSS for styling
- Component-based architecture
- Real-time updates via polling

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
