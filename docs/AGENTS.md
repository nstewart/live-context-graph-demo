# AI Agents Guide

Complete guide to the LangGraph-powered operations assistant with conversational memory and multi-tool capabilities.

## Table of Contents

- [Overview](#overview)
- [Capabilities](#capabilities)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Using the Agent](#using-the-agent)
- [Available Tools](#available-tools)
- [Example Queries](#example-queries)
- [Customizing the Agent](#customizing-the-agent)
- [Configuration](#configuration)
- [Safety and Limits](#safety--limits)
- [Debugging](#debugging)

## Overview

The FreshMart Operations Assistant is an AI agent that helps operations staff manage FreshMart's same-day grocery delivery operations through natural language interactions.

**Key Features:**
- Natural language order search and management
- Inventory discovery across stores
- Customer and order creation
- Conversational memory for follow-up questions
- Tool-based reasoning with multiple capabilities
- PostgreSQL-backed conversation persistence

## Capabilities

### Order Management
- **Search orders** by customer name, address, order number, or status (searches OpenSearch `orders` index)
- **Fetch order details** with full context including line items, customer info, delivery tasks
- **Update order status** (CREATED → PICKING → OUT_FOR_DELIVERY → DELIVERED)

### Inventory & Product Discovery
- **Search inventory** by product name, category, store, or availability (searches OpenSearch `inventory` index)
- Find products across stores with real-time stock levels
- Ingredient-aware search with synonyms (e.g., "milk" finds whole milk, 2% milk, skim milk)

### Customer & Order Creation
- **Create new customers** with name, email, address, and phone
- **Create complete orders** with customer selection, store selection, and multiple line items
- Automatically validates product availability and inventory at selected store
- **Stock validation**: Returns error if insufficient stock (no silent quantity changes)
- **Live pricing**: Uses current dynamic prices from inventory automatically

### Knowledge Graph Operations
- **Query the ontology** to understand entity types and properties
- **Write triples** directly to the knowledge graph for custom updates
- Read any entity's full context from the triple store

### Conversational Memory
- **Remember conversation context** across multiple messages using PostgreSQL-backed checkpointing
- Maintains session state for natural follow-up questions
- References previous searches and entities mentioned in conversation

## Prerequisites

The agent requires an LLM API key. Add one to your `.env` file:

```bash
# Option 1: Anthropic (recommended)
ANTHROPIC_API_KEY=sk-ant-...

# Option 2: OpenAI
OPENAI_API_KEY=sk-...
```

## Getting Started

### Start the Agent Service

```bash
# Option 1: Using make (recommended - handles everything automatically)
make up-agent

# Option 2: Using docker compose directly
docker network create freshmart-network  # if not already created
docker compose --profile agent up -d
./db/materialize/init.sh  # if not already initialized
docker compose exec agents python -m src.init_checkpointer  # initialize conversation memory
```

**Note:** `make up-agent` automatically:
- Starts all services including the agent
- Initializes Materialize sources and views
- Creates PostgreSQL checkpointer tables for conversation memory

### Check Configuration

```bash
docker compose exec agents python -m src.main check
```

## Using the Agent

### Interactive Mode (Recommended)

Start an interactive chat session with persistent conversation memory:

```bash
# Start interactive chat (creates a unique session)
docker compose exec -it agents python -m src.main chat
```

**Example Conversation:**

```
You: Find orders for Lisa
Assistant: I found 2 orders for customers named Lisa:
- Order FM-1001: $125.50 for Lisa Chen (OUT_FOR_DELIVERY)
- Order FM-1005: $87.30 for Lisa Martinez (DELIVERED)

You: Show me her orders that are out for delivery
Assistant: Based on the previous search for Lisa, here are her OUT_FOR_DELIVERY orders:
- Order FM-1001: $125.50 for Lisa Chen
  Delivery window: 2:00 PM - 4:00 PM
  Store: FreshMart Brooklyn 1

You: What's the status of order FM-1001?
Assistant: Order FM-1001 is currently OUT_FOR_DELIVERY, assigned to courier John Delivery.
Expected delivery: 3:30 PM

You: Mark that order as delivered
Assistant: I'll update order FM-1001 to DELIVERED status...
✓ Order FM-1001 has been marked as DELIVERED.
```

**Memory Features:**
- Each interactive session gets a unique `thread_id` displayed on startup
- All messages in that session share the same conversation history
- Context is maintained for follow-up questions and pronouns ("her", "that order", etc.)

### Single Command Mode

Run a single query without entering interactive mode:

```bash
# One-time query (creates a temporary thread_id)
docker compose exec agents python -m src.main chat "Show all orders for customer Alex Thompson"

# Continue a conversation across multiple commands with --thread-id
docker compose exec agents python -m src.main chat --thread-id my-session "Find orders for Lisa"
docker compose exec agents python -m src.main chat --thread-id my-session "Show me her orders"
```

### HTTP API

The agent service exposes an HTTP API on port 8081:

#### Health Check

```bash
curl http://localhost:8081/health
```

#### Chat Endpoint

```bash
# New conversation (thread_id generated automatically)
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show all OUT_FOR_DELIVERY orders"}'

# Continue existing conversation
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Find orders for Lisa",
    "thread_id": "user-123-session"
  }'

curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me her orders",
    "thread_id": "user-123-session"
  }'
```

**Response Format:**
```json
{
  "response": "I found 2 orders for Lisa...",
  "thread_id": "user-123-session"
}
```

### Programmatic Usage

```python
from src.graphs.ops_assistant_graph import run_assistant

# Single query (one-time thread)
response = await run_assistant("Find orders at risk of missing their delivery window")
print(response)

# Multi-turn conversation with memory
thread_id = "user-456-session"
response1 = await run_assistant("Find orders for Lisa", thread_id=thread_id)
print(response1)

response2 = await run_assistant("Show me her orders", thread_id=thread_id)
print(response2)  # Agent remembers Lisa from previous message
```

## Available Tools

### list_stores

List all FreshMart store locations with their IDs and details.

**Parameters:**
- `zone` (str, optional): Filter by zone (MAN, BK, QNS, BX, SI)

**Example:**
```python
# List all stores
stores = await list_stores()

# List stores in Queens only
stores = await list_stores(zone="QNS")
```

**Returns:**
- List of stores with store_id, store_name, zone, and address

**Use Case:**
Use this tool FIRST when a user mentions a store by name or zone to find the correct store_id for use with other tools like search_inventory.

### search_orders

Search for orders using natural language via OpenSearch.

**Parameters:**
- `query` (str): Search query (customer name, address, order number)
- `status` (str, optional): Filter by order status
- `limit` (int): Max results (default 10)

**Example:**
```python
results = await search_orders(
    query="Alex Thompson",
    status="OUT_FOR_DELIVERY",
    limit=10
)
```

**Returns:**
- List of matching orders with customer, store, delivery details, and line items

### search_inventory

Search for products and inventory across stores.

**Parameters:**
- `query` (str): Product name, category, or keywords
- `store_id` (str, optional): Filter by specific store
- `limit` (int): Max results (default 10)

**Example:**
```python
results = await search_inventory(
    query="organic milk",
    store_id="store:BK-01"
)
```

**Returns:**
- List of inventory items with product details, stock levels, prices

### fetch_order_context

Get detailed information for specific orders from the triple store.

**Parameters:**
- `order_ids` (list[str]): Order IDs to fetch

**Example:**
```python
orders = await fetch_order_context(["order:FM-1001", "order:FM-1002"])
```

**Returns:**
- Complete order context including all triples

### create_customer

Create a new customer entity.

**Parameters:**
- `name` (str): Customer name
- `email` (str): Email address
- `address` (str): Delivery address
- `phone` (str): Phone number

**Example:**
```python
customer = await create_customer(
    name="John Smith",
    email="john@example.com",
    address="123 Main St, Brooklyn",
    phone="555-0123"
)
```

**Returns:**
- New customer ID

### create_order

Create a complete order with line items.

**Parameters:**
- `customer_id` (str): Customer ID (e.g., "customer:123")
- `store_id` (str): Store ID (e.g., "store:BK-01")
- `line_items` (list[dict]): Products and quantities
- `delivery_window_start` (str, optional): ISO datetime
- `delivery_window_end` (str, optional): ISO datetime

**Example:**
```python
order = await create_order(
    customer_id="customer:123",
    store_id="store:BK-01",
    line_items=[
        {"product_id": "product:MILK-WH", "quantity": 2},
        {"product_id": "product:EGGS-12", "quantity": 1}
    ]
)
```

**Returns:**
- New order ID and details

**Features:**
- Automatically validates stock availability
- Uses live dynamic prices
- Returns error if insufficient inventory

### get_context_graph

Retrieve the knowledge graph schema.

**Returns:**
- Classes: Entity types with prefixes
- Properties: Attributes and relationships

**Example:**
```python
schema = await get_context_graph()
# Returns classes and properties
```

### write_triples

Create or update data in the knowledge graph.

**Parameters:**
- `triples` (list[dict]): Triples to write
- `validate_ontology` (bool): Validate against ontology (default True)

**Example:**
```python
results = await write_triples([
    {
        "subject_id": "order:FM-1001",
        "predicate": "order_status",
        "object_value": "DELIVERED",
        "object_type": "string"
    }
])
```

**Note:** If a triple already exists with the same subject and predicate, it will be updated rather than creating a duplicate.

## Example Queries

### Order Search

```
"Find all orders for customer Alex"
"Show orders at store BK-01"
"What orders are currently being picked?"
"List orders with delivery window ending soon"
"Show me all orders using the SUMMER25 promo code"
```

### Order Details

```
"Show me details for order FM-1001"
"What's the status of Alex's order?"
"Who is delivering order FM-1002?"
"What items are in order FM-1001?"
```

### Status Updates

```
"Mark order FM-1001 as delivered"
"Cancel order FM-1004"
"Update FM-1003 to out for delivery"
"Change the status of order FM-1002 to picking"
```

### Inventory Search

```
"Find stores with milk in stock"
"Show me organic products at Brooklyn store"
"What dairy items are available?"
"Which stores have eggs with more than 50 units?"
```

### Customer and Order Creation

```
"Create a new customer named Jane Doe with email jane@example.com"
"Create an order for customer:123 at Manhattan store with 2 gallons of milk and 1 dozen eggs"
"Add a customer John Smith, address 456 Oak St, Brooklyn, phone 555-9999"
```

### Store Queries

```
"List all stores"
"What stores are in Queens?"
"Show me all Brooklyn stores"
"Find stores in Manhattan"
```

### System Queries

```
"What entity types exist in the system?"
"Show me properties for the Order class"
"What statuses can an order have?"
```

## Customizing the Agent

### Adding New Tools

1. Create tool function in `agents/src/tools/`:

```python
from langchain_core.tools import tool

@tool
async def check_store_capacity(store_id: str) -> dict:
    """
    Check current order capacity for a store.

    Args:
        store_id: Store ID (e.g., "store:BK-01")

    Returns:
        Current capacity and utilization
    """
    # Implementation
    pass
```

2. Add to tools list in `ops_assistant_graph.py`:

```python
from src.tools import check_store_capacity

TOOLS = [
    create_customer,
    list_stores,  # Note: list_stores should be early in the list
    search_orders,
    search_inventory,
    fetch_order_context,
    create_order,
    get_context_graph,
    write_triples,
    check_store_capacity,  # Add new tool
]
```

### Modifying the System Prompt

Edit `SYSTEM_PROMPT` in `ops_assistant_graph.py` to change agent behavior:

```python
SYSTEM_PROMPT = """You are an operations assistant for FreshMart...

Additional capabilities:
- Check store capacity before routing orders
- Recommend courier assignments based on location
"""
```

### Creating New Graphs

For specialized agents, create new graph files:

```python
# agents/src/graphs/inventory_assistant_graph.py

def create_inventory_assistant():
    """Create an agent focused on inventory management."""
    workflow = StateGraph(AgentState)
    # Customize for inventory use case
    return workflow.compile()
```

## Configuration

### LLM Provider

Set one of these environment variables in `.env`:

```bash
# For Anthropic Claude (default)
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
OPENAI_API_KEY=sk-...
```

### Model Selection

Edit `agents/src/config.py` to change the default model:

```python
llm_model: str = "claude-sonnet-4-20250514"  # Anthropic (default)
# or
llm_model: str = "gpt-4-turbo"  # OpenAI
```

### API Configuration

```bash
# Graph API endpoint (default: http://api:8080)
GRAPH_API_URL=http://localhost:8080

# OpenSearch endpoint (default: http://opensearch:9200)
OPENSEARCH_URL=http://localhost:9200

# PostgreSQL for checkpointer
CHECKPOINTER_DB_URL=postgresql://postgres:postgres@db:5432/freshmart
```

## Safety & Limits

The agent includes safety measures:

1. **Iteration Limit**: Max 10 tool calls per request
2. **Validation**: Triple writes validated against ontology
3. **Confirmation**: Destructive actions require explicit confirmation
4. **Timeouts**: HTTP requests timeout after 10 seconds
5. **Memory isolation**: Conversations are isolated by thread_id
6. **Persistent storage**: Conversation history stored in PostgreSQL
7. **Stock validation**: Orders fail if insufficient inventory (no silent modifications)

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG docker compose --profile agent up agents
```

### Check Configuration

```bash
docker compose exec agents python -m src.main check
```

Output shows:
- LLM provider and model
- API endpoints
- Checkpointer connection
- Available tools

### Trace Tool Calls

The agent logs all tool calls and results when `LOG_LEVEL=DEBUG`:

```
DEBUG - Tool call: search_orders(query="Alex Thompson", status="OUT_FOR_DELIVERY")
DEBUG - Tool result: [{'order_id': 'order:FM-1001', ...}]
```

### Inspect Conversation History

Connect to PostgreSQL to view stored checkpoints:

```bash
make shell-db

# List checkpoint tables
\dt checkpoints*

# View recent conversations
SELECT DISTINCT thread_id, MAX(checkpoint_id) as last_checkpoint
FROM checkpoints
GROUP BY thread_id
ORDER BY MAX(checkpoint_id) DESC
LIMIT 10;

# View messages for specific thread
SELECT checkpoint_id, channel, type
FROM checkpoints
WHERE thread_id = 'your-thread-id'
ORDER BY checkpoint_id;
```

### Reinitialize Checkpointer Tables

If you need to reset conversation memory:

```bash
make init-checkpointer
# or
docker compose exec agents python -m src.init_checkpointer
```

### Common Issues

**API Connection Errors:**
```bash
# Check if services are running
docker compose ps

# Test API connectivity
docker compose exec agents curl http://api:8080/health
docker compose exec agents curl http://opensearch:9200
```

**Missing LLM API Key:**
```bash
# Verify environment variable
docker compose exec agents env | grep API_KEY
```

**Checkpointer Errors:**
```bash
# Reinitialize checkpointer tables
docker compose exec agents python -m src.init_checkpointer

# Check PostgreSQL connection
docker compose exec agents python -c "from src.config import settings; print(settings.checkpointer_db_url)"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Input                                    │
│        "Find orders for Alex that are out for delivery"         │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│               PostgreSQL Checkpointer (Memory)                   │
│  • Load conversation history for thread_id                       │
│  • Restore previous context and messages                         │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Node (LLM)                              │
│  1. Understand request with full conversation context           │
│  2. Select appropriate tool(s)                                   │
│  3. Generate tool call parameters                                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ Tool calls
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Tool Node                                     │
│  Execute tools in parallel:                                      │
│  • search_orders("Alex", status="OUT_FOR_DELIVERY")             │
│  • search_inventory("milk")                                      │
│  • create_order(customer_id, store_id, line_items)              │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ Results
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Node (LLM)                              │
│  1. Process tool results                                         │
│  2. Decide: more tools needed OR respond to user                │
│  3. Generate final response                                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│               PostgreSQL Checkpointer (Memory)                   │
│  • Save updated conversation state                               │
│  • Persist for future requests in this thread                    │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Response                                      │
│  "I found 2 orders for customers named Alex that are out        │
│   for delivery: FM-1002 and FM-1013..."                         │
└─────────────────────────────────────────────────────────────────┘
```

## See Also

- [Architecture Guide](ARCHITECTURE.md) - Overall system architecture
- [API Reference](API_REFERENCE.md) - API endpoints used by agent tools
- [Operations Guide](OPERATIONS.md) - Service management
