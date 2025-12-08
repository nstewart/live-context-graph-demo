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

    def __post_init__(self):
        """Validate configuration after initialization."""
        # Validate that weights sum to approximately 1.0
        total_weight = (
            self.new_order_weight
            + self.status_transition_weight
            + self.order_modification_weight
            + self.customer_creation_weight
            + self.inventory_update_weight
            + self.order_cancellation_weight
        )
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(
                f"Activity weights must sum to 1.0, got {total_weight:.3f} for profile '{self.name}'"
            )

        # Validate that all weights are non-negative
        weights = [
            self.new_order_weight,
            self.status_transition_weight,
            self.order_modification_weight,
            self.customer_creation_weight,
            self.inventory_update_weight,
            self.order_cancellation_weight,
        ]
        if any(w < 0 for w in weights):
            raise ValueError(f"Activity weights must be non-negative for profile '{self.name}'")


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
