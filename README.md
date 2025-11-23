# FreshMart Digital Twin Agent Starter

A forkable, batteries-included repository demonstrating how to build a **digital twin** of FreshMart's same-day grocery delivery operations using:

- **PostgreSQL** as a triple store with ontology validation
- **Materialize Emulator** for real-time materialized views with admin console
- **OpenSearch** for full-text search and discovery
- **LangGraph Agents** with tools for AI-powered operations assistance
- **React Admin UI** for managing the ontology and browsing operations

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/your-org/freshmart-digital-twin-agent-starter.git
cd freshmart-digital-twin-agent-starter

# 2. Configure environment
cp .env.example .env
# Edit .env to add your LLM API keys if using the agent

# 3. Start all services
docker-compose up -d

# 4. Access the services
# - Admin UI: http://localhost:5173
# - API Docs: http://localhost:8080/docs
# - Materialize Console: http://localhost:6874
# - OpenSearch: http://localhost:9200
```

The system will automatically:
- Run database migrations
- Seed demo data (5 stores, 15 products, 15 customers, 20 orders)
- Sync orders to OpenSearch

### Initialize Materialize (First Run)

After the first `docker-compose up`, initialize Materialize to set up the PostgreSQL source and views:

```bash
# Option 1: Run the init script from host (requires psql)
./db/materialize/init.sh

# Option 2: Run from within the mz container
docker-compose exec mz psql -U materialize -h localhost -p 6875 -f /init_materialize.sql
```

You can verify the setup by visiting the Materialize Console at http://localhost:6874 and checking that sources and views exist.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Admin UI (React)                                 │
│                         Port: 5173                                       │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Graph/Ontology API (FastAPI)                          │
│                         Port: 8080                                       │
│  • Ontology CRUD       • Triple CRUD with validation                     │
│  • FreshMart endpoints • Health checks                                   │
│  • Query logging with execution time                                     │
└──────────────┬────────────────────────────────────┬─────────────────────┘
               │                                    │
               │ (writes)                           │ (UI reads)
               ▼                                    ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│     PostgreSQL           │         │   Materialize Emulator    │
│     Port: 5432           │────────▶│  Console: 6874 SQL: 6875  │
│  • ontology_classes      │ (CDC)   │  Three-Tier Architecture: │
│  • ontology_properties   │         │  • ingest: pg_source      │
│  • triples               │         │  • compute: MVs           │
└──────────────────────────┘         │  • serving: indexes       │
                                     └───────────┬──────────────┘
                                                 │
                                                 ▼
                                     ┌──────────────────────────┐
                                     │    Search Sync Worker     │
                                     │  (polls every 5 seconds)  │
                                     └───────────┬──────────────┘
                                                 │
                                                 ▼
┌──────────────────────────┐         ┌──────────────────────────┐
│    LangGraph Agents       │────────▶│      OpenSearch          │
│      Port: 8081           │         │       Port: 9200         │
│  • search_orders          │         │  • orders index          │
│  • fetch_order_context    │         │                          │
│  • write_triples          │         │                          │
└──────────────────────────┘         └──────────────────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL - primary triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **opensearch** | 9200 | Search engine for orders |
| **api** | 8080 | FastAPI backend |
| **search-sync** | - | Background worker syncing to OpenSearch |
| **web** | 5173 | React admin UI |
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

# Get subject with all triples
GET /triples/subjects/order:FM-1001

# List subjects by class
GET /triples/subjects/list?class_name=Order
```

### FreshMart Operations

```bash
# List orders with filters
GET /freshmart/orders?status=OUT_FOR_DELIVERY

# Get order details
GET /freshmart/orders/order:FM-1001

# List stores
GET /freshmart/stores

# Get store with inventory
GET /freshmart/stores/store:BK-01

# List couriers
GET /freshmart/couriers?status=AVAILABLE
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
# Start with the agent profile
docker-compose --profile agent up -d

# Check configuration
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

```bash
# Restart the API service
docker-compose restart api

# Restart all services
docker-compose restart

# Rebuild and restart API (after code changes)
docker-compose up -d --build api

# Stop all services
docker-compose down

# Stop and remove volumes (full reset)
docker-compose down -v
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
```

### Materialize Three-Tier Architecture

All UI read queries are routed through Materialize's **serving cluster** for low-latency indexed access:

```
UI → API → Materialize (serving cluster) → Indexed Materialized Views
```

The architecture uses three clusters:
- **ingest**: PostgreSQL source replication via CDC
- **compute**: Materialized view computation
- **serving**: Indexes for low-latency queries

To verify queries are hitting the serving cluster:
```bash
# Watch query logs - should show [Materialize]
docker-compose logs -f api | grep -E "\[Materialize\]"

# Example output:
# [Materialize] [SET] 0.68ms: SET CLUSTER = serving | params=()
# [Materialize] [SELECT] 4.30ms: SELECT order_id, order_number... | params=(100, 0)
```

## Development

### Running Tests

```bash
# API tests (requires database connection)
cd api
export PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DATABASE=freshmart
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
```

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
│   ├── seed/                   # Demo data
│   ├── materialize/            # Materialize emulator init
│   └── scripts/                # Helper scripts
│
├── api/                        # FastAPI backend
│   ├── src/
│   │   ├── ontology/          # Ontology CRUD
│   │   ├── triples/           # Triple store + validation
│   │   ├── freshmart/         # FreshMart operational endpoints
│   │   └── routes/            # HTTP routes
│   └── tests/                 # API tests
│
├── search-sync/               # OpenSearch sync worker
│   └── src/
│       ├── mz_client.py       # Materialize queries
│       ├── opensearch_client.py
│       └── orders_sync.py     # Sync logic
│
├── web/                       # React admin UI
│   └── src/
│       ├── api/               # API client
│       └── pages/             # UI pages
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

The React Admin UI (`web/`) provides CRUD operations for managing FreshMart entities:

### Orders Dashboard
- View all orders with status badges and filtering
- Create new orders with dropdown selectors for:
  - **Customer**: Format "Customer Name (customer:ID)"
  - **Store**: Format "Store Name (store:ID)"
- Edit existing orders with pre-populated form fields
- Delete orders with confirmation dialog

### Couriers & Schedule
- View all couriers with their assigned tasks
- Create new couriers with dropdown selector for:
  - **Home Store**: Format "Store Name (store:ID)"
- Edit courier details including status and vehicle type
- Delete couriers with confirmation dialog

### Stores Inventory
- View stores with their current inventory levels
- Create/edit stores with zone and capacity settings
- Manage inventory items per store

All dropdown data is fetched from Materialize's serving cluster for low-latency access.

## Acceptance Criteria

From a clean checkout:

1. **Setup**: `cp .env.example .env && docker-compose up -d` starts all services
2. **Admin UI**: Shows classes, properties, orders dashboard at `localhost:5173`
3. **API**: `GET /freshmart/orders` returns demo orders
4. **Validation**: Invalid triples return 400 with clear error messages
5. **Search**: Orders indexed in OpenSearch and searchable
6. **Agent**: Can search orders and update status via natural language

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for detailed guidelines.
