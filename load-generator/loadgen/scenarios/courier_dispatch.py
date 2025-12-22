"""Courier dispatch scenario for CQRS-based order fulfillment.

This scenario manages the courier-driven order lifecycle:
1. Queries Materialize for tasks ready to advance (timer elapsed)
2. Advances tasks: PICKING -> DELIVERING -> COMPLETED
3. Assigns available couriers to pending orders
4. All state is maintained in Materialize views
"""

import logging
from datetime import datetime, timezone
from typing import Any

from loadgen.api_client import FreshMartAPIClient

logger = logging.getLogger(__name__)

# Task timing configuration (in seconds)
PICKING_DURATION_SECONDS = 5  # 5 seconds
DELIVERY_DURATION_SECONDS = 5  # 5 seconds


class CourierDispatchScenario:
    """Execute courier dispatch operations using CQRS pattern.

    This scenario:
    - Reads state from Materialize views (queries)
    - Writes state changes to triples (commands)
    - Does not maintain any in-memory state
    """

    def __init__(self, api_client: FreshMartAPIClient):
        """Initialize courier dispatch scenario.

        Args:
            api_client: FreshMart API client for queries and writes
        """
        self.api_client = api_client
        self.stores: list[dict[str, Any]] = []

    async def initialize(self):
        """Initialize scenario by fetching store list."""
        logger.info("Initializing courier dispatch scenario...")
        self.stores = await self.api_client.get_stores(limit=100)
        logger.info(f"Loaded {len(self.stores)} stores for dispatch")

    async def execute(self) -> dict[str, Any]:
        """Execute one dispatch cycle.

        This method:
        1. Advances tasks where timer has elapsed
        2. Assigns available couriers to pending orders

        Returns:
            Result dictionary with dispatch statistics
        """
        results = {
            "tasks_advanced": 0,
            "picking_started": 0,
            "deliveries_started": 0,
            "deliveries_completed": 0,
            "assignments_made": 0,
            "errors": [],
        }

        try:
            # Step 1: Advance tasks that are ready
            advanced = await self._advance_ready_tasks()
            results["tasks_advanced"] = advanced["total"]
            results["deliveries_started"] = advanced["to_delivering"]
            results["deliveries_completed"] = advanced["completed"]

            # Step 2: Assign couriers to pending orders
            assignments = await self._assign_couriers_to_orders()
            results["assignments_made"] = assignments["assigned"]
            results["picking_started"] = assignments["assigned"]

            # Log summary at INFO level if anything happened
            if results["tasks_advanced"] > 0 or results["assignments_made"] > 0:
                logger.info(
                    f"Dispatch: {results['assignments_made']} assigned, "
                    f"{results['deliveries_started']} to delivery, "
                    f"{results['deliveries_completed']} completed"
                )

        except Exception as e:
            logger.error(f"Dispatch cycle error: {e}")
            results["errors"].append(str(e))

        return results

    async def _advance_ready_tasks(self) -> dict[str, int]:
        """Advance tasks where the timer has elapsed.

        - PICKING tasks (2 min elapsed) -> DELIVERING
        - DELIVERING tasks (2 min elapsed) -> COMPLETED, courier freed

        Returns:
            Count of tasks advanced by type
        """
        advanced = {"total": 0, "to_delivering": 0, "completed": 0}

        try:
            # Query Materialize for tasks ready to advance
            ready_tasks = await self.api_client.get_tasks_ready_to_advance()

            for task in ready_tasks:
                task_id = task["task_id"]
                order_id = task["order_id"]
                courier_id = task["courier_id"]
                current_status = task["task_status"]

                try:
                    if current_status == "PICKING":
                        # Transition to DELIVERING
                        await self._transition_to_delivering(task_id, order_id, courier_id)
                        advanced["to_delivering"] += 1
                        advanced["total"] += 1
                        logger.debug(f"Task {task_id}: PICKING -> DELIVERING")

                    elif current_status == "DELIVERING":
                        # Complete delivery
                        await self._complete_delivery(task_id, order_id, courier_id)
                        advanced["completed"] += 1
                        advanced["total"] += 1
                        logger.debug(f"Task {task_id}: DELIVERING -> COMPLETED")

                except Exception as e:
                    logger.error(f"Failed to advance task {task_id}: {e}")

        except Exception as e:
            logger.error(f"Failed to query ready tasks: {e}")

        return advanced

    async def _transition_to_delivering(self, task_id: str, order_id: str, courier_id: str):
        """Transition task from PICKING to DELIVERING."""
        now = datetime.now(timezone.utc).isoformat()

        triples = [
            {
                "subject_id": task_id,
                "predicate": "task_status",
                "object_value": "DELIVERING",
                "object_type": "string",
            },
            {
                "subject_id": task_id,
                "predicate": "task_started_at",
                "object_value": now,
                "object_type": "timestamp",
            },
            {
                "subject_id": order_id,
                "predicate": "order_status",
                "object_value": "OUT_FOR_DELIVERY",
                "object_type": "string",
            },
            {
                "subject_id": courier_id,
                "predicate": "courier_status",
                "object_value": "ON_DELIVERY",
                "object_type": "string",
            },
        ]
        await self.api_client.update_triples_batch(triples)

    async def _complete_delivery(self, task_id: str, order_id: str, courier_id: str):
        """Complete delivery - mark task done and free courier."""
        triples = [
            {
                "subject_id": task_id,
                "predicate": "task_status",
                "object_value": "COMPLETED",
                "object_type": "string",
            },
            {
                "subject_id": order_id,
                "predicate": "order_status",
                "object_value": "DELIVERED",
                "object_type": "string",
            },
            {
                "subject_id": courier_id,
                "predicate": "courier_status",
                "object_value": "AVAILABLE",
                "object_type": "string",
            },
        ]
        await self.api_client.update_triples_batch(triples)

    async def _assign_couriers_to_orders(self) -> dict[str, int]:
        """Assign available couriers to pending orders.

        For each store:
        1. Query available couriers
        2. Query orders awaiting courier
        3. Match them up and create assignments

        Returns:
            Count of assignments made
        """
        assigned_count = 0

        for store in self.stores:
            store_id = store["store_id"]

            try:
                # Get available couriers for this store
                available_couriers = await self.api_client.get_available_couriers(
                    store_id=store_id, limit=10
                )

                if not available_couriers:
                    continue

                # Get orders awaiting courier for this store
                pending_orders = await self.api_client.get_orders_awaiting_courier(
                    store_id=store_id, limit=len(available_couriers)
                )

                if not pending_orders:
                    continue

                # Match couriers to orders (1:1)
                for courier, order in zip(available_couriers, pending_orders):
                    try:
                        await self._assign_courier_to_order(
                            courier_id=courier["courier_id"],
                            order_id=order["order_id"],
                        )
                        assigned_count += 1
                        logger.debug(
                            f"Assigned courier {courier['courier_id']} "
                            f"to order {order['order_id']}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to assign {courier['courier_id']} "
                            f"to {order['order_id']}: {e}"
                        )

            except Exception as e:
                logger.error(f"Failed to process store {store_id}: {e}")

        return {"assigned": assigned_count}

    async def _assign_courier_to_order(self, courier_id: str, order_id: str):
        """Assign a courier to an order - create task and update statuses."""
        now = datetime.now(timezone.utc).isoformat()

        # Generate task ID from order ID
        order_num = order_id.split(":")[-1] if ":" in order_id else order_id
        task_id = f"task:{order_num}"

        triples = [
            # Create delivery task
            {
                "subject_id": task_id,
                "predicate": "task_of_order",
                "object_value": order_id,
                "object_type": "entity_ref",
            },
            {
                "subject_id": task_id,
                "predicate": "assigned_to",
                "object_value": courier_id,
                "object_type": "entity_ref",
            },
            {
                "subject_id": task_id,
                "predicate": "task_status",
                "object_value": "PICKING",
                "object_type": "string",
            },
            {
                "subject_id": task_id,
                "predicate": "task_started_at",
                "object_value": now,
                "object_type": "timestamp",
            },
            # Update courier status
            {
                "subject_id": courier_id,
                "predicate": "courier_status",
                "object_value": "PICKING",
                "object_type": "string",
            },
            # Update order status
            {
                "subject_id": order_id,
                "predicate": "order_status",
                "object_value": "PICKING",
                "object_type": "string",
            },
        ]

        await self.api_client.update_triples_batch(triples)
