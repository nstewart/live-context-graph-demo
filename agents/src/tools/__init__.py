# Agent tools
from src.tools.tool_create_customer import create_customer
from src.tools.tool_create_order import create_order
from src.tools.tool_fetch_order_context import fetch_order_context
from src.tools.tool_find_customer import find_customer
from src.tools.tool_get_context_graph import get_context_graph
from src.tools.tool_get_store_health import get_store_health
from src.tools.tool_list_couriers import list_couriers
from src.tools.tool_list_stores import list_stores
from src.tools.tool_manage_order_lines import manage_order_lines
from src.tools.tool_search_inventory import search_inventory
from src.tools.tool_search_orders import search_orders
from src.tools.tool_write_triples import write_triples


# LangChain ships each tool's docstring to the model as its description, so that
# prose is copy the customer hears back -- "List all stores with IDs" teaches the
# model to say "stores" no matter how well the payload is aliased. Rewrite the
# nouns from the active label here, once, rather than in twelve docstrings.
# Identifiers inside them (search_orders, store_id, order:FM-1001, DELIVERED)
# are protected; see localize_doc.
from src.demo_label import localize_doc

for _tool in (
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
):
    _tool.description = localize_doc(_tool.description) or _tool.description

__all__ = [
    "create_customer",
    "create_order",
    "fetch_order_context",
    "find_customer",
    "get_context_graph",
    "get_store_health",
    "list_couriers",
    "list_stores",
    "manage_order_lines",
    "search_inventory",
    "search_orders",
    "write_triples",
]
