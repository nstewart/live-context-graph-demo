"""FreshMart Operations Assistant - LangGraph implementation."""

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
    get_ontology,
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
    search_inventory,
    create_order,
    manage_order_lines,
    search_orders,
    fetch_order_context,
    get_ontology,
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

**For Administrators:**
- Create new customer accounts
- Bulk order lookups and status updates
- Inventory and operations reporting

## Available Tools

- create_customer: Create a new customer account (requires name)
- search_inventory: Find products in a store's inventory
- create_order: Create an order with confirmed items
- manage_order_lines: Add, update, or delete products from an existing order
- search_orders: Search existing orders
- fetch_order_context: Get full details for an order
- get_ontology: Get the schema of all entity classes and properties
- write_triples: Update order status or other data

## CRITICAL: Ontology Validation Rules

**BEFORE using write_triples, you MUST:**
1. Call get_ontology to retrieve the current schema
2. Verify that the predicate you want to use exists in the ontology properties list
3. Verify that the predicate is valid for the subject's entity class (check domain)
4. Only proceed with write_triples if the predicate exists and is valid

**If the predicate doesn't exist:**
- DO NOT attempt to write the triple
- Inform the user that the operation isn't supported by the ontology
- Suggest using the appropriate high-level tool instead (e.g., manage_order_lines for order modifications)

**Example validation flow:**
1. User asks to remove an item from an order
2. Call get_ontology to check available predicates
3. See that there's no "remove_item" predicate
4. Use manage_order_lines with action="delete" instead

## Workflow Guidelines

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


async def run_assistant(user_message: str, thread_id: str = "default") -> str:
    """
    Run the ops assistant with a user message.

    Args:
        user_message: Natural language request
        thread_id: Conversation thread ID for memory persistence (default: "default")

    Returns:
        Assistant's final response
    """
    settings = get_settings()

    # Use async checkpointer as a context manager
    async with AsyncPostgresSaver.from_conn_string(settings.pg_dsn) as checkpointer:
        # Create workflow and compile with checkpointer
        workflow = create_workflow()
        graph = workflow.compile(checkpointer=checkpointer)

        # Config with thread_id for conversation memory
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: AgentState = {
            "messages": [HumanMessage(content=user_message)],
            "iteration": 0,
        }

        final_state = await graph.ainvoke(initial_state, config)

        # Get final AI response
        for msg in reversed(final_state["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                return msg.content

        return "I couldn't complete that request."
