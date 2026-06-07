# Operations Guide

Complete guide for managing FreshMart Digital Twin services, monitoring system health, and troubleshooting issues.

## Table of Contents

- [Quick Start](#quick-start)
- [Service Management](#service-management)
- [Viewing Logs](#viewing-logs)
- [Query Logging](#query-logging)
- [Query Statistics](#query-statistics)
- [Materialize Console](#materialize-console)
- [Troubleshooting](#troubleshooting)
- [Environment Variables](#environment-variables)

## Quick Start

### Starting Services

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
- Initialize Materialize (sources, views, indexes, Kafka sinks)
- Provision Redpanda topics, OpenSearch index templates, and Kafka Connect connectors (via `connect-init`)
- Sync orders and inventory to OpenSearch

**Note:** `zero-server` starts immediately and automatically connects to Materialize when it's ready. The search-indexing path (Materialize Kafka sink → Redpanda → Kafka Connect → OpenSearch) comes online once `connect-init` registers the connectors. You may see retry messages in the logs - this is normal during initialization. Services will be fully operational within 30 seconds.

### Using Docker Compose Directly

If you prefer to use `docker compose` directly instead of `make`:

```bash
# Create persistent network
docker network create freshmart-network

# Start services
docker compose up -d
# or with agents
docker compose --profile agent up -d

# Initialize Materialize manually
./db/materialize/init.sh
```

You can verify the setup by visiting the Materialize Console at http://localhost:6874 and checking that sources and views exist.

## Service Management

### Using Make (Recommended)

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

### Using Docker Compose Directly

```bash
# Restart the API service
docker compose restart api

# Restart all services
docker compose restart

# Rebuild and restart API (after code changes)
docker compose up -d --build api

# Stop all services (network persists)
docker compose down

# Stop and remove volumes (full reset, network still persists)
docker compose down -v

# To also remove the persistent network
make clean-network
# or
docker network rm freshmart-network
```

### Service Status

```bash
# Check running services
docker compose ps

# Check individual service
docker compose ps api

# View resource usage
docker stats
```

## Viewing Logs

### Real-Time Logs

```bash
# View API logs (with query timing)
docker compose logs -f api

# View last 100 lines of API logs
docker compose logs --tail=100 api

# View logs for multiple services
docker compose logs -f api mz

# View Materialize logs
docker compose logs -f mz

# View all service logs
docker compose logs -f
```

### Filter Logs

```bash
# Filter by operation type
docker compose logs -f api | grep -E "\[INSERT\]|\[UPDATE\]|\[DELETE\]"

# Only show reads
docker compose logs -f api | grep "\[SELECT\]"

# Only show slow queries
docker compose logs -f api | grep "SLOW QUERY"

# Show database-specific logs
docker compose logs -f api | grep -E "\[Materialize\]|\[PostgreSQL\]"
```

## Query Logging

All database queries are logged with execution time. The logs show:
- **Database**: `[PostgreSQL]` or `[Materialize]`
- **Operation**: `[SELECT]`, `[INSERT]`, `[UPDATE]`, `[DELETE]`, or `[SET]`
- **Execution time**: in milliseconds
- **Query**: SQL statement (truncated if > 200 chars)
- **Parameters**: query parameters

### Example Log Output

```
[Materialize] [SET] 1.23ms: SET CLUSTER = serving | params={}
[Materialize] [SELECT] 15.67ms: SELECT order_id, order_number, order_status... | params={'limit': 100, 'offset': 0}
[PostgreSQL] [INSERT] 3.45ms: INSERT INTO triples (subject_id, predicate...) | params={'subject_id': 'order:FM-1001', ...}
[PostgreSQL] [UPDATE] 2.89ms: UPDATE triples SET object_value = ... | params={'id': 123, 'value': 'DELIVERED'}
```

### Slow Query Warnings

Queries exceeding 100ms are logged as warnings:

```
[Materialize] [SELECT] SLOW QUERY 150.23ms (threshold: 100ms): SELECT...
```

### View Query Logs

```bash
# Real-time query logs
docker compose logs -f api | grep -E "\[Materialize\]|\[PostgreSQL\]"

# Filter by operation type
docker compose logs -f api | grep -E "\[INSERT\]|\[UPDATE\]|\[DELETE\]"

# Only show reads (all from Materialize serving cluster)
docker compose logs -f api | grep "\[SELECT\]"

# Only show slow queries
docker compose logs -f api | grep "SLOW QUERY"
```

## Query Statistics

The `/stats` endpoint provides aggregated query statistics:

```bash
curl http://localhost:8080/stats
```

**Response:**
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

## Materialize Console

Access the Materialize Admin Console at **http://localhost:6874** to monitor:
- Clusters (ingest, compute, serving)
- Sources (pg_source with CDC)
- Views (regular and materialized)
- Indexes
- Query performance

### Verify Queries Hit Serving Cluster

```bash
# Watch query logs - should show [Materialize]
docker compose logs -f api | grep -E "\[Materialize\]"

# Example output:
# [Materialize] [SET] 0.68ms: SET CLUSTER = serving | params=()
# [Materialize] [SELECT] 4.30ms: SELECT order_id, order_number... | params=(100, 0)
```

## Troubleshooting

### OpenSearch Sync Issues

#### Check Kafka Connect Pipeline Status

```bash
# View Kafka Connect logs (OpenSearch sink + embedding SMT)
docker compose logs -f kafka-connect

# Check connector / task status via the Connect REST API
curl -s http://localhost:8083/connectors | jq
curl -s http://localhost:8083/connectors/orders-opensearch-sink/status | jq
curl -s http://localhost:8083/connectors/inventory-opensearch-sink/status | jq

# Each connector and its task should report "state": "RUNNING"

# Check the embedding service used by the orders connector's SMT (and query-time kNN)
docker compose logs -f embedding-service
curl -s http://localhost:8085/v1/models | jq
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

# Check that Kafka Connect is processing records
docker compose logs --tail=50 kafka-connect | grep -Ei "put|flush|record"
```

#### Common Issues

**Connectors Not Running / Not Registered:**

```bash
# Symptom: orders/inventory indices not updating, no connectors listed
# Check if Materialize is running and the sinks exist
docker compose ps mz
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -d materialize \
  -c "SHOW SINKS;"

# Should see: orders_sink, inventory_sink

# Check that the connectors are registered with Kafka Connect
curl -s http://localhost:8083/connectors | jq

# If missing, re-run the one-shot connect-init (templates, indices, connectors)
docker compose up connect-init

# Restart a failed connector
curl -X POST http://localhost:8083/connectors/orders-opensearch-sink/restart
```

**High Sync Latency (> 5 seconds):**

```bash
# Inspect connector task status for errors / lag
curl -s http://localhost:8083/connectors/orders-opensearch-sink/status | jq

# Check Kafka Connect logs for errors (sink puts, embedding SMT calls)
docker compose logs kafka-connect | grep -Ei "error|warn"

# If the orders connector is slow, the embedding service may be the bottleneck
docker compose logs embedding-service | grep -Ei "error|warn"

# Verify the Materialize sink source view is updating
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_with_lines_mv;"
```

**OpenSearch Index Drift:**

```bash
# Compare counts between Materialize and OpenSearch

# Orders index
MZ_ORDERS=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM orders_with_lines_mv;")
OS_ORDERS=$(curl -s 'http://localhost:9200/orders/_count' | jq '.count')
echo "Orders - Materialize: $MZ_ORDERS, OpenSearch: $OS_ORDERS"

# Inventory index
MZ_INVENTORY=$(PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -t -c \
  "SET CLUSTER = serving; SELECT COUNT(*) FROM inventory_items_with_dynamic_pricing_mv;")
OS_INVENTORY=$(curl -s 'http://localhost:9200/inventory/_count' | jq '.count')
echo "Inventory - Materialize: $MZ_INVENTORY, OpenSearch: $OS_INVENTORY"

# If drift detected, reset the connector to re-consume from the start of the topic
curl -X DELETE http://localhost:8083/connectors/orders-opensearch-sink
docker compose up connect-init
```

### Service Health Checks

```bash
# Check API health
curl http://localhost:8080/health

# Check readiness (verifies DB connectivity)
curl http://localhost:8080/ready

# Check agent health
curl http://localhost:8081/health

# Check OpenSearch
curl http://localhost:9200/_cluster/health
```

### Database Connection Issues

```bash
# Connect to PostgreSQL
PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d freshmart

# Connect to Materialize
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -d materialize

# Test from inside API container
docker compose exec api python -c "from src.config import settings; print(settings.pg_external_url)"
```

### Materialize Initialization Issues

```bash
# Check if Materialize is initialized
PGPASSWORD=materialize psql -h localhost -p 6875 -U materialize -d materialize \
  -c "SHOW SOURCES;"

# Should show: pg_source

# Reinitialize if needed
./db/materialize/init.sh

# Or using make
make init-mz
```

### Agent Issues

See detailed debugging in [Agents Guide](AGENTS.md#debugging).

```bash
# Check configuration
docker compose exec agents python -m src.main check

# Enable debug logging
LOG_LEVEL=DEBUG docker compose --profile agent up agents

# Verify LLM API key
docker compose exec agents env | grep API_KEY
```

## Environment Variables

See `.env.example` for all available configuration:

### Database Configuration

```bash
# Use external PostgreSQL (for production)
PG_EXTERNAL_URL=postgresql://user:pass@host:5432/db

# Use external Materialize (for cloud deployment)
MZ_EXTERNAL_URL=postgresql://user:pass@host:6875/materialize

# Local defaults (for development)
PG_HOST=db
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=postgres
PG_DATABASE=freshmart

MZ_HOST=mz
MZ_PORT=6875
MZ_USER=materialize
MZ_PASSWORD=materialize
MZ_DATABASE=materialize
```

### Feature Flags

```bash
# Use Materialize for reads (default: true)
USE_MATERIALIZE_FOR_READS=true

# Set to false to query PostgreSQL directly instead
# Useful for:
# - Development without Materialize
# - Debugging query differences
# - Environments where Materialize isn't available
```

### LLM Configuration (for Agents)

```bash
# Anthropic (recommended)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI
OPENAI_API_KEY=sk-...
```

### Search Indexing Configuration

Search indexing runs through Materialize Kafka sinks, Redpanda, and Kafka Connect.
The embedding service (used by the orders connector's SMT and by query-time kNN)
is configured via:

```bash
# Embedding service (OpenAI-compatible facade over fastembed BAAI/bge-small-en-v1.5)
EMBEDDING_SERVICE_URL=http://embedding-service:8085
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5   # 384-dim
```

Connector definitions, OpenSearch index templates, and the embedding SMT config are
applied by the one-shot `connect-init` service and live under `kafka-connect/`.

## Load Test Data Generation

Generate realistic operational data to demonstrate PostgreSQL vs Materialize performance:

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

Materialize views update automatically via CDC - no rebuild needed.

## Production Scaling Considerations

### Current Architecture (Development)

- Single PostgreSQL instance with logical replication enabled
- Materialize Emulator with admin console
- Single-node OpenSearch
- Single-broker Redpanda + single-worker Kafka Connect for search indexing

### Production Scaling

1. **Database**: Switch to managed PostgreSQL (Neon, RDS, Supabase)
2. **Materialize**: Use cloud Materialize for true streaming
3. **OpenSearch**: Use managed OpenSearch with replication
4. **Search indexing**: Use managed Kafka/Redpanda + a Kafka Connect cluster with multiple tasks/partitions
5. **API**: Horizontal scaling behind load balancer

### Security Considerations

- API authentication (add JWT/OAuth for production)
- Database connection pooling with SSL
- OpenSearch authentication
- Environment-based secrets management
- CORS configuration for production domains

## See Also

- [Architecture Guide](ARCHITECTURE.md) - System architecture and data flow
- [API Reference](API_REFERENCE.md) - Complete API documentation
- [Agents Guide](AGENTS.md) - AI agent debugging
- [Contributing Guide](CONTRIBUTING.md) - Development setup and testing
