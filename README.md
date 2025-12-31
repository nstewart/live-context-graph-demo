# FreshMart Digital Twin Agent Starter

A production-ready starter for building semantic knowledge graphs with live materialized views, AI agents, and full-text search.

## What Is This?

This project demonstrates a **live digital twin** of same-day grocery delivery operations powered by:

- **PostgreSQL** as a governed triple store with ontology-based validation
- **Materialize** for real-time CQRS read models with sub-second CDC
- **OpenSearch** for natural language search over orders and inventory
- **LangGraph Agents** with semantic reasoning over the knowledge graph
- **React Admin UI** with WebSocket-powered real-time updates

**Why digital twins?** AI agents need access to **fresh operational context** that reflects your business at the current moment. This starter transforms operational data into **live data products**—composable contextual building blocks maintained continuously—enabling agents to observe, reason, and act within your **latency budget**. Rather than waiting for batch ETL or querying stale data, agents operate in **operational space** where consequences of their actions are visible within seconds, enabling tight feedback loops for multi-agent coordination.

## Who Is This For?

- Developers building **AI agents** that reason over operational data
- Teams minimizing time-to-confident action based on changes to **semantic knowledge graphs**
- Projects requiring **live materialized views** over graph data with sub-second end-to-end latency
- Organizations exploring **CQRS patterns** with ontology validation


## Quick Start

```bash
# Clone and configure
git clone https://github.com/nstewart/live-agent-ontology-demo.git
cd live-agent-ontology-demo
cp .env.example .env

# Install uv (Python package manager) if not already installed
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh
# Or on macOS with Homebrew:
brew install uv

# Start with AI agent included
make up-agent
```

**Services will be ready at:**
- Admin UI: http://localhost:5173
- API Docs: http://localhost:8080/docs
- Materialize Console: http://localhost:6874
- OpenSearch: http://localhost:9200

The system automatically seeds demo data: 5 stores, 15 products, 15 customers, 20 orders.

## Core Features

### Low-latency Data Synchronization
- **Sub-second CDC** from PostgreSQL to Materialize via replication
- **Differential streaming** to UI clients via Zero WebSocket protocol
- **Speed layer for operational decisions**: Agents and users operate in real-time, not batch ETL time
- **Tight feedback loops**: Changes appear in UI, search indexes, and materialized views simultaneously
- **Butterfly effect visibility**: See cascading consequences of actions across the system within seconds

### Semantic Knowledge Graph
- **RDF-style triples** (subject-predicate-object) as universal data model
- **Ontology validation** enforces schema at write time
- **Class and property definitions** prevent invalid data entry
- **Entity references** maintain graph relationships with referential integrity

### CQRS Architecture
- **Write model**: PostgreSQL triple store with ontology validation
- **Read model**: Materialize materialized views optimized per query pattern with pre-assembled context
- **No latency-freshness tradeoff**: Get the data freshness of an OLTP system with the last-mile context assembly of a data warehouse
- **Independent scaling** of writes (PostgreSQL) and reads (Materialize)
- **Agents stay within latency budget**: No approximating data, accepting stale inputs, or sacrificing correctness for latency

### Dynamic Pricing Engine
- **Zone-based adjustments**: Manhattan (+15%), Brooklyn (+5%), baseline Queens
- **Perishability discounts**: 5% off to move inventory faster
- **Local scarcity premiums**: +10% for items with low store stock
- **Demand multipliers**: Real-time pricing based on sales velocity (recent 7-day vs prior 7-day unit sales)
- **Live price display** in UI shopping cart and order creation

### AI-Powered Operations
- **Agent control loop**: Observe (pre-assembled context in milliseconds) → Think (LLM reasoning) → Act (writes visible within seconds)
- **Embedded Chat Widget**: Floating Operations Assistant accessible from any page with SSE streaming
- **Natural language search** over orders and inventory via OpenSearch
- **LangGraph agents** with tools for semantic reasoning over the knowledge graph
- **Conversational memory** with PostgreSQL-backed checkpointing
- **Tight feedback loops**: Agents see consequences of their actions immediately, enabling multi-agent coordination
- **Write operations**: Create customers, orders, and update statuses
- **Read operations**: Search, fetch context, and analyze data without querying stale snapshots

### Full-Text Search
- **Orders index**: Search by customer name, address, order number, status
- **Inventory index**: Search by product name, category, store, ingredients
- **Real-time sync**: < 2 second latency from write to searchable
- **SUBSCRIBE streaming**: Differential updates from Materialize to OpenSearch

## Architecture Overview

FreshMart implements **CQRS (Command Query Responsibility Segregation)** to separate write and read concerns:

**Write Path:**
All data modifications flow through the PostgreSQL triple store where they are validated against the ontology schema (classes, properties, ranges, domains). This ensures semantic consistency and referential integrity at write time.

**Read Path:**
Queries use Materialize materialized views that provide **millisecond access to sub-second fresh data**. Rather than querying multiple tables on demand, agents and users access **pre-assembled context** that is incrementally maintained through a three-tier architecture (ingest cluster for CDC, compute cluster for aggregation, serving cluster for indexed queries).

**Benefits:**
- Write model enforces schema through ontology validation
- Read model provides **pre-assembled context** optimized for specific query patterns
- **Millisecond access to sub-second fresh data**: No waiting for batch ETL or dealing with stale data
- Avoids the **latency-freshness tradeoff** that plagues traditional architectures
- Independent scaling of write and read workloads

**Data Flow:**
```
User → API → PostgreSQL (validated write)
              ↓ CDC
              Materialize (materialized views)
              ↓ SUBSCRIBE
              Zero Server → WebSocket → UI (live updates)
              ↓ SUBSCRIBE
              Search Sync → OpenSearch (full-text search)
```

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed component descriptions and data flow diagrams.

## API Overview

The Graph API (FastAPI, port 8080) provides three main categories of endpoints:

**Ontology Management (`/ontology`)**
Define and manage schema classes and properties. Control what entity types exist and what predicates are valid for each class.

**Triple Store CRUD (`/triples`)**
Manage knowledge graph data as subject-predicate-object triples. All writes are validated against the ontology before persistence.

**FreshMart Operations (`/freshmart`)**
Query pre-computed, denormalized views powered by Materialize. Includes orders, stores, inventory, customers, products, and couriers.

See [API_REFERENCE.md](docs/API_REFERENCE.md) for complete endpoint documentation with examples.

## Using the AI Agent

### Prerequisites

Add an LLM API key to your `.env` file:

```bash
# Option 1: Anthropic (recommended)
ANTHROPIC_API_KEY=sk-ant-...

# Option 2: OpenAI
OPENAI_API_KEY=sk-...
```

### Start Agent Service

```bash
# Using make (handles initialization)
make up-agent

# Or using docker-compose directly
docker-compose --profile agent up -d
docker-compose exec agents python -m src.init_checkpointer
```

### Chat Widget (Recommended)

The easiest way to interact with the Operations Assistant is through the embedded chat widget in the Admin UI:

1. Open the Admin UI at http://localhost:5173
2. Click the green chat bubble in the bottom-right corner
3. Ask questions or give commands in natural language

**Features:**
- **SSE Streaming**: See tool calls and results in real-time as the agent works
- **Markdown Rendering**: Formatted responses with tables, lists, and code
- **Session Persistence**: Conversation memory maintained across page navigation
- **Thinking Display**: Expandable view of agent reasoning steps

**Example queries:**
- "List all stores in Queens"
- "What couriers are available at store:MAN-01?"
- "Find orders for Lisa that are out for delivery"
- "Add 2 gallons of milk to order FM-000001"

### Terminal Chat

```bash
# Start interactive session with conversation memory
docker-compose exec -it agents python -m src.main chat

# Example conversation:
> Find orders for Lisa
> Show me her orders that are out for delivery
> Mark order FM-1001 as DELIVERED
> Create an order for John at Brooklyn store with milk and eggs
```

### Single Command

```bash
# One-time query
docker-compose exec agents python -m src.main chat "Show all OUT_FOR_DELIVERY orders"

# Search inventory
docker-compose exec agents python -m src.main chat "Find stores with organic milk in stock"
```

See [AGENTS.md](docs/AGENTS.md) for complete agent capabilities, tool descriptions, and HTTP API usage.

## Services

| Service | Port | Description |
|---------|------|-------------|
| **db** | 5432 | PostgreSQL - primary triple store |
| **mz** | 6874 | Materialize Admin Console |
| **mz** | 6875 | Materialize SQL interface |
| **zero-cache** | 4848 | Zero cache for real-time UI updates |
| **opensearch** | 9200 | Search engine for orders and inventory |
| **api** | 8080 | FastAPI backend |
| **search-sync** | 8083 | SUBSCRIBE workers for OpenSearch sync + propagation API |
| **web** | 5173 | React admin UI with real-time updates and chat widget |
| **agents** | 8081 | LangGraph agent with SSE streaming API (optional) |

## Development

### Essential Commands

```bash
# Start all services
make up

# Start with agents
make up-agent

# Stop services (data persists)
make down

# View logs
docker-compose logs -f api
docker-compose logs -f search-sync

# Track write propagation (clean output, strips timestamps)
docker-compose logs -f api search-sync | sed 's/.*INFO - //'

# Restart a service
docker-compose restart api

# Run tests
docker-compose exec api python -m pytest tests/ -v

# See all commands
make help
```

### Generate Load Test Data

```bash
# Generate ~700K triples (6 months of operations)
./db/scripts/generate_data.sh

# Or smaller dataset for quick testing
./db/scripts/generate_data.sh --scale 0.1
```

### Generate Live Load

For continuous, realistic activity that demonstrates real-time data flow:

```bash
# Start load generator with demo profile (5 orders/min)
make load-gen

# Or use specific profiles
make load-gen-standard  # 20 orders/min
make load-gen-peak      # 60 orders/min
make load-gen-stress    # 200 orders/min
```

See [load-generator/README.md](load-generator/README.md) for detailed documentation.

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup, testing guidelines, and contribution workflow.

## Project Structure

```
freshmart-digital-twin-agent-starter/
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Common commands
├── .env.example                # Environment template
│
├── db/
│   ├── migrations/             # SQL migrations
│   ├── seed/                   # Demo data
│   ├── materialize/            # Materialize initialization
│   └── scripts/                # Load test data generator
│
├── api/                        # FastAPI backend
│   ├── src/
│   │   ├── ontology/          # Ontology CRUD
│   │   ├── triples/           # Triple store + validation
│   │   ├── freshmart/         # Operational endpoints
│   │   └── routes/            # HTTP routes
│   └── tests/                  # Unit and integration tests
│
├── search-sync/               # OpenSearch sync workers
│   └── src/
│       ├── base_subscribe_worker.py  # Abstract base class
│       ├── orders_sync.py     # Orders sync worker
│       └── inventory_sync.py  # Inventory sync worker
│
├── zero-server/               # WebSocket server
│   └── src/
│       ├── server.ts          # Zero protocol WebSocket server
│       └── materialize-backend.ts  # SUBSCRIBE to Materialize
│
├── web/                       # React admin UI
│   └── src/
│       ├── api/               # API client
│       ├── components/        # ChatWidget and other shared components
│       ├── contexts/          # ChatContext for agent communication
│       ├── hooks/             # useZeroQuery for real-time data
│       └── pages/             # Orders, Couriers, Stores dashboards
│
├── agents/                    # LangGraph agents
│   └── src/
│       ├── server.py          # FastAPI server with SSE streaming
│       ├── tools/             # Agent tools (list_stores, list_couriers, etc.)
│       └── graphs/            # LangGraph definitions
│
└── docs/                      # Documentation
```

## Documentation Index

### Core Concepts
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System architecture, data flow, and component details
- [ONTOLOGY.md](docs/ONTOLOGY.md) - Ontology design patterns and extending the schema
- [DATA_MODEL.md](docs/DATA_MODEL.md) - Triple store model, entity types, and relationships

### Implementation Guides
- [SEARCH.md](docs/SEARCH.md) - OpenSearch setup, sync architecture, and debugging
- [AGENTS.md](docs/AGENTS.md) - AI agent capabilities, tools, and integration patterns
- [UI_GUIDE.md](docs/UI_GUIDE.md) - React Admin UI features and real-time updates
- [ONTOLOGY_GUIDE.md](docs/ONTOLOGY_GUIDE.md) - Step-by-step guide to adding new entity types

### Operations
- [CONTRIBUTING.md](docs/CONTRIBUTING.md) - Development setup, testing, and contribution guidelines
- [API_REFERENCE.md](docs/API_REFERENCE.md) - Complete API endpoint documentation
- [OPENSEARCH_SYNC_RUNBOOK.md](docs/OPENSEARCH_SYNC_RUNBOOK.md) - Troubleshooting search sync issues
- [OPERATIONS.md](docs/OPERATIONS.md) - Service management and troubleshooting

### Advanced Topics
- [DYNAMIC_PRICING.md](docs/DYNAMIC_PRICING.md) - Dynamic pricing implementation and configuration

## Key Design Decisions

### Why RDF-Style Triples?
- Universal data model accommodates any entity type without schema migrations
- Semantic relationships preserved as first-class graph edges
- Ontology validation prevents invalid data at write time
- Easy to reason over with AI agents

### Why CQRS with Materialize?
- Write model (PostgreSQL) optimized for consistency and validation
- Read model (Materialize) can denormalize triples while applying complex business logic and send updates to downstream systems correctly
- Handle agentic reads via auery offload: Materialize does a small amount of work as writes come in so reads on maintained objects are essentially free.

### Why OpenSearch for Agents?
- Natural language queries require full-text search capabilities
- Agents can search by partial matches, synonyms, and fuzzy text
- OpenSearch provides relevance ranking for best-match results
- Complement to structured queries over Materialize views
- *This will ultimately support vectors for semantic search*

### Why Three-Tier Materialize Architecture?
- **Ingest cluster**: Dedicated resources for CDC replication
- **Compute cluster**: Isolated aggregation and transformation workloads
- **Serving cluster**: Indexed queries without impacting compute
- Resource isolation prevents one workload from starving others

## Known Limitations

### Zero and Materialize UNIQUE Index Constraint

**Issue**: Zero (the real-time sync layer) requires tables to have either a `PRIMARY KEY` constraint or a `UNIQUE` index. Materialize supports `PRIMARY KEY` on tables but does not support `UNIQUE` indexes on materialized views.

**Impact**: Time-series views created in Materialize (e.g., `store_metrics_timeseries_mv`, `system_metrics_timeseries_mv`) cannot be synced through Zero because they use generated composite keys that require `UNIQUE` indexes for Zero compatibility.

**Workaround**: Time-series data for sparklines and trend visualization is fetched via direct API polling instead of Zero sync:
- The `/api/metrics/timeseries` endpoint queries Materialize directly
- The `useMetricsTimeseries` React hook polls this endpoint every 5 seconds
- All other data (orders, stores, inventory, etc.) continues to sync in real-time through Zero

**Code locations**:
- API endpoint: `api/src/routes/metrics.py`
- React hook: `web/src/hooks/useMetricsTimeseries.ts`
- Time-series views: `db/materialize/init.sh` (lines 1165-1204)

**Alternative approaches considered**:
1. **Tables with PRIMARY KEY**: Would work but requires separate insert/update logic instead of incremental maintenance
2. **Composite string keys**: Implemented but Zero still requires UNIQUE index, not just a regular index
3. **Direct API polling**: Current solution - provides 5-second granularity which is acceptable for sparklines


## License

MIT

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for:
- Development setup instructions
- Testing guidelines
- Code style and conventions
- Pull request process
- Community guidelines

## Support

- **GitHub Issues**: Bug reports and feature requests
- **Documentation**: See `/docs` directory for detailed guides
- **API Reference**: Interactive Swagger UI at http://localhost:8080/docs
- **Examples**: See `db/seed/` for demo data examples
