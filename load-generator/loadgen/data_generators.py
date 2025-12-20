"""Realistic data generators for FreshMart load testing."""

import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from faker import Faker

# Initialize Faker
fake = Faker()


class DataGenerator:
    """Generate realistic FreshMart data."""

    def __init__(self, seed: int = None):
        """Initialize data generator.

        Args:
            seed: Random seed for reproducibility
        """
        if seed is not None:
            Faker.seed(seed)
            random.seed(seed)

    def generate_customer_id(self) -> str:
        """Generate a unique customer ID.

        Returns:
            Customer ID in format "customer:UUID"
        """
        return f"customer:{uuid.uuid4()}"

    def generate_order_id(self) -> str:
        """Generate a unique order ID.

        Returns:
            Order ID in format "order:FM-UUID"
        """
        # Use first 8 chars of UUID for readability while maintaining uniqueness
        return f"order:FM-{str(uuid.uuid4())[:8]}"

    def generate_customer_name(self) -> str:
        """Generate a realistic customer name.

        Returns:
            Full name
        """
        return fake.name()

    def generate_customer_email(self, name: str = None) -> str:
        """Generate a realistic email address.

        Args:
            name: Optional name to base email on

        Returns:
            Email address
        """
        if name:
            # Create email from name
            parts = name.lower().split()
            if len(parts) >= 2:
                return f"{parts[0]}.{parts[-1]}@{fake.free_email_domain()}"
        return fake.email()

    def generate_address(self, zone: str = None) -> str:
        """Generate a realistic NYC address.

        Args:
            zone: Optional zone (Manhattan, Brooklyn, Queens)

        Returns:
            Street address
        """
        zones = {
            "Manhattan": ["Upper West Side", "Midtown", "Lower East Side", "Chelsea"],
            "Brooklyn": ["Park Slope", "Williamsburg", "Brooklyn Heights", "DUMBO"],
            "Queens": ["Astoria", "Long Island City", "Forest Hills", "Flushing"],
        }

        if zone and zone in zones:
            neighborhood = random.choice(zones[zone])
        else:
            zone = random.choice(list(zones.keys()))
            neighborhood = random.choice(zones[zone])

        street = fake.street_address()
        return f"{street}, {neighborhood}, {zone}, NY"

    def generate_delivery_window(
        self, hours_from_now: int = None
    ) -> tuple[datetime, datetime]:
        """Generate a realistic delivery window.

        Args:
            hours_from_now: Optional hours from now for window start

        Returns:
            Tuple of (start_time, end_time)
        """
        if hours_from_now is None:
            hours_from_now = random.randint(2, 8)

        start = datetime.now() + timedelta(hours=hours_from_now)
        # Delivery windows are typically 2-4 hours
        window_duration = random.randint(2, 4)
        end = start + timedelta(hours=window_duration)

        return start, end

    def generate_line_items(
        self, products: list[dict[str, Any]], min_items: int = 1, max_items: int = 6
    ) -> list[dict[str, Any]]:
        """Generate realistic order line items.

        Args:
            products: List of available products
            min_items: Minimum number of items
            max_items: Maximum number of items

        Returns:
            List of line items with product_id, quantity, price
        """
        num_items = random.randint(min_items, max_items)
        selected_products = random.sample(products, min(num_items, len(products)))

        line_items = []
        for product in selected_products:
            # Typical quantities: mostly 1-2, occasionally more
            quantity = random.choices(
                [1, 2, 3, 4], weights=[50, 30, 15, 5], k=1
            )[0]

            line_items.append(
                {
                    "product_id": product["product_id"],
                    "quantity": quantity,
                    "price": float(product["unit_price"]) if isinstance(product["unit_price"], str) else product["unit_price"],
                }
            )

        return line_items

    def should_transition_status(
        self,
        current_status: str,
        order_age_minutes: float,
    ) -> tuple[bool, Optional[str]]:
        """Determine if an order should transition to next status.

        Args:
            current_status: Current order status
            order_age_minutes: Minutes since order was created

        Returns:
            Tuple of (should_transition, new_status)
        """
        # Define transition thresholds and probabilities
        transitions = {
            "CREATED": {
                "min_age": 5,  # Minimum 5 minutes
                "max_age": 30,  # Should transition within 30 minutes
                "next_status": "PICKING",
            },
            "PICKING": {
                "min_age": 10,  # Minimum 10 minutes picking
                "max_age": 20,  # Should be done within 20 minutes
                "next_status": "OUT_FOR_DELIVERY",
            },
            "OUT_FOR_DELIVERY": {
                "min_age": 20,  # Minimum 20 minutes delivery
                "max_age": 45,  # Should deliver within 45 minutes
                "next_status": "DELIVERED",
            },
        }

        if current_status not in transitions:
            return False, None

        config = transitions[current_status]

        # Below minimum age, never transition
        if order_age_minutes < config["min_age"]:
            return False, None

        # Above maximum age, always transition
        if order_age_minutes > config["max_age"]:
            return True, config["next_status"]

        # In between: probabilistic transition
        # Probability increases linearly from 0% at min_age to 100% at max_age
        age_range = config["max_age"] - config["min_age"]
        age_progress = (order_age_minutes - config["min_age"]) / age_range
        transition_probability = age_progress * 0.3  # Max 30% chance per check

        if random.random() < transition_probability:
            return True, config["next_status"]

        return False, None

    def should_cancel_order(self, current_status: str) -> bool:
        """Determine if an order should be cancelled.

        Args:
            current_status: Current order status

        Returns:
            True if order should be cancelled
        """
        # Only cancel CREATED or PICKING orders
        if current_status not in ["CREATED", "PICKING"]:
            return False

        # 5% cancellation rate as per product brief
        return random.random() < 0.05

    def generate_inventory_adjustment(
        self, current_quantity: int, is_replenishment: bool = False
    ) -> int:
        """Generate a realistic inventory adjustment.

        Args:
            current_quantity: Current inventory quantity
            is_replenishment: Whether this is a replenishment event

        Returns:
            New quantity value
        """
        if is_replenishment:
            # Replenishment: add significant stock
            adjustment = random.randint(20, 100)
            return current_quantity + adjustment
        else:
            # Random adjustment: small changes
            adjustment = random.randint(-5, 10)
            new_quantity = max(0, current_quantity + adjustment)
            return new_quantity

    def select_random_weighted(
        self, items: list[Any], weights: list[float]
    ) -> Any:
        """Select a random item based on weights.

        Args:
            items: List of items to choose from
            weights: List of weights (should sum to 1.0)

        Returns:
            Selected item
        """
        return random.choices(items, weights=weights, k=1)[0]

    def apply_peak_hours_multiplier(self, base_rate: float) -> float:
        """Apply peak hours multiplier to base rate.

        Args:
            base_rate: Base activity rate

        Returns:
            Adjusted rate based on time of day
        """
        hour = datetime.now().hour

        # Peak hours as per product brief
        if 7 <= hour < 9:  # Morning rush
            return base_rate * 1.5
        elif 11 <= hour < 13:  # Lunch peak
            return base_rate * 2.0
        elif 17 <= hour < 20:  # Dinner rush
            return base_rate * 2.5
        elif 22 <= hour or hour < 6:  # Late night
            return base_rate * 0.3
        else:  # Regular hours
            return base_rate
