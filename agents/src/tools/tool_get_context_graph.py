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

    `name` is what this business calls the class or property and is the only one
    to show a user. `prefix` and `prop_name` are identifiers -- use them to build
    subject ids and to pass predicates to write_triples, and never show them.
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
            # `class_name` is deliberately ABSENT. Nothing in the agent consumes
            # it -- write_triples validates server-side from subject_id and
            # predicate, and the model builds subject ids from `prefix` -- so its
            # only effect was that the model read it aloud. Asked what entity
            # types exist it answered "Courier, DeliveryTask, InventoryItem" on a
            # mortgage demo, and it kept doing so through a display_name beside
            # it, display_name first, and an explicit instruction not to. The
            # word cannot be spoken if it is not sent.
            #
            # `prefix` and `prop_name` stay: those the model genuinely needs to
            # pass back, and both are identifier-shaped rather than prose.
            classes_summary = [
                {
                    "name": alias_class(c["class_name"]),
                    "prefix": c["prefix"],
                    "description": c.get("description"),
                }
                for c in schema.get("classes", [])
            ]

            properties_summary = [
                {
                    "name": alias_column(p["prop_name"]),
                    "prop_name": p["prop_name"],
                    "domain": alias_class(p.get("domain_class_name") or ""),
                    # range_class_name is a class name too, so it needs the
                    # same treatment; range_kind ("string", "int") is a type.
                    "range": (
                        alias_class(p["range_class_name"])
                        if p.get("range_class_name")
                        else p["range_kind"]
                    ),
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
