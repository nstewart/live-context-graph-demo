"""Inventory update scenarios."""

import logging
import random
from typing import Any

from loadgen.api_client import FreshMartAPIClient
from loadgen.data_generators import DataGenerator

logger = logging.getLogger(__name__)


class InventoryScenario:
    """Execute inventory update scenarios."""

    def __init__(
        self,
        api_client: FreshMartAPIClient,
        data_generator: DataGenerator,
    ):
        """Initialize inventory scenario.

        Args:
            api_client: FreshMart API client
            data_generator: Data generator instance
        """
        self.api_client = api_client
        self.data_generator = data_generator
        self.stores: list[dict[str, Any]] = []
        self.products: list[dict[str, Any]] = []

    async def initialize(self):
        """Initialize scenario by fetching required data."""
        logger.info("Initializing inventory scenario...")
        self.stores = await self.api_client.get_stores(limit=100)
        self.products = await self.api_client.get_products(limit=1000)
        logger.info(f"Loaded {len(self.stores)} stores, {len(self.products)} products")

    async def execute(self) -> dict[str, Any]:
        """Execute inventory update scenario.

        Returns:
            Result dictionary with update details
        """
        if not self.stores or not self.products:
            raise RuntimeError("Scenario not initialized. Call initialize() first.")

        # Select random store and product
        store = random.choice(self.stores)
        product = random.choice(self.products)

        # Determine if this is a replenishment or adjustment
        is_replenishment = random.random() < 0.3  # 30% chance of replenishment

        try:
            # For this demo, we'll assume current quantity
            # In a real implementation, we'd fetch current inventory
            current_quantity = random.randint(0, 50)

            new_quantity = self.data_generator.generate_inventory_adjustment(
                current_quantity, is_replenishment
            )

            # Update inventory via API
            await self.api_client.update_inventory(
                store_id=store["store_id"],
                product_id=product["product_id"],
                new_quantity=new_quantity,
            )

            action = "replenishment" if is_replenishment else "adjustment"
            logger.debug(
                f"Updated inventory at {store['store_name']}: "
                f"{product['product_name']} = {new_quantity} ({action})"
            )

            return {
                "success": True,
                "store_name": store["store_name"],
                "product_name": product["product_name"],
                "old_quantity": current_quantity,
                "new_quantity": new_quantity,
                "action": action,
            }

        except Exception as e:
            logger.error(f"Failed to update inventory: {e}")
            return {
                "success": False,
                "error": str(e),
            }
