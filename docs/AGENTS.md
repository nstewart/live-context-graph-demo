# Agent Guide

This document describes the LangGraph-powered operations assistant.

## Overview

The FreshMart Operations Assistant is an AI agent that helps operations staff:
- Search for orders by natural language
- View order details and status
- Update order status
- Query the knowledge graph structure

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User Input                                    │
│        "Find orders for Alex that are out for delivery"         │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Node (LLM)                              │
│  1. Understand request                                           │
│  2. Select appropriate tool(s)                                   │
│  3. Generate tool call parameters                                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ Tool calls
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Tool Node                                     │
│  Execute tools in parallel:                                      │
│  • search_orders("Alex", status="OUT_FOR_DELIVERY")             │
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
│                    Response                                      │
│  "I found 2 orders for customers named Alex that are out        │
│   for delivery: FM-1002 and FM-1013..."                         │
└─────────────────────────────────────────────────────────────────┘
```

## Tools

### search_orders

Search for orders using natural language via OpenSearch.

**Parameters**:
- `query` (str): Search query (customer name, address, order number)
- `status` (str, optional): Filter by order status
- `limit` (int): Max results (default 10)

**Example**:
```python
results = await search_orders(
    query="Alex Thompson",
    status="OUT_FOR_DELIVERY",
    limit=10
)
```

### fetch_order_context

Get detailed information for specific orders.

**Parameters**:
- `order_ids` (list[str]): Order IDs to fetch

**Example**:
```python
orders = await fetch_order_context(["order:FM-1001", "order:FM-1002"])
```

### get_ontology

Retrieve the knowledge graph schema.

**Returns**:
- Classes: Entity types with prefixes
- Properties: Attributes and relationships

**Example**:
```python
schema = await get_ontology()
# Returns classes and properties
```

### write_triples

Create or update data in the knowledge graph. If a triple already exists with the same subject and predicate, it will be updated rather than creating a duplicate.

**Parameters**:
- `triples` (list[dict]): Triples to write
- `validate_ontology` (bool): Validate against ontology (default True)

**Example**:
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

## Using the Agent

### CLI - Interactive Mode

```bash
# Start the agent service
docker-compose --profile agent up -d

# Start interactive chat
docker-compose exec -it agents python -m src.main chat

# Example conversation
You: Show all orders that are out for delivery
Assistant: I found 4 orders currently out for delivery...

You: What's the status of order FM-1002?
Assistant: Order FM-1002 is OUT_FOR_DELIVERY...

You: Mark that order as delivered
Assistant: I'll update order FM-1002 to DELIVERED...
```

### CLI - Single Command

```bash
# Run a single query
docker-compose exec agents python -m src.main chat "Show all orders for customer Alex Thompson"
```

### HTTP API

The agent service exposes an HTTP API on port 8081:

```bash
# Health check
curl http://localhost:8081/health

# Chat with the agent
curl -X POST http://localhost:8081/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show all OUT_FOR_DELIVERY orders"}'
```

### Programmatic Usage

```python
from src.graphs.ops_assistant_graph import run_assistant

response = await run_assistant("Find orders at risk of missing their delivery window")
print(response)
```

## Example Queries

### Order Search

```
"Find all orders for customer Alex"
"Show orders at store BK-01"
"What orders are currently being picked?"
"List orders with delivery window ending soon"
```

### Order Details

```
"Show me details for order FM-1001"
"What's the status of Alex's order?"
"Who is delivering order FM-1002?"
```

### Status Updates

```
"Mark order FM-1001 as delivered"
"Cancel order FM-1004"
"Update FM-1003 to out for delivery"
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
    search_orders,
    fetch_order_context,
    get_ontology,
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

Set one of these environment variables:

```bash
# For Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
OPENAI_API_KEY=sk-...
```

### Model Selection

Edit `config.py` to change the default model:

```python
llm_model: str = "claude-sonnet-4-20250514"  # Anthropic (default)
# or
llm_model: str = "gpt-4-turbo"  # OpenAI
```

## Safety & Limits

The agent includes safety measures:

1. **Iteration Limit**: Max 10 tool calls per request
2. **Validation**: Triple writes validated against ontology
3. **Confirmation**: Destructive actions require explicit confirmation
4. **Timeouts**: HTTP requests timeout after 10 seconds

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG docker-compose --profile agent up agents
```

### Check Configuration

```bash
docker-compose exec agents python -m src.main check
```

### Trace Tool Calls

The agent logs all tool calls and results when `LOG_LEVEL=DEBUG`.
