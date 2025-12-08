"""Tests for configuration and profiles."""

import pytest

from loadgen.config import PROFILES, get_profile, list_profiles


def test_profiles_exist():
    """Test that all required profiles exist."""
    required_profiles = ["demo", "standard", "peak", "stress"]
    for profile_name in required_profiles:
        assert profile_name in PROFILES


def test_get_profile_demo():
    """Test getting demo profile."""
    profile = get_profile("demo")
    assert profile.name == "demo"
    assert profile.orders_per_minute == 5
    assert profile.concurrent_workflows == 10
    assert profile.duration_minutes == 30


def test_get_profile_standard():
    """Test getting standard profile."""
    profile = get_profile("standard")
    assert profile.name == "standard"
    assert profile.orders_per_minute == 20
    assert profile.concurrent_workflows == 50


def test_get_profile_peak():
    """Test getting peak profile."""
    profile = get_profile("peak")
    assert profile.name == "peak"
    assert profile.orders_per_minute == 60
    assert profile.concurrent_workflows == 150


def test_get_profile_stress():
    """Test getting stress profile."""
    profile = get_profile("stress")
    assert profile.name == "stress"
    assert profile.orders_per_minute == 200
    assert profile.concurrent_workflows == 500


def test_get_profile_invalid():
    """Test getting invalid profile raises error."""
    with pytest.raises(ValueError, match="Unknown profile"):
        get_profile("invalid_profile")


def test_list_profiles():
    """Test listing all profiles."""
    profiles = list_profiles()
    assert len(profiles) == 4
    profile_names = [p.name for p in profiles]
    assert "demo" in profile_names
    assert "standard" in profile_names
    assert "peak" in profile_names
    assert "stress" in profile_names


def test_profile_weights_sum_to_one():
    """Test that activity weights sum to approximately 1.0."""
    for profile in list_profiles():
        total = (
            profile.new_order_weight
            + profile.status_transition_weight
            + profile.order_modification_weight
            + profile.customer_creation_weight
            + profile.inventory_update_weight
            + profile.order_cancellation_weight
        )
        assert abs(total - 1.0) < 0.01, f"Profile {profile.name} weights sum to {total}"
