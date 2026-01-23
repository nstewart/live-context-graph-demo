"""Tool for retrieving the context graph schema."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def get_context_graph() -> dict:
    """
    Get the complete context graph schema (classes and properties).

    Use this tool to understand what entities and relationships exist
    in the FreshMart knowledge graph. Returns:
    - Classes: Entity types (Customer, Order, Store, Courier, etc.)
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

            # Simplify for the agent
            classes_summary = [
                {
                    "class_name": c["class_name"],
                    "prefix": c["prefix"],
                    "description": c.get("description"),
                }
                for c in schema.get("classes", [])
            ]

            properties_summary = [
                {
                    "prop_name": p["prop_name"],
                    "domain": p.get("domain_class_name"),
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
