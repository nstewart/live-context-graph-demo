"""Metrics tracking for load generation."""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ActivityMetrics:
    """Track activity metrics."""

    # Counters
    total_attempts: int = 0
    total_successes: int = 0
    total_failures: int = 0

    # Latency tracking (in seconds)
    latencies: list[float] = field(default_factory=list)

    # Activity-specific counters
    orders_created: int = 0
    status_transitions: int = 0
    customers_created: int = 0
    inventory_updates: int = 0
    cancellations: int = 0

    def record_success(self, latency: float, activity_type: str):
        """Record a successful activity.

        Args:
            latency: Activity latency in seconds
            activity_type: Type of activity (order, transition, etc.)
        """
        self.total_attempts += 1
        self.total_successes += 1
        self.latencies.append(latency)

        # Update specific counters
        if activity_type == "order":
            self.orders_created += 1
        elif activity_type == "transition":
            self.status_transitions += 1
        elif activity_type == "customer":
            self.customers_created += 1
        elif activity_type == "inventory":
            self.inventory_updates += 1
        elif activity_type == "cancellation":
            self.cancellations += 1

    def record_failure(self):
        """Record a failed activity."""
        self.total_attempts += 1
        self.total_failures += 1

    @property
    def success_rate(self) -> float:
        """Calculate success rate.

        Returns:
            Success rate as percentage (0-100)
        """
        if self.total_attempts == 0:
            return 0.0
        return (self.total_successes / self.total_attempts) * 100

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency in milliseconds.

        Returns:
            Average latency in ms
        """
        if not self.latencies:
            return 0.0
        return (sum(self.latencies) / len(self.latencies)) * 1000

    @property
    def p95_latency_ms(self) -> float:
        """Calculate 95th percentile latency in milliseconds.

        Returns:
            P95 latency in ms
        """
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] * 1000

    @property
    def p99_latency_ms(self) -> float:
        """Calculate 99th percentile latency in milliseconds.

        Returns:
            P99 latency in ms
        """
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] * 1000


class MetricsTracker:
    """Track metrics for load generation."""

    def __init__(self):
        """Initialize metrics tracker."""
        self.start_time = time.time()
        self.overall = ActivityMetrics()
        self.windowed = ActivityMetrics()  # Last minute stats
        self.window_start = time.time()

    def record_activity(
        self,
        success: bool,
        latency: float = 0.0,
        activity_type: str = "other",
    ):
        """Record an activity.

        Args:
            success: Whether activity succeeded
            latency: Activity latency in seconds
            activity_type: Type of activity
        """
        if success:
            self.overall.record_success(latency, activity_type)
            self.windowed.record_success(latency, activity_type)
        else:
            self.overall.record_failure()
            self.windowed.record_failure()

    def reset_window(self):
        """Reset windowed metrics (call every minute)."""
        self.windowed = ActivityMetrics()
        self.window_start = time.time()

    def get_throughput(self, window: bool = True) -> float:
        """Calculate throughput in activities per minute.

        Args:
            window: If True, use windowed metrics; else use overall

        Returns:
            Activities per minute
        """
        if window:
            elapsed = time.time() - self.window_start
            if elapsed == 0:
                return 0.0
            return (self.windowed.total_successes / elapsed) * 60
        else:
            elapsed = time.time() - self.start_time
            if elapsed == 0:
                return 0.0
            return (self.overall.total_successes / elapsed) * 60

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics.

        Returns:
            Dictionary of summary statistics
        """
        elapsed = time.time() - self.start_time
        return {
            "duration_seconds": elapsed,
            "total_attempts": self.overall.total_attempts,
            "total_successes": self.overall.total_successes,
            "total_failures": self.overall.total_failures,
            "success_rate": self.overall.success_rate,
            "throughput_per_min": self.get_throughput(window=False),
            "avg_latency_ms": self.overall.avg_latency_ms,
            "p95_latency_ms": self.overall.p95_latency_ms,
            "p99_latency_ms": self.overall.p99_latency_ms,
            "orders_created": self.overall.orders_created,
            "status_transitions": self.overall.status_transitions,
            "customers_created": self.overall.customers_created,
            "inventory_updates": self.overall.inventory_updates,
            "cancellations": self.overall.cancellations,
        }

    def get_windowed_summary(self) -> dict[str, Any]:
        """Get windowed summary statistics (last minute).

        Returns:
            Dictionary of windowed statistics
        """
        return {
            "window_seconds": time.time() - self.window_start,
            "attempts": self.windowed.total_attempts,
            "successes": self.windowed.total_successes,
            "failures": self.windowed.total_failures,
            "success_rate": self.windowed.success_rate,
            "throughput_per_min": self.get_throughput(window=True),
            "avg_latency_ms": self.windowed.avg_latency_ms,
            "orders_created": self.windowed.orders_created,
            "status_transitions": self.windowed.status_transitions,
            "customers_created": self.windowed.customers_created,
            "inventory_updates": self.windowed.inventory_updates,
            "cancellations": self.windowed.cancellations,
        }
