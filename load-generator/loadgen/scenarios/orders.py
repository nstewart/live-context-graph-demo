"""Order creation scenarios."""

import logging
import random
from typing import Any

from loadgen.api_client import FreshMartAPIClient
from loadgen.data_generators import DataGenerator

logger = logging.getLogger(__name__)


class OrderCreationScenario:
    """Execute order creation scenarios."""

    def __init__(
        self,
        api_client: FreshMartAPIClient,
        data_generator: DataGenerator,
    ):
        """Initialize order creation scenario.

        Args:
            api_client: FreshMart API client
            data_generator: Data generator instance
        """
        self.api_client = api_client
        self.data_generator = data_generator
        self.customers: list[dict[str, Any]] = []
        self.stores: list[dict[str, Any]] = []
        self.products: list[dict[str, Any]] = []

    async def initialize(self):
        """Initialize scenario by fetching required data."""
        logger.info("Initializing order creation scenario...")
        self.customers = await self.api_client.get_customers(limit=1000)
        self.stores = await self.api_client.get_stores(limit=100)
        self.products = await self.api_client.get_products(limit=1000)
        logger.info(
            f"Loaded {len(self.customers)} customers, {len(self.stores)} stores, "
            f"{len(self.products)} products"
        )

    async def execute(self) -> dict[str, Any]:
        """Execute order creation scenario.

        Returns:
            Result dictionary with order details
        """
        if not self.customers or not self.stores or not self.products:
            raise RuntimeError("Scenario not initialized. Call initialize() first.")

        # Select random customer and store
        customer = random.choice(self.customers)
        store = random.choice(self.stores)

        # Generate order details
        order_id = self.data_generator.generate_order_id()
        line_items = self.data_generator.generate_line_items(
            self.products, min_items=1, max_items=6
        )
        start_time, end_time = self.data_generator.generate_delivery_window()

        try:
            # Create order via API
            result = await self.api_client.create_order(
                order_id=order_id,
                customer_id=customer["customer_id"],
                store_id=store["store_id"],
                line_items=line_items,
                delivery_window_start=start_time,
                delivery_window_end=end_time,
            )

            logger.debug(
                f"Created order {order_id} for {customer['customer_name']} "
                f"at {store['store_name']} with {len(line_items)} items"
            )

            return {
                "success": True,
                "order_id": order_id,
                "customer_name": customer["customer_name"],
                "store_name": store["store_name"],
                "num_items": len(line_items),
                "total": sum(item["quantity"] * item["price"] for item in line_items),
            }

        except Exception as e:
            logger.error(f"Failed to create order {order_id}: {e}")
            return {
                "success": False,
                "error": str(e),
            }
