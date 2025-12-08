"""Customer creation scenarios."""

import logging
import random
from typing import Any

from loadgen.api_client import FreshMartAPIClient
from loadgen.data_generators import DataGenerator

logger = logging.getLogger(__name__)


class CustomerScenario:
    """Execute customer creation scenarios."""

    def __init__(
        self,
        api_client: FreshMartAPIClient,
        data_generator: DataGenerator,
    ):
        """Initialize customer scenario.

        Args:
            api_client: FreshMart API client
            data_generator: Data generator instance
        """
        self.api_client = api_client
        self.data_generator = data_generator
        self.stores: list[dict[str, Any]] = []

    async def initialize(self):
        """Initialize scenario by fetching required data."""
        logger.info("Initializing customer scenario...")
        self.stores = await self.api_client.get_stores(limit=100)
        logger.info(f"Loaded {len(self.stores)} stores")

    async def execute(self) -> dict[str, Any]:
        """Execute customer creation scenario.

        Returns:
            Result dictionary with customer details
        """
        if not self.stores:
            raise RuntimeError("Scenario not initialized. Call initialize() first.")

        # Generate customer details
        customer_id = self.data_generator.generate_customer_id()
        name = self.data_generator.generate_customer_name()
        email = self.data_generator.generate_customer_email(name)

        # Select random home store
        home_store = random.choice(self.stores)

        # Generate address in same zone as store
        # Extract zone from store name if possible, otherwise random
        zone = None
        store_name = home_store.get("store_name", "")
        for z in ["Manhattan", "Brooklyn", "Queens"]:
            if z in store_name:
                zone = z
                break

        address = self.data_generator.generate_address(zone)

        try:
            # Create customer via API
            result = await self.api_client.create_customer(
                customer_id=customer_id,
                name=name,
                email=email,
                address=address,
                home_store_id=home_store["store_id"],
            )

            logger.debug(
                f"Created customer {customer_id} ({name}) with home store "
                f"{home_store['store_name']}"
            )

            return {
                "success": True,
                "customer_id": customer_id,
                "name": name,
                "email": email,
                "home_store": home_store["store_name"],
            }

        except Exception as e:
            logger.error(f"Failed to create customer {customer_id}: {e}")
            return {
                "success": False,
                "error": str(e),
            }
