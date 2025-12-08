"""Configuration and profiles for load generation."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LoadProfile:
    """Configuration for a load generation profile."""

    name: str
    description: str
    orders_per_minute: float
    concurrent_workflows: int
    duration_minutes: Optional[int] = None

    # Activity mix (should sum to 1.0)
    new_order_weight: float = 0.40
    status_transition_weight: float = 0.30
    order_modification_weight: float = 0.10
    customer_creation_weight: float = 0.05
    inventory_update_weight: float = 0.10
    order_cancellation_weight: float = 0.05


# Predefined profiles matching the product brief
PROFILES = {
    "demo": LoadProfile(
        name="demo",
        description="Gentle activity for showcasing features",
        orders_per_minute=5,
        concurrent_workflows=10,
        duration_minutes=30,
    ),
    "standard": LoadProfile(
        name="standard",
        description="Realistic weekday traffic",
        orders_per_minute=20,
        concurrent_workflows=50,
        duration_minutes=120,
    ),
    "peak": LoadProfile(
        name="peak",
        description="Peak hour simulation",
        orders_per_minute=60,
        concurrent_workflows=150,
        duration_minutes=60,
    ),
    "stress": LoadProfile(
        name="stress",
        description="Stress testing - push system limits",
        orders_per_minute=200,
        concurrent_workflows=500,
        duration_minutes=30,
    ),
}


def get_profile(name: str) -> LoadProfile:
    """Get a load profile by name.

    Args:
        name: Profile name (demo, standard, peak, stress)

    Returns:
        LoadProfile configuration

    Raises:
        ValueError: If profile name is not found
    """
    if name not in PROFILES:
        available = ", ".join(PROFILES.keys())
        raise ValueError(f"Unknown profile '{name}'. Available: {available}")
    return PROFILES[name]


def list_profiles() -> list[LoadProfile]:
    """List all available profiles.

    Returns:
        List of all LoadProfile configurations
    """
    return list(PROFILES.values())
