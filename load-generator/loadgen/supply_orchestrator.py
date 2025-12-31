"""Orchestrator for supply-side load generation (courier dispatch, deliveries)."""

import asyncio
import logging
import signal
import time
from datetime import datetime
from typing import Optional

from loadgen.api_client import FreshMartAPIClient
from loadgen.config import LoadProfile, SupplyConfig
from loadgen.metrics import MetricsTracker
from loadgen.scenarios import CourierDispatchScenario

logger = logging.getLogger(__name__)


class SupplyOrchestrator:
    """Orchestrate supply-side load generation (courier dispatch, deliveries)."""

    def __init__(
        self,
        api_url: str,
        profile: LoadProfile,
        supply_config: Optional[SupplyConfig] = None,
    ):
        """Initialize supply orchestrator.

        Args:
            api_url: FreshMart API base URL
            profile: Load generation profile (used for duration)
            supply_config: Supply-specific configuration
        """
        self.api_url = api_url
        self.profile = profile
        self.supply_config = supply_config or SupplyConfig()

        # Initialize components
        self.api_client = FreshMartAPIClient(base_url=api_url)
        self.metrics = MetricsTracker()

        # Initialize dispatch scenario with configurable durations
        self.dispatch_scenario = CourierDispatchScenario(
            self.api_client,
            picking_duration_seconds=self.supply_config.picking_duration_seconds,
            delivery_duration_seconds=self.supply_config.delivery_duration_seconds,
        )

        # Control flags
        self.running = False
        self.stop_requested = False

    async def initialize(self):
        """Initialize orchestrator and scenarios."""
        logger.info("Initializing supply orchestrator...")

        # Health check
        try:
            health = await self.api_client.health_check()
            logger.info(f"API health check passed: {health}")
        except Exception as e:
            logger.error(f"API health check failed: {e}")
            raise RuntimeError(f"FreshMart API is not available at {self.api_url}")

        # Initialize dispatch scenario
        await self.dispatch_scenario.initialize()

        logger.info("Supply orchestrator initialized successfully")

    async def cleanup(self):
        """Clean up resources."""
        await self.api_client.close()

    async def courier_dispatcher(self):
        """Background task that runs courier dispatch cycles.

        This task:
        1. Advances tasks where the timer has elapsed (PICKING->DELIVERING, DELIVERING->COMPLETED)
        2. Assigns available couriers to pending orders

        Runs every dispatch_interval_seconds.
        """
        logger.info(
            f"Courier dispatcher started (interval: {self.supply_config.dispatch_interval_seconds}s, "
            f"picking: {self.supply_config.picking_duration_seconds}s, "
            f"delivery: {self.supply_config.delivery_duration_seconds}s)"
        )

        while self.running and not self.stop_requested:
            try:
                start_time = time.time()
                result = await self.dispatch_scenario.execute()

                # Log dispatch activity if anything happened
                total_actions = (
                    result.get("tasks_advanced", 0) + result.get("assignments_made", 0)
                )
                if total_actions > 0:
                    logger.debug(
                        f"Dispatch cycle: {result.get('assignments_made', 0)} assigned, "
                        f"{result.get('deliveries_started', 0)} delivering, "
                        f"{result.get('deliveries_completed', 0)} completed"
                    )

                # Record metrics for dispatch activity
                latency = time.time() - start_time
                if result.get("assignments_made", 0) > 0:
                    for _ in range(result["assignments_made"]):
                        self.metrics.record_activity(
                            success=True,
                            latency=latency,
                            activity_type="dispatch_assign",
                        )
                if result.get("deliveries_completed", 0) > 0:
                    for _ in range(result["deliveries_completed"]):
                        self.metrics.record_activity(
                            success=True,
                            latency=latency,
                            activity_type="dispatch_complete",
                        )

            except Exception as e:
                logger.error(f"Dispatch cycle error: {e}")

            # Wait before next cycle
            await asyncio.sleep(self.supply_config.dispatch_interval_seconds)

        logger.debug("Courier dispatcher stopped")

    async def metrics_reporter(self):
        """Periodically report metrics."""
        while self.running and not self.stop_requested:
            await asyncio.sleep(60)

            windowed = self.metrics.get_windowed_summary()
            # Get supply-specific metrics
            summary = self.metrics.get_summary()
            dispatch_assigns = summary.get("dispatch_assigns", 0)
            dispatch_completes = summary.get("dispatch_completes", 0)

            logger.info(
                f"Supply last minute: {windowed['successes']} actions, "
                f"assigns: {dispatch_assigns}, completes: {dispatch_completes}"
            )

            self.metrics.reset_window()

    async def run(self, duration_minutes: Optional[int] = None):
        """Run supply load generation.

        Args:
            duration_minutes: Optional duration in minutes (overrides profile)
        """
        duration = duration_minutes or self.profile.duration_minutes

        logger.info("=" * 60)
        logger.info("FreshMart Supply Generator (Courier Dispatch)")
        logger.info("=" * 60)
        logger.info(f"Dispatch interval: {self.supply_config.dispatch_interval_seconds}s")
        logger.info(f"Picking duration: {self.supply_config.picking_duration_seconds}s")
        logger.info(f"Delivery duration: {self.supply_config.delivery_duration_seconds}s")
        if duration:
            logger.info(f"Duration: {duration} minutes")
        else:
            logger.info("Duration: until interrupted")
        logger.info(f"API: {self.api_url}")
        logger.info("=" * 60)

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        shutdown_event = asyncio.Event()

        def signal_handler():
            logger.info("Interrupt received, stopping supply generator...")
            self.stop_requested = True
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        # Initialize
        await self.initialize()

        # Start dispatch and metrics
        self.running = True
        dispatch_task = asyncio.create_task(self.courier_dispatcher())
        metrics_task = asyncio.create_task(self.metrics_reporter())

        try:
            if duration:
                logger.info(f"Running supply generator for {duration} minutes...")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=duration * 60)
                except asyncio.TimeoutError:
                    pass
            else:
                logger.info("Running supply generator until interrupted (Ctrl+C)...")
                await shutdown_event.wait()

        except asyncio.CancelledError:
            logger.info("Supply generation cancelled")
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.remove_signal_handler(sig)
                except NotImplementedError:
                    pass

            logger.info("Stopping supply generator...")
            self.running = False
            self.stop_requested = True

            dispatch_task.cancel()
            metrics_task.cancel()

            await asyncio.gather(dispatch_task, metrics_task, return_exceptions=True)

            await self.cleanup()
            self.print_summary()

    def print_summary(self):
        """Print final summary statistics."""
        summary = self.metrics.get_summary()

        logger.info("=" * 60)
        logger.info("Supply Generator Summary")
        logger.info("=" * 60)
        logger.info(f"Duration: {summary['duration_seconds'] / 60:.1f} minutes")
        logger.info(f"Total dispatch actions: {summary['total_successes']}")
        logger.info(f"Couriers assigned: {summary.get('dispatch_assigns', 0)}")
        logger.info(f"Deliveries completed: {summary.get('dispatch_completes', 0)}")
        logger.info("=" * 60)
