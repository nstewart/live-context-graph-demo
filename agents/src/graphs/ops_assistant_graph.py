"""Operations assistant - LangGraph implementation.

The persona, vocabulary, and system prompt are label-driven; see labels/."""

import asyncio
import json
import operator
from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.config import get_settings
from src.demo_label import system_prompt
from src.tools import (
    create_customer,
    create_order,
    fetch_order_context,
    find_customer,
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
    find_customer,
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

# System prompt. Label-driven: the persona and all domain vocabulary live in
# labels/<name>.yaml so the assistant speaks the customer's language. The tool
# set, graph structure, and ontology are NOT label-driven.
SYSTEM_PROMPT = system_prompt()


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
