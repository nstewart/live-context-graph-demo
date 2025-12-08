"""Order lifecycle transition scenarios."""

import logging
import random
from datetime import datetime
from typing import Any

from loadgen.api_client import FreshMartAPIClient
from loadgen.data_generators import DataGenerator

logger = logging.getLogger(__name__)


class OrderLifecycleScenario:
    """Execute order status transition scenarios."""

    def __init__(
        self,
        api_client: FreshMartAPIClient,
        data_generator: DataGenerator,
    ):
        """Initialize order lifecycle scenario.

        Args:
            api_client: FreshMart API client
            data_generator: Data generator instance
        """
        self.api_client = api_client
        self.data_generator = data_generator

    async def execute(self) -> dict[str, Any]:
        """Execute order lifecycle scenario.

        Returns:
            Result dictionary with transition details
        """
        # Fetch orders that can transition
        transitionable_statuses = ["CREATED", "PICKING", "OUT_FOR_DELIVERY"]
        status = random.choice(transitionable_statuses)

        try:
            orders = await self.api_client.get_orders(status=status, limit=100)

            if not orders:
                return {
                    "success": False,
                    "error": f"No orders found in status {status}",
                }

            # Select a random order
            order = random.choice(orders)
            order_id = order["order_id"]

            # Check if order should be cancelled
            if self.data_generator.should_cancel_order(status):
                await self.api_client.update_order_status(order_id, "CANCELLED")
                logger.debug(f"Cancelled order {order_id} (was {status})")
                return {
                    "success": True,
                    "order_id": order_id,
                    "old_status": status,
                    "new_status": "CANCELLED",
                    "action": "cancelled",
                }

            # Calculate order age (approximate from current time)
            # Note: In a real scenario, we'd parse the order creation timestamp
            # For load generation, we'll use random age
            order_age_minutes = random.uniform(0, 60)

            # Check if order should transition
            should_transition, new_status = (
                self.data_generator.should_transition_status(status, order_age_minutes)
            )

            if should_transition and new_status:
                await self.api_client.update_order_status(order_id, new_status)
                logger.debug(f"Transitioned order {order_id}: {status} -> {new_status}")
                return {
                    "success": True,
                    "order_id": order_id,
                    "old_status": status,
                    "new_status": new_status,
                    "action": "transitioned",
                }
            else:
                return {
                    "success": False,
                    "error": "Order not ready for transition",
                }

        except Exception as e:
            logger.error(f"Failed to transition order: {e}")
            return {
                "success": False,
                "error": str(e),
            }
