"""Tool for creating customer accounts."""

from typing import Optional
from uuid import uuid4

import httpx
from langchain_core.tools import tool

from src.config import get_settings


@tool
async def create_customer(
    name: str,
    email: Optional[str] = None,
    address: Optional[str] = None,
    home_store_id: str = "store:BK-01",
) -> dict:
    """
    Create a new customer account in FreshMart.

    Use this tool to register new customers before they place their first order.

    Args:
        name: Customer's full name (required)
        email: Customer's email address (optional)
        address: Customer's delivery address (optional)
        home_store_id: Customer's preferred store (default: store:BK-01)

    Returns:
        Customer information including the generated customer_id

    Example:
        create_customer(
            name="John Doe",
            email="john@email.com",
            address="123 Main St, Brooklyn, NY"
        )
    """
    settings = get_settings()

    # Generate unique customer ID
    customer_id = f"customer:{uuid4().hex[:8]}"

    # Build triples for customer
    triples = [
        {
            "subject_id": customer_id,
            "predicate": "customer_name",
            "object_value": name,
            "object_type": "string",
        },
        {
            "subject_id": customer_id,
            "predicate": "home_store",
            "object_value": home_store_id,
            "object_type": "entity_ref",
        },
    ]

    if email:
        triples.append(
            {
                "subject_id": customer_id,
                "predicate": "customer_email",
                "object_value": email,
                "object_type": "string",
            }
        )

    # Always add an address - use provided or create dummy
    if not address:
        address = "123 Main St, Brooklyn, NY 11201"

    triples.append(
        {
            "subject_id": customer_id,
            "predicate": "customer_address",
            "object_value": address,
            "object_type": "string",
        }
    )

    # Create customer triples via batch API
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.agent_api_base}/triples/batch",
                json=triples,
                params={"validate": True},
                timeout=10.0,
            )
            response.raise_for_status()

            return {
                "success": True,
                "customer_id": customer_id,
                "name": name,
                "email": email,
                "address": address,
                "home_store_id": home_store_id,
            }

        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"Failed to create customer: {str(e)}",
            }
