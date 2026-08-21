"""Tool for resolving a person's name to the customer subject id."""

import httpx
from langchain_core.tools import tool

from src.config import get_settings
from src.demo_label import alias_payload


@tool
async def find_customer(name: str) -> list[dict]:
    """
    Resolve a person's NAME to their real customer subject id.

    Call this whenever the user names a person in plain language instead of
    giving an id. Subject ids are opaque (customer:00002); they are never
    derived from the name, so an id you construct yourself will not exist and any
    record referencing it loses its link to the person.

    Args:
        name: Full or partial name, case-insensitive. "spence", "James Spence"
            and "james" all match "James Spence".

    Returns:
        Matches, best first, each with:
        - customer_id: the real subject id to pass to other tools
        - customer_name: the stored name
        - customer_email, customer_address: for disambiguating duplicates
        On no match, a single {"error": ..., "hint": ...} describing what to do.

    Example workflow:
        1. User asks: "open a case for James Spence"
        2. find_customer(name="James Spence") -> customer:00002
        3. create_order(customer_id="customer:00002", ...)

    If there is no match, the person is not on file: use create_customer to add
    them, then pass the id it returns. Never invent an id, and never guess
    between several matches -- ask the user which one they mean.
    """
    settings = get_settings()
    needle = (name or "").strip().lower()
    if not needle:
        return [{"error": "name is required"}]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{settings.agent_api_base}/freshmart/customers",
                timeout=10.0,
            )
            response.raise_for_status()
            customers = response.json()
        except Exception as e:  # noqa: BLE001 - surfaced to the model as text
            return [{"error": f"Failed to look up the name: {str(e)}"}]

    def rank(record: dict) -> int:
        stored = (record.get("customer_name") or "").lower()
        if stored == needle:
            return 0
        if stored.startswith(needle):
            return 1
        if needle in stored:
            return 2
        # every whitespace-separated part matched, in any order ("spence james")
        if all(part in stored for part in needle.split()):
            return 3
        return 99

    matches = sorted(
        ((rank(c), c) for c in customers if rank(c) < 99),
        key=lambda pair: (pair[0], pair[1].get("customer_name") or ""),
    )

    if not matches:
        return [
            {
                "error": f"No customer on file matches '{name}'.",
                "hint": (
                    "Use create_customer to add them, then pass the id it "
                    "returns. Do not construct an id from the name."
                ),
            }
        ]

    return alias_payload([
        {
            "customer_id": c.get("customer_id"),
            "customer_name": c.get("customer_name"),
            "customer_email": c.get("customer_email"),
            "customer_address": c.get("customer_address"),
        }
        for _, c in matches[:10]
    ])
