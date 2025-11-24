"""FreshMart Operations Assistant - LangGraph implementation."""

import json
import operator
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.config import get_settings
from src.tools import fetch_order_context, get_ontology, search_orders, write_triples


# State definition
class AgentState(TypedDict):
    """State passed through the agent graph."""

    messages: Annotated[list[BaseMessage], operator.add]
    iteration: int


# Tools
TOOLS = [
    search_orders,
    fetch_order_context,
    get_ontology,
    write_triples,
]

# System prompt
SYSTEM_PROMPT = """You are an operations assistant for FreshMart's same-day grocery delivery service.

You help operations staff:
1. Find and inspect orders by customer name, address, or order number
2. Check order status and delivery progress
3. Update order status (mark as DELIVERED, CANCELLED, etc.)
4. View the knowledge graph structure (ontology)

Available tools:
- search_orders: Search for orders using natural language (customer name, address, order number)
- fetch_order_context: Get full details for specific order IDs
- get_ontology: View the knowledge graph schema
- write_triples: Update order status or other data

When updating order status, use these valid statuses:
- CREATED: New order placed
- PICKING: Items being picked in store
- OUT_FOR_DELIVERY: Order dispatched with courier
- DELIVERED: Successfully delivered
- CANCELLED: Order cancelled

Always confirm what you're about to do before making changes.
After any search, summarize results clearly and offer next actions."""


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
