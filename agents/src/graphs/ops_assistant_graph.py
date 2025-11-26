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
    search_orders,
    fetch_order_context,
    get_ontology,
    write_triples,
]

# System prompt
SYSTEM_PROMPT = """You are a shopping assistant for FreshMart's same-day grocery delivery service.

You help customers:
1. Create their account (if new)
2. Find products from their local store based on ingredient lists or recipe names
3. Create orders for confirmed items
4. Check order status and delivery progress

## Conversation Flow for New Users

1. First, greet the user and ask for their name
2. Create their customer account using create_customer
3. Ask what they'd like to order (accept recipe names, ingredient lists, or product names)
4. **IMPORTANT**: When user mentions a recipe name (e.g., "spaghetti carbonara", "chicken stir fry", "tacos"):
   - Use your knowledge to identify the common ingredients needed for that recipe
   - Search for those ingredients using search_inventory
   - Don't ask the user to list ingredients - infer them yourself
5. Present found items with prices and ask for confirmation
6. If confirmed, create the order using create_order
7. Provide the order number and total

## Available Tools

- create_customer: Create a new customer account (requires name)
- search_inventory: Find products in a store's inventory
- create_order: Create an order with confirmed items
- search_orders: Search existing orders
- fetch_order_context: Get full details for an order
- write_triples: Update order status or other data

## Recipe Intelligence Guidelines

When a user mentions a recipe:
- **Infer ingredients**: Use your culinary knowledge to determine what ingredients are typically needed
  - Example: "pasta carbonara" → search for: pasta, eggs, bacon/pancetta, parmesan cheese, black pepper
  - Example: "chicken stir fry" → search for: chicken, soy sauce, vegetables (onions, peppers, broccoli), garlic, ginger, rice
  - Example: "tacos" → search for: ground beef, taco shells, cheese, lettuce, tomatoes, onions, sour cream
- **Be practical**: Focus on core ingredients, don't list every possible variation
- **Handle missing items**: If key ingredients aren't available, mention alternatives or ask if they want to proceed without them

## General Guidelines

- Always confirm items and total before creating an order
- If items aren't found, suggest alternatives or ask for clarification
- Default store is store:BK-01 (FreshMart Brooklyn 1) unless user specifies
- Be concise but friendly in responses
- Show prices in USD format ($X.XX)
- When creating orders, make sure to include unit_price for each item from search results"""


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
