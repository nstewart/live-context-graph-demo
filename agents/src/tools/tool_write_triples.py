"""Tool for writing triples to the knowledge graph."""

from typing import Literal

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def write_triples(
    triples: list[dict],
    validate_ontology: bool = True,
) -> list[dict]:
    """
    Write one or more triples to the FreshMart knowledge graph.

    **IMPORTANT: You MUST call get_context_graph BEFORE using this tool to verify
    that the predicates you want to use exist in the ontology schema.**

    Use this tool to:
    - Update order status (e.g., mark as DELIVERED)
    - Assign couriers to tasks
    - Create new entities

    Each triple must have:
    - subject_id: Entity ID (e.g., "order:FM-1001", "task:T1001")
    - predicate: Property name (e.g., "order_status", "assigned_to")
    - object_value: The value to set
    - object_type: One of "string", "int", "float", "bool", "timestamp", "entity_ref"

    **DO NOT use predicates that don't exist in the ontology.**
    For operations like removing order items, use manage_order_lines instead.

    Args:
        triples: List of triples to create/update
        validate_ontology: Whether to validate against ontology (default True)

    Returns:
        List of created/updated triples or error details

    Example:
        # First check ontology:
        ontology = get_context_graph()
        # Verify "order_status" exists in properties
        # Then write:
        write_triples([{
            "subject_id": "order:FM-1001",
            "predicate": "order_status",
            "object_value": "DELIVERED",
            "object_type": "string"
        }])
    """
    settings = get_settings()
    results = []

    # Fetch ontology for client-side validation if requested
    ontology_properties = None
    if validate_ontology:
        async with httpx.AsyncClient() as client:
            try:
                ont_response = await client.get(
                    f"{settings.agent_api_base}/ontology/schema",
                    timeout=10.0,
                )
                if ont_response.status_code == 200:
                    ontology_schema = ont_response.json()
                    ontology_properties = {
                        p["prop_name"]: p for p in ontology_schema.get("properties", [])
                    }
            except Exception:
                # If we can't fetch ontology, let server-side validation handle it
                pass

    async with httpx.AsyncClient() as client:
        for triple in triples:
            try:
                # Validate triple structure
                required_fields = ["subject_id", "predicate", "object_value", "object_type"]
                missing = [f for f in required_fields if f not in triple]
                if missing:
                    results.append({
                        "error": f"Missing required fields: {missing}",
                        "triple": triple,
                    })
                    continue

                # Client-side ontology validation
                if ontology_properties and triple["predicate"] not in ontology_properties:
                    available_predicates = list(ontology_properties.keys())
                    results.append({
                        "success": False,
                        "error": f"Predicate '{triple['predicate']}' does not exist in ontology",
                        "suggestion": "Check get_context_graph() for available predicates, or use a high-level tool like manage_order_lines",
                        "available_predicates_sample": available_predicates[:10],  # Show first 10
                        "triple": triple,
                    })
                    continue

                # Check if triple with same subject+predicate exists (for single-valued predicates)
                existing_response = await client.get(
                    f"{settings.agent_api_base}/triples",
                    params={
                        "subject_id": triple["subject_id"],
                        "predicate": triple["predicate"],
                    },
                    timeout=10.0,
                )

                if existing_response.status_code == 200:
                    existing_triples = existing_response.json()
                    if existing_triples:
                        # Update existing triple instead of creating new one
                        existing_id = existing_triples[0]["id"]
                        response = await client.patch(
                            f"{settings.agent_api_base}/triples/{existing_id}",
                            json={"object_value": triple["object_value"]},
                            timeout=10.0,
                        )
                        if response.status_code == 200:
                            results.append({
                                "success": True,
                                "action": "updated",
                                "triple": response.json(),
                            })
                            continue
                        # If update failed, fall through to create

                # Create new triple
                response = await client.post(
                    f"{settings.agent_api_base}/triples",
                    json=triple,
                    params={"validate": validate_ontology},
                    timeout=10.0,
                )

                if response.status_code == 201:
                    results.append({
                        "success": True,
                        "action": "created",
                        "triple": response.json(),
                    })
                elif response.status_code == 400:
                    error_detail = response.json().get("detail", {})
                    results.append({
                        "success": False,
                        "error": "Validation failed",
                        "details": error_detail,
                        "triple": triple,
                    })
                else:
                    results.append({
                        "success": False,
                        "error": f"API error: {response.status_code}",
                        "triple": triple,
                    })

            except httpx.HTTPError as e:
                results.append({
                    "success": False,
                    "error": f"Request failed: {str(e)}",
                    "triple": triple,
                })

    return results
