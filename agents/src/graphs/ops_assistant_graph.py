"""FreshMart Operations Assistant - LangGraph implementation."""

import asyncio
import json
import operator
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.config import get_settings
from src.tools import (
    create_customer,
    create_order,
    fetch_order_context,
    get_context_graph,
    get_store_health,
    list_couriers,
    list_stores,
    manage_order_lines,
    search_inventory,
    search_orders,
    write_triples,
)


# State definition
class AgentState(TypedDict):
    """State passed through the agent graph."""

    messages: Annotated[list[BaseMessage], operator.add]
    iteration: int


# Tools
TOOLS = [
    create_customer,
    list_stores,
    list_couriers,
    search_inventory,
    create_order,
    manage_order_lines,
    search_orders,
    fetch_order_context,
    get_context_graph,
    get_store_health,
    write_triples,
]

# System prompt
SYSTEM_PROMPT = """You are an operations assistant for FreshMart's same-day grocery delivery service.

**Your Role**: You support FreshMart administrators and customer support agents by helping them manage:
- Customer orders and order modifications
- Inventory lookups across stores
- Order status updates and tracking
- Customer account creation and management

**You are NOT a customer-facing chatbot.** You assist FreshMart staff members who are helping customers or managing operations.

## MANDATORY FIRST STEP - DO NOT SKIP

**ALWAYS call get_context_graph() FIRST before ANY other tool.**

This is NON-NEGOTIABLE. Your very first tool call for every user request must be get_context_graph().
NEVER call search_orders, search_inventory, get_store_health, list_stores, or any other tool
before calling get_context_graph() first.

**Why this matters:** The ontology defines how your business entities connect:
- Orders link to Customers via `order_customer`
- Orders link to Stores via `order_store`
- OrderLines link to Orders via `orderline_order`
- Products link to Inventory via `inventoryitem_product`

Without this context, you cannot provide accurate, relationship-aware responses.

**CORRECT behavior:**
1. User asks anything → Call get_context_graph() FIRST
2. Review the schema to understand entity relationships
3. THEN call other tools as needed

**WRONG behavior (NEVER do this):**
- User asks "what's happening in my business?" → Calling get_store_health directly (WRONG!)
- User asks "find order 123" → Calling search_orders directly (WRONG!)

The ONLY acceptable first tool call is get_context_graph(). No exceptions.

## Common Tasks

**For Customer Support Agents:**
- Look up existing customer orders by order number or customer name
- Add or remove items from orders that customers call about
- Update order status (e.g., mark as delivered, cancel orders)
- Check product availability at specific store locations
- Create new orders on behalf of customers calling in

**For Store/Warehouse Staff:**
- Search for products in inventory
- Check stock levels across different stores
- Update order statuses as they're being picked/packed
- View delivery task assignments
- Check courier availability and workload by store

**For Administrators:**
- Create new customer accounts
- Bulk order lookups and status updates
- Inventory and operations reporting

## Available Tools

- create_customer: Create a new customer account (requires name)
- list_stores: List all stores with IDs and zone info (use FIRST when user mentions a store by name)
- list_couriers: List couriers with status and task info (can filter by store_id or status)
- search_inventory: Find products in a store's inventory (requires correct store_id)
- create_order: Create an order with confirmed items
- manage_order_lines: Add, update, or delete products from an existing order
- search_orders: Search existing orders
- fetch_order_context: Get full details for an order
- get_context_graph: Get the schema of all entity classes and properties
- get_store_health: Get real-time operational health metrics (capacity, inventory risk, pricing yield)
- write_triples: Update order status or other data

## CRITICAL: Ontology Validation Rules

**BEFORE using write_triples, you MUST:**
1. Call get_context_graph to retrieve the current schema
2. Verify that the predicate you want to use exists in the ontology properties list
3. Verify that the predicate is valid for the subject's entity class (check domain)
4. Only proceed with write_triples if the predicate exists and is valid

**If the predicate doesn't exist:**
- DO NOT attempt to write the triple
- Inform the user that the operation isn't supported by the ontology
- Suggest using the appropriate high-level tool instead (e.g., manage_order_lines for order modifications)

**Example validation flow:**
1. User asks to remove an item from an order
2. Call get_context_graph to check available predicates
3. See that there's no "remove_item" predicate
4. Use manage_order_lines with action="delete" instead

## Workflow Guidelines

**When searching inventory for a specific store:**
1. If user mentions a store by name (e.g., "Queens store", "Manhattan location"), call list_stores FIRST
2. Store IDs use abbreviated zone codes: MAN=Manhattan, BK=Brooklyn, QNS=Queens, BX=Bronx, SI=Staten Island
3. Use the correct store_id from list_stores in your search_inventory call
4. Example: "Queens store" → list_stores → find store:QNS-01 → search_inventory(store_id="store:QNS-01")

**When helping staff create or modify orders:**
1. Search for products by name or category using search_inventory
2. Present found items with live_price (dynamic pricing) and stock levels
3. For new orders: use create_order with the confirmed items
4. For existing orders: use manage_order_lines to add/update/delete items
5. Always use live_price (not base_price) from inventory search results - this includes all 7 dynamic pricing factors

**When looking up orders:**
1. Use search_orders to find orders by number, customer, or status
2. Use fetch_order_context to get complete order details
3. Present information clearly for the staff member

**When updating order status:**
1. First verify the current status using search_orders
2. Use write_triples to update order_status predicate
3. Common statuses: CREATED, PICKING, OUT_FOR_DELIVERY, DELIVERED, CANCELLED

**When checking store operational health:**
1. Use get_store_health to understand current operational state before making recommendations
2. Choose appropriate view based on question:
   - **summary**: "How are all stores doing?" or "What's our overall operational health?"
   - **quick_check**: "What's happening at Brooklyn store?" (requires store_id)
   - **capacity**: "Which stores are overloaded?" or "Can we handle more orders?"
   - **inventory_risk**: "Any inventory emergencies?" or "What products might stock out?"
3. Proactively check store health before creating large orders or during peak times
4. Include health metrics in your response to provide context for operational decisions
5. Use recommendations from the tool to advise staff on actions (e.g., close intake, surge pricing, replenishment)

**CRITICAL: Be precise with health status data:**
- **NEVER generalize** - Do not say "all stores are critical" unless literally every store has CRITICAL status
- **Count accurately** - If 7 stores are CRITICAL, 2 are STRAINED, and 1 is HEALTHY, report those exact counts
- **List specific stores** - When asked about least/most healthy, name the actual stores with their status and utilization %
- **Differentiate statuses** - CRITICAL, STRAINED, HEALTHY, and UNDERUTILIZED are distinct categories; do not conflate them
- Example good response: "3 stores are CRITICAL (Manhattan 1 at 155%, Bronx 1 at 147%, Brooklyn 1 at 112%), 2 are STRAINED, and 1 is HEALTHY"
- Example bad response: "All stores are at critical capacity" (when some are STRAINED or HEALTHY)

**Examples of when to use get_store_health:**
- Staff asks: "Can we accept a large catering order at Manhattan store?" → Check capacity first
- Staff reports: "Customer says their order is delayed" → Quick check the fulfilling store's health
- Manager asks: "What's the state of operations right now?" → Get summary view
- During order creation: If store shows CRITICAL capacity, warn staff before proceeding

## General Guidelines

- **Be professional**: You're assisting staff, not chatting with customers
- **Be precise**: Include order numbers, product IDs, and exact prices
- **Confirm changes**: Before modifying orders, confirm the change with the staff member
- Default store is store:BK-01 (FreshMart Brooklyn 1) unless specified
- Show prices in USD format ($X.XX)
- When working with products, always include current stock availability

## Pricing Guidelines

- **Always show live_price by default** - this is the current dynamic price that customers actually pay
- Only show base_price if specifically requested or when explaining pricing breakdowns
- **CRITICAL: Always fetch fresh pricing data** - Whenever a staff member asks about prices, product availability, or inventory:
  - ALWAYS call search_inventory to get current real-time data
  - NEVER rely on pricing information from conversation memory or previous tool calls
  - Prices are dynamic and can change based on stock levels, demand, and time
  - Even if you just searched for a product, search again if asked about its price
- The live_price includes 7 real-time pricing factors:
  1. **Zone adjustments**: Manhattan +15%, Brooklyn +5%, Queens baseline, Bronx -2%, Staten Island -5%
  2. **Perishable discounts**: -5% for items requiring refrigeration to move inventory faster
  3. **Local stock premiums**: +10% for ≤5 units at store, +3% for ≤15 units (store-specific scarcity)
  4. **Popularity adjustments**: Top 3 products +20%, ranks 4-10 +10%, others -10% (by sales volume)
  5. **Global scarcity premiums**: Top 3 scarcest +15%, ranks 4-10 +8% (total stock across all stores)
  6. **Demand multipliers**: Based on recent sales price trends and velocity
  7. **Demand premiums**: +5% for high-demand products above average sales
- If showing price comparisons, format as: "$5.75 (live price, base: $5.00)"
- When staff ask about pricing, you can explain which factors are affecting a specific product's price
"""


def get_llm():
    """Get the LLM based on available API keys."""
    settings = get_settings()

    if settings.anthropic_api_key:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.llm_model,
            anthropic_api_key=settings.anthropic_api_key,
        )
    elif settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.openai_api_key,
            temperature=1,  # Required for reasoning models (o1, o3)
        )
    else:
        raise ValueError("No LLM API key configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY")


async def agent_node(state: AgentState) -> AgentState:
    """Main agent node - reasons and decides on tool calls."""
    llm = get_llm()
    llm_with_tools = llm.bind_tools(TOOLS)

    # Build messages with system prompt, ensuring all messages have non-empty content
    # (Anthropic API requires non-empty content except for final assistant message)
    filtered_messages = []
    for msg in state["messages"]:
        if isinstance(msg, AIMessage):
            # For AI messages with tool calls but no content, add placeholder
            if not msg.content and hasattr(msg, "tool_calls") and msg.tool_calls:
                msg = AIMessage(
                    content="I'll use a tool to help with that.",
                    tool_calls=msg.tool_calls,
                )
        elif isinstance(msg, ToolMessage):
            # For tool messages with empty content (e.g., empty list from search),
            # convert to a string representation
            content = msg.content
            if not content or (isinstance(content, list) and len(content) == 0):
                msg = ToolMessage(
                    content="No results found.",
                    tool_call_id=msg.tool_call_id,
                )
            elif isinstance(content, list):
                # Ensure list content is converted to string for Anthropic
                msg = ToolMessage(
                    content=json.dumps(content),
                    tool_call_id=msg.tool_call_id,
                )
        filtered_messages.append(msg)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + filtered_messages

    # Get response
    response = await llm_with_tools.ainvoke(messages)

    return {
        "messages": [response],
        "iteration": state["iteration"] + 1,
    }


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """Decide whether to continue with tools or end."""
    # Check iteration limit
    if state["iteration"] > 10:
        return "end"

    # Check for tool calls in last message
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"

    return "end"


def create_workflow() -> StateGraph:
    """Create the agent workflow (without compiling)."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", ToolNode(TOOLS))

    # Set entry point
    workflow.set_entry_point("agent")

    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END,
        },
    )

    # Loop back after tools
    workflow.add_edge("tools", "agent")

    return workflow


# Cache for compiled graph and checkpointer to avoid recreation on every call
_cached_checkpointer = None
_cached_graph = None
_checkpointer_context = None
_init_lock = asyncio.Lock()


async def _get_graph_and_checkpointer():
    """Get or create the compiled graph with checkpointer (cached for reuse)."""
    global _cached_checkpointer, _cached_graph, _checkpointer_context

    # Thread-safe initialization with lock
    async with _init_lock:
        if _cached_graph is None:
            settings = get_settings()
            try:
                # from_conn_string returns a context manager, need to enter it
                _checkpointer_context = AsyncPostgresSaver.from_conn_string(settings.pg_dsn)
                _cached_checkpointer = await _checkpointer_context.__aenter__()

                workflow = create_workflow()
                _cached_graph = workflow.compile(checkpointer=_cached_checkpointer)
            except Exception:
                # Clean up partial state on initialization failure
                if _checkpointer_context and _cached_checkpointer:
                    try:
                        await _checkpointer_context.__aexit__(None, None, None)
                    except Exception:
                        pass  # Best effort cleanup
                _cached_graph = None
                _cached_checkpointer = None
                _checkpointer_context = None
                raise

    return _cached_graph


async def cleanup_graph_resources():
    """
    Clean up cached graph resources and exit the checkpointer context.

    Call this on application shutdown to properly close database connections.
    """
    global _cached_checkpointer, _cached_graph, _checkpointer_context

    async with _init_lock:
        if _checkpointer_context and _cached_checkpointer:
            try:
                await _checkpointer_context.__aexit__(None, None, None)
            except Exception:
                pass  # Best effort cleanup

        _cached_graph = None
        _cached_checkpointer = None
        _checkpointer_context = None


async def _reset_cached_graph():
    """Reset the cached graph and checkpointer to force reconnection."""
    global _cached_checkpointer, _cached_graph, _checkpointer_context

    async with _init_lock:
        if _checkpointer_context and _cached_checkpointer:
            try:
                await _checkpointer_context.__aexit__(None, None, None)
            except Exception:
                pass  # Best effort cleanup

        _cached_graph = None
        _cached_checkpointer = None
        _checkpointer_context = None


async def run_assistant(user_message: str, thread_id: str = "default", stream_events: bool = False):
    """
    Run the ops assistant with a user message.

    Args:
        user_message: Natural language request
        thread_id: Conversation thread ID for memory persistence (default: "default")
        stream_events: If True, yields status updates during execution

    Yields:
        tuple[str, Any]: Status updates as (event_type, data) tuples where event_type is one of:
            - "tool_call": {"name": str, "args": dict} - Agent is calling a tool
            - "tool_result": {"content": str} - Tool execution completed
            - "thinking": {"content": str} - Extended thinking content (if available)
            - "error": {"message": str} - An error occurred during execution
            - "response": str - Final response text (always emitted last)
    """
    # Use cached graph (avoids recreating workflow and reconnecting to postgres each call)
    # If connection is closed, reset and retry once
    try:
        graph = await _get_graph_and_checkpointer()
    except Exception as e:
        if "connection is closed" in str(e).lower():
            await _reset_cached_graph()
            graph = await _get_graph_and_checkpointer()
        else:
            raise

    # Config with thread_id for conversation memory
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: AgentState = {
        "messages": [HumanMessage(content=user_message)],
        "iteration": 0,
    }

    if stream_events:
        # Stream events to show what's happening
        final_response = None
        try:
            async for event in graph.astream(initial_state, config):
                # Agent node processing
                if "agent" in event:
                    agent_data = event["agent"]
                    if "messages" in agent_data and agent_data["messages"]:
                        last_msg = agent_data["messages"][-1]
                        if isinstance(last_msg, AIMessage):
                            if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                                # Agent decided to call tools
                                for tool_call in last_msg.tool_calls:
                                    # Handle both dict and object formats
                                    tool_name = getattr(tool_call, 'name', tool_call.get("name", "unknown") if isinstance(tool_call, dict) else "unknown")
                                    tool_args = getattr(tool_call, 'args', tool_call.get("args", {}) if isinstance(tool_call, dict) else {})
                                    yield ("tool_call", {"name": tool_name, "args": tool_args})
                            elif last_msg.content:
                                # Agent produced a response
                                final_response = last_msg.content

                # Tool node processing
                elif "tools" in event:
                    tools_data = event["tools"]
                    if "messages" in tools_data and tools_data["messages"]:
                        for msg in tools_data["messages"]:
                            if isinstance(msg, ToolMessage):
                                # Extract tool name from the message with truncation indicator
                                content_str = str(msg.content)
                                if len(content_str) > 150:
                                    content_preview = content_str[:150] + "..."
                                else:
                                    content_preview = content_str
                                yield ("tool_result", {"content": content_preview})

            # Yield final response
            if final_response:
                yield ("response", final_response)
            else:
                yield ("response", "I couldn't complete that request.")
        except Exception as e:
            error_msg = str(e)
            # If connection closed, reset cache and inform user to retry
            if "connection is closed" in error_msg.lower():
                await _reset_cached_graph()
                yield ("error", {"message": "Database connection was reset. Please try again."})
                yield ("response", "The database connection was reset. Please try your request again.")
            # Provide helpful message for common configuration errors
            elif "API key" in error_msg or "api_key" in error_msg.lower():
                yield ("error", {"message": error_msg})
                yield ("response", f"Configuration error: {error_msg}\n\nAdd ANTHROPIC_API_KEY or OPENAI_API_KEY to your .env file, then restart the agents container.")
            else:
                yield ("error", {"message": error_msg})
                yield ("response", f"An error occurred: {error_msg}")
    else:
        # Non-streaming: just get result and yield final response
        try:
            final_state = await graph.ainvoke(initial_state, config)

            # Get final AI response
            response = None
            for msg in reversed(final_state["messages"]):
                if isinstance(msg, AIMessage) and msg.content:
                    response = msg.content
                    break

            if response:
                yield ("response", response)
            else:
                yield ("response", "I couldn't complete that request.")
        except Exception as e:
            error_msg = str(e)
            # If connection closed, reset cache and inform user to retry
            if "connection is closed" in error_msg.lower():
                await _reset_cached_graph()
                yield ("error", {"message": "Database connection was reset. Please try again."})
                yield ("response", "The database connection was reset. Please try your request again.")
            # Provide helpful message for common configuration errors
            elif "API key" in error_msg or "api_key" in error_msg.lower():
                yield ("error", {"message": error_msg})
                yield ("response", f"Configuration error: {error_msg}\n\nAdd ANTHROPIC_API_KEY or OPENAI_API_KEY to your .env file, then restart the agents container.")
            else:
                yield ("error", {"message": error_msg})
                yield ("response", f"An error occurred: {error_msg}")
