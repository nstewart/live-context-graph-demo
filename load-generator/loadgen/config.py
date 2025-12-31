"""Configuration and profiles for load generation."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SupplyConfig:
    """Configuration for supply-side (courier dispatch) generation."""

    # How often to run dispatch cycles (seconds)
    dispatch_interval_seconds: float = 1.0

    # Task durations - how long each phase takes (seconds)
    picking_duration_seconds: float = 3.0
    delivery_duration_seconds: float = 3.0

    def with_speed_multiplier(self, multiplier: float) -> "SupplyConfig":
        """Create a new config with adjusted speeds.

        Args:
            multiplier: Speed multiplier (2.0 = twice as fast, 0.5 = half speed)

        Returns:
            New SupplyConfig with adjusted durations
        """
        return SupplyConfig(
            dispatch_interval_seconds=self.dispatch_interval_seconds / multiplier,
            picking_duration_seconds=self.picking_duration_seconds / multiplier,
            delivery_duration_seconds=self.delivery_duration_seconds / multiplier,
        )


# Default supply configurations
SUPPLY_CONFIGS = {
    "normal": SupplyConfig(),
    "fast": SupplyConfig(
        dispatch_interval_seconds=0.5,
        picking_duration_seconds=2.0,
        delivery_duration_seconds=2.0,
    ),
    "slow": SupplyConfig(
        dispatch_interval_seconds=2.0,
        picking_duration_seconds=5.0,
        delivery_duration_seconds=5.0,
    ),
}


def get_supply_config(name: str = "normal") -> SupplyConfig:
    """Get a supply config by name.

    Args:
        name: Config name (normal, fast, slow)

    Returns:
        SupplyConfig

    Raises:
        ValueError: If config name is not found
    """
    if name not in SUPPLY_CONFIGS:
        available = ", ".join(SUPPLY_CONFIGS.keys())
        raise ValueError(f"Unknown supply config '{name}'. Available: {available}")
    return SUPPLY_CONFIGS[name]


@dataclass
class LoadProfile:
    """Configuration for a load generation profile."""

    name: str
    description: str
    orders_per_minute: float
    concurrent_workflows: int
    duration_minutes: Optional[int] = None

    # Activity mix (should sum to 1.0)
    # Balanced so courier capacity can keep up with order creation
    new_order_weight: float = 0.15  # Reduced to let couriers keep up
    status_transition_weight: float = 0.50  # Helps process existing orders
    order_modification_weight: float = 0.10
    customer_creation_weight: float = 0.05
    inventory_update_weight: float = 0.15
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
