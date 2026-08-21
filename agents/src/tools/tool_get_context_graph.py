"""Tool for retrieving the context graph schema."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings
from src.demo_label import alias_class, alias_column


@tool
async def get_context_graph() -> dict:
    """
    Get the complete context graph schema (classes and properties).

    Use this tool to understand what entities and relationships exist
    in the knowledge graph. Returns:
    - Classes: Entity types (Customer, Order, Store, Courier, etc.)

    Each class and property carries both names. Use `display_name` whenever you
    describe one to a person -- NEVER show `class_name` or `prop_name` to a user,
    not even in parentheses beside the display name. They are identifiers for
    write_triples, which validates against them, and nothing else.
    - Properties: Attributes and relationships for each class

    Returns:
        Dictionary with 'classes' and 'properties' lists
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.agent_api_base}/ontology/schema",
                timeout=10.0,
            )
            response.raise_for_status()
            schema = response.json()

            # Simplify for the agent.
            #
            # `class_name` and `prefix` are the fixed shape -- write_triples and
            # ontology validation both key on them, so they stay. `display_name`
            # is what this deployment calls the class, and without it the model
            # answers "what entity types exist?" by reading the wire schema
            # aloud: Courier, DeliveryTask, InventoryItem on a mortgage demo.
            classes_summary = [
                {
                    # display_name FIRST: the model narrates the first name it
                    # sees, and with class_name leading it answered "what entity
                    # types exist?" with Courier / DeliveryTask / InventoryItem.
                    "display_name": alias_class(c["class_name"]),
                    "class_name": c["class_name"],
                    "prefix": c["prefix"],
                    "description": c.get("description"),
                }
                for c in schema.get("classes", [])
            ]

            properties_summary = [
                {
                    "display_name": alias_column(p["prop_name"]),
                    "prop_name": p["prop_name"],
                    "domain": alias_class(p.get("domain_class_name") or ""),
                    "domain_class_name": p.get("domain_class_name"),
                    "range": p.get("range_class_name") or p["range_kind"],
                    "required": p["is_required"],
                }
                for p in schema.get("properties", [])
            ]

            return {
                "classes": classes_summary,
                "properties": properties_summary,
            }

        except httpx.HTTPError as e:
            return {"error": f"Failed to fetch context graph: {str(e)}"}
