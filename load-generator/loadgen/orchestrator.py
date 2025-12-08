"""Orchestrator for load generation activities."""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional

from loadgen.api_client import FreshMartAPIClient
from loadgen.config import LoadProfile
from loadgen.data_generators import DataGenerator
from loadgen.metrics import MetricsTracker
from loadgen.scenarios import (
    CustomerScenario,
    InventoryScenario,
    OrderCreationScenario,
    OrderLifecycleScenario,
)

logger = logging.getLogger(__name__)


class LoadOrchestrator:
    """Orchestrate load generation across multiple scenarios."""

    def __init__(
        self,
        api_url: str,
        profile: LoadProfile,
        seed: Optional[int] = None,
    ):
        """Initialize load orchestrator.

        Args:
            api_url: FreshMart API base URL
            profile: Load generation profile
            seed: Random seed for reproducibility
        """
        self.api_url = api_url
        self.profile = profile
        self.seed = seed

        # Initialize components
        self.api_client = FreshMartAPIClient(base_url=api_url)
        self.data_generator = DataGenerator(seed=seed)
        self.metrics = MetricsTracker()

        # Initialize scenarios
        self.order_scenario = OrderCreationScenario(
            self.api_client, self.data_generator
        )
        self.lifecycle_scenario = OrderLifecycleScenario(
            self.api_client, self.data_generator
        )
        self.inventory_scenario = InventoryScenario(
            self.api_client, self.data_generator
        )
        self.customer_scenario = CustomerScenario(
            self.api_client, self.data_generator
        )

        # Control flags
        self.running = False
        self.stop_requested = False

    async def initialize(self):
        """Initialize orchestrator and scenarios."""
        logger.info("Initializing load orchestrator...")

        # Health check
        try:
            health = await self.api_client.health_check()
            logger.info(f"API health check passed: {health}")
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            raise RuntimeError(f"FreshMart API is not available at {self.api_url}")

        # Initialize scenarios
        await self.order_scenario.initialize()
        await self.inventory_scenario.initialize()
        await self.customer_scenario.initialize()

        logger.info("Load orchestrator initialized successfully")

    async def cleanup(self):
        """Clean up resources."""
        await self.api_client.close()

    def select_activity(self) -> str:
        """Select next activity based on profile weights.

        Returns:
            Activity type name
        """
        activities = [
            "order",
            "transition",
            "modification",
            "customer",
            "inventory",
            "cancellation",
        ]
        weights = [
            self.profile.new_order_weight,
            self.profile.status_transition_weight,
            self.profile.order_modification_weight,
            self.profile.customer_creation_weight,
            self.profile.inventory_update_weight,
            self.profile.order_cancellation_weight,
        ]

        return random.choices(activities, weights=weights, k=1)[0]

    async def execute_activity(self, activity_type: str) -> dict:
        """Execute a single activity.

        Args:
            activity_type: Type of activity to execute

        Returns:
            Activity result dictionary
        """
        start_time = time.time()

        try:
            if activity_type == "order":
                result = await self.order_scenario.execute()
                metric_type = "order"
            elif activity_type == "transition":
                result = await self.lifecycle_scenario.execute(force_cancellation=False)
                metric_type = "transition"
            elif activity_type == "cancellation":
                result = await self.lifecycle_scenario.execute(force_cancellation=True)
                metric_type = "cancellation"
            elif activity_type == "customer":
                result = await self.customer_scenario.execute()
                metric_type = "customer"
            elif activity_type == "inventory":
                result = await self.inventory_scenario.execute()
                metric_type = "inventory"
            elif activity_type == "modification":
                # For now, treat modifications like status transitions
                result = await self.lifecycle_scenario.execute(force_cancellation=False)
                metric_type = "transition"
            else:
                result = {"success": False, "error": f"Unknown activity: {activity_type}"}
                metric_type = "other"

            latency = time.time() - start_time
            self.metrics.record_activity(
                success=result.get("success", False),
                latency=latency,
                activity_type=metric_type,
                error=result.get("error") if not result.get("success", False) else None,
            )

            return result

        except Exception as e:
            logger.error(f"Activity execution failed: {e}", exc_info=True)
            self.metrics.record_activity(
                success=False,
                error=str(e),
            )
            return {"success": False, "error": str(e)}

    async def worker(self, worker_id: int):
        """Worker coroutine that executes activities.

        Args:
            worker_id: Unique worker identifier
        """
        logger.debug(f"Worker {worker_id} started")

        while self.running and not self.stop_requested:
            # Select and execute activity
            activity_type = self.select_activity()

            try:
                await self.execute_activity(activity_type)
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

            # Add jitter to avoid thundering herd
            jitter = random.uniform(0.5, 1.5)
            await asyncio.sleep(jitter)

        logger.debug(f"Worker {worker_id} stopped")

    async def rate_controller(self):
        """Control activity rate to match profile target."""
        # Calculate target interval between activities
        target_per_second = self.profile.orders_per_minute / 60.0
        target_interval = 1.0 / target_per_second if target_per_second > 0 else 1.0

        logger.info(
            f"Rate controller: target {self.profile.orders_per_minute} orders/min "
            f"(~{target_per_second:.2f} activities/sec)"
        )

        last_count = 0
        while self.running and not self.stop_requested:
            await asyncio.sleep(10)  # Check every 10 seconds

            # Get current throughput
            current_throughput = self.metrics.get_throughput(window=True)

            # Log status
            logger.debug(
                f"Current throughput: {current_throughput:.1f} activities/min "
                f"(target: {self.profile.orders_per_minute})"
            )

    async def metrics_reporter(self):
        """Periodically report metrics."""
        while self.running and not self.stop_requested:
            await asyncio.sleep(60)  # Report every minute

            windowed = self.metrics.get_windowed_summary()
            logger.info(
                f"Last minute: {windowed['successes']} activities, "
                f"{windowed['throughput_per_min']:.1f}/min, "
                f"{windowed['avg_latency_ms']:.0f}ms avg latency, "
                f"{windowed['success_rate']:.1f}% success"
            )

            # Reset windowed metrics
            self.metrics.reset_window()

    async def run(self, duration_minutes: Optional[int] = None):
        """Run load generation.

        Args:
            duration_minutes: Optional duration in minutes (overrides profile)
        """
        # Determine duration
        duration = duration_minutes or self.profile.duration_minutes

        logger.info("=" * 60)
        logger.info("FreshMart Load Generator")
        logger.info("=" * 60)
        logger.info(f"Profile: {self.profile.name} - {self.profile.description}")
        logger.info(f"Target: {self.profile.orders_per_minute} orders/min")
        logger.info(f"Concurrent workflows: {self.profile.concurrent_workflows}")
        if duration:
            logger.info(f"Duration: {duration} minutes")
        else:
            logger.info("Duration: until interrupted")
        logger.info(f"API: {self.api_url}")
        logger.info("=" * 60)

        # Initialize
        await self.initialize()

        # Start workers
        self.running = True
        workers = [
            asyncio.create_task(self.worker(i))
            for i in range(self.profile.concurrent_workflows)
        ]

        # Start support tasks
        rate_task = asyncio.create_task(self.rate_controller())
        metrics_task = asyncio.create_task(self.metrics_reporter())

        try:
            if duration:
                # Run for specified duration
                logger.info(f"Running for {duration} minutes...")
                await asyncio.sleep(duration * 60)
            else:
                # Run indefinitely until interrupted
                logger.info("Running until interrupted (Ctrl+C)...")
                await asyncio.Event().wait()  # Wait forever

        except asyncio.CancelledError:
            logger.info("Load generation interrupted")
        finally:
            # Stop workers
            logger.info("Stopping workers...")
            self.running = False
            self.stop_requested = True

            # Wait for workers to finish
            await asyncio.gather(*workers, rate_task, metrics_task, return_exceptions=True)

            # Cleanup
            await self.cleanup()

            # Print final summary
            self.print_summary()

    def print_summary(self):
        """Print final summary statistics."""
        summary = self.metrics.get_summary()

        logger.info("=" * 60)
        logger.info("Final Summary")
        logger.info("=" * 60)
        logger.info(f"Duration: {summary['duration_seconds'] / 60:.1f} minutes")
        logger.info(f"Total activities: {summary['total_successes']}")
        logger.info(f"Success rate: {summary['success_rate']:.1f}%")
        logger.info(f"Throughput: {summary['throughput_per_min']:.1f} activities/min")
        logger.info(f"Avg latency: {summary['avg_latency_ms']:.0f}ms")
        logger.info(f"P95 latency: {summary['p95_latency_ms']:.0f}ms")
        logger.info(f"P99 latency: {summary['p99_latency_ms']:.0f}ms")
        logger.info("")
        logger.info("Activity Breakdown:")
        logger.info(f"  Orders created: {summary['orders_created']}")
        logger.info(f"  Status transitions: {summary['status_transitions']}")
        logger.info(f"  Customers created: {summary['customers_created']}")
        logger.info(f"  Inventory updates: {summary['inventory_updates']}")
        logger.info(f"  Cancellations: {summary['cancellations']}")

        # Print error breakdown if there were failures
        if summary['total_failures'] > 0 and summary['error_counts']:
            logger.info("")
            logger.info("Error Breakdown:")
            for error_msg, count in sorted(
                summary['error_counts'].items(), key=lambda x: x[1], reverse=True
            ):
                # Truncate long error messages
                display_msg = error_msg[:60] + "..." if len(error_msg) > 60 else error_msg
                logger.info(f"  {display_msg}: {count}")

        logger.info("=" * 60)
