"""Tests for data generators."""

import pytest

from loadgen.data_generators import DataGenerator


def test_generate_customer_id():
    """Test customer ID generation."""
    generator = DataGenerator()
    customer_id = generator.generate_customer_id()
    assert customer_id.startswith("customer:")
    assert len(customer_id) > len("customer:")


def test_generate_order_id():
    """Test order ID generation."""
    generator = DataGenerator()
    order_id = generator.generate_order_id()
    assert order_id.startswith("order:FM-")
    assert len(order_id) > len("order:FM-")


def test_generate_customer_name():
    """Test customer name generation."""
    generator = DataGenerator()
    name = generator.generate_customer_name()
    assert len(name) > 0
    assert " " in name  # Should have first and last name


def test_generate_customer_email():
    """Test email generation."""
    generator = DataGenerator()
    email = generator.generate_customer_email()
    assert "@" in email
    assert "." in email


def test_generate_customer_email_from_name():
    """Test email generation from name."""
    generator = DataGenerator()
    email = generator.generate_customer_email("John Doe")
    assert "@" in email
    assert "john" in email.lower()


def test_generate_address():
    """Test address generation."""
    generator = DataGenerator()
    address = generator.generate_address()
    assert "NY" in address


def test_generate_address_with_zone():
    """Test address generation with specific zone."""
    generator = DataGenerator()
    address = generator.generate_address("Manhattan")
    assert "Manhattan" in address
    assert "NY" in address


def test_generate_delivery_window():
    """Test delivery window generation."""
    generator = DataGenerator()
    start, end = generator.generate_delivery_window()
    assert end > start
    assert (end - start).total_seconds() >= 7200  # At least 2 hours


def test_generate_line_items(sample_products):
    """Test line items generation."""
    generator = DataGenerator()
    line_items = generator.generate_line_items(sample_products, min_items=1, max_items=3)

    assert len(line_items) >= 1
    assert len(line_items) <= 3

    for item in line_items:
        assert "product_id" in item
        assert "quantity" in item
        assert "price" in item
        assert item["quantity"] >= 1


def test_should_transition_status_created():
    """Test status transition logic for CREATED orders."""
    generator = DataGenerator()

    # Young order should not transition
    should_transition, new_status = generator.should_transition_status("CREATED", 2.0)
    assert not should_transition

    # Old order should transition
    should_transition, new_status = generator.should_transition_status("CREATED", 35.0)
    assert should_transition
    assert new_status == "PICKING"


def test_should_transition_status_picking():
    """Test status transition logic for PICKING orders."""
    generator = DataGenerator()

    # Young order should not transition
    should_transition, new_status = generator.should_transition_status("PICKING", 5.0)
    assert not should_transition

    # Old order should transition
    should_transition, new_status = generator.should_transition_status("PICKING", 25.0)
    assert should_transition
    assert new_status == "OUT_FOR_DELIVERY"


def test_should_transition_status_out_for_delivery():
    """Test status transition logic for OUT_FOR_DELIVERY orders."""
    generator = DataGenerator()

    # Young order should not transition
    should_transition, new_status = generator.should_transition_status(
        "OUT_FOR_DELIVERY", 10.0
    )
    assert not should_transition

    # Old order should transition
    should_transition, new_status = generator.should_transition_status(
        "OUT_FOR_DELIVERY", 50.0
    )
    assert should_transition
    assert new_status == "DELIVERED"


def test_should_transition_status_delivered():
    """Test that DELIVERED orders don't transition."""
    generator = DataGenerator()
    should_transition, new_status = generator.should_transition_status("DELIVERED", 100.0)
    assert not should_transition
    assert new_status is None


def test_should_cancel_order():
    """Test order cancellation logic."""
    generator = DataGenerator(seed=42)

    # Test with multiple attempts (statistical test)
    cancellations = 0
    attempts = 1000

    for _ in range(attempts):
        if generator.should_cancel_order("CREATED"):
            cancellations += 1

    # Should be around 5% (50 out of 1000)
    # Allow some variance: 30-70 cancellations
    assert 30 <= cancellations <= 70


def test_generate_inventory_adjustment():
    """Test inventory adjustment generation."""
    generator = DataGenerator()

    # Test regular adjustment
    new_qty = generator.generate_inventory_adjustment(50, is_replenishment=False)
    assert new_qty >= 0  # Never negative

    # Test replenishment
    new_qty = generator.generate_inventory_adjustment(10, is_replenishment=True)
    assert new_qty > 10  # Should increase


def test_select_random_weighted():
    """Test weighted random selection."""
    generator = DataGenerator(seed=42)
    items = ["a", "b", "c"]
    weights = [0.5, 0.3, 0.2]

    # Test multiple selections (statistical test)
    selections = [generator.select_random_weighted(items, weights) for _ in range(1000)]

    # Count occurrences
    counts = {item: selections.count(item) for item in items}

    # "a" should be most common (around 500)
    assert counts["a"] > counts["b"]
    assert counts["b"] > counts["c"]


def test_apply_peak_hours_multiplier():
    """Test peak hours multiplier."""
    generator = DataGenerator()
    base_rate = 10.0

    # Test that multiplier affects rate
    adjusted_rate = generator.apply_peak_hours_multiplier(base_rate)
    assert adjusted_rate > 0


def test_seed_reproducibility():
    """Test that seed produces reproducible results."""
    gen1 = DataGenerator(seed=42)
    gen2 = DataGenerator(seed=42)

    # Generate same sequence
    for _ in range(10):
        id1 = gen1.generate_customer_id()
        id2 = gen2.generate_customer_id()
        assert id1 == id2
