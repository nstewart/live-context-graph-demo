"""Tests for metrics tracking."""

import time

import pytest

from loadgen.metrics import ActivityMetrics, MetricsTracker


def test_activity_metrics_initialization():
    """Test ActivityMetrics initialization."""
    metrics = ActivityMetrics()
    assert metrics.total_attempts == 0
    assert metrics.total_successes == 0
    assert metrics.total_failures == 0
    assert len(metrics.latencies) == 0


def test_activity_metrics_record_success():
    """Test recording successful activity."""
    metrics = ActivityMetrics()
    metrics.record_success(0.5, "order")

    assert metrics.total_attempts == 1
    assert metrics.total_successes == 1
    assert metrics.total_failures == 0
    assert metrics.orders_created == 1
    assert len(metrics.latencies) == 1


def test_activity_metrics_record_failure():
    """Test recording failed activity."""
    metrics = ActivityMetrics()
    metrics.record_failure()

    assert metrics.total_attempts == 1
    assert metrics.total_successes == 0
    assert metrics.total_failures == 1


def test_activity_metrics_success_rate():
    """Test success rate calculation."""
    metrics = ActivityMetrics()

    # No attempts
    assert metrics.success_rate == 0.0

    # All successes
    metrics.record_success(0.1, "order")
    metrics.record_success(0.2, "order")
    assert metrics.success_rate == 100.0

    # Mixed
    metrics.record_failure()
    assert metrics.success_rate == pytest.approx(66.67, rel=0.01)


def test_activity_metrics_avg_latency():
    """Test average latency calculation."""
    metrics = ActivityMetrics()

    # No latencies
    assert metrics.avg_latency_ms == 0.0

    # Add latencies
    metrics.record_success(0.1, "order")  # 100ms
    metrics.record_success(0.2, "order")  # 200ms
    metrics.record_success(0.3, "order")  # 300ms

    assert metrics.avg_latency_ms == pytest.approx(200.0, rel=0.01)


def test_activity_metrics_p95_latency():
    """Test P95 latency calculation."""
    metrics = ActivityMetrics()

    # Add 100 latencies
    for i in range(100):
        metrics.record_success(i / 1000.0, "order")  # 0-99ms

    # P95 should be around 95ms
    assert 90 <= metrics.p95_latency_ms <= 99


def test_activity_metrics_activity_types():
    """Test activity type counters."""
    metrics = ActivityMetrics()

    metrics.record_success(0.1, "order")
    metrics.record_success(0.1, "transition")
    metrics.record_success(0.1, "customer")
    metrics.record_success(0.1, "inventory")
    metrics.record_success(0.1, "cancellation")

    assert metrics.orders_created == 1
    assert metrics.status_transitions == 1
    assert metrics.customers_created == 1
    assert metrics.inventory_updates == 1
    assert metrics.cancellations == 1


def test_metrics_tracker_initialization():
    """Test MetricsTracker initialization."""
    tracker = MetricsTracker()
    assert tracker.overall.total_attempts == 0
    assert tracker.windowed.total_attempts == 0


def test_metrics_tracker_record_activity():
    """Test recording activity in tracker."""
    tracker = MetricsTracker()

    tracker.record_activity(success=True, latency=0.5, activity_type="order")

    assert tracker.overall.total_successes == 1
    assert tracker.windowed.total_successes == 1
    assert tracker.overall.orders_created == 1


def test_metrics_tracker_reset_window():
    """Test resetting windowed metrics."""
    tracker = MetricsTracker()

    tracker.record_activity(success=True, latency=0.5, activity_type="order")
    assert tracker.windowed.total_successes == 1

    tracker.reset_window()
    assert tracker.windowed.total_successes == 0
    assert tracker.overall.total_successes == 1  # Overall not reset


def test_metrics_tracker_throughput():
    """Test throughput calculation."""
    tracker = MetricsTracker()

    # Record some activities
    for _ in range(10):
        tracker.record_activity(success=True, latency=0.1, activity_type="order")

    # Wait a bit
    time.sleep(0.1)

    # Throughput should be > 0
    throughput = tracker.get_throughput(window=True)
    assert throughput > 0


def test_metrics_tracker_summary():
    """Test summary generation."""
    tracker = MetricsTracker()

    tracker.record_activity(success=True, latency=0.1, activity_type="order")
    tracker.record_activity(success=True, latency=0.2, activity_type="transition")
    tracker.record_activity(success=False)

    summary = tracker.get_summary()

    assert summary["total_attempts"] == 3
    assert summary["total_successes"] == 2
    assert summary["total_failures"] == 1
    assert summary["orders_created"] == 1
    assert summary["status_transitions"] == 1


def test_metrics_tracker_windowed_summary():
    """Test windowed summary generation."""
    tracker = MetricsTracker()

    tracker.record_activity(success=True, latency=0.1, activity_type="order")

    windowed = tracker.get_windowed_summary()

    assert windowed["successes"] == 1
    assert windowed["orders_created"] == 1
