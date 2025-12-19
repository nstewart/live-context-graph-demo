"""Integration tests for get_store_health tool.

These tests connect to the actual Materialize instance to verify
the tool works end-to-end with real data.
"""

import asyncio
import pytest


@pytest.mark.asyncio
@pytest.mark.integration
async def test_summary_view():
    """Test summary view returns all three metric categories."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({"view": "summary"})

    # Verify structure
    assert "view" in result
    assert result["view"] == "summary"
    assert "error" not in result

    # Verify capacity metrics
    assert "capacity" in result
    assert "total_stores" in result["capacity"]
    assert "critical_stores" in result["capacity"]
    assert "strained_stores" in result["capacity"]
    assert "by_status" in result["capacity"]

    # Verify inventory risk metrics
    assert "inventory_risk" in result
    assert "critical_items" in result["inventory_risk"]
    assert "high_risk_items" in result["inventory_risk"]
    assert "total_revenue_at_risk" in result["inventory_risk"]

    # Verify pricing yield metrics
    assert "pricing_yield" in result
    assert "total_premium" in result["pricing_yield"]
    assert "total_revenue" in result["pricing_yield"]
    assert "yield_percentage" in result["pricing_yield"]

    # Verify recommendations
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)
    assert len(result["recommendations"]) > 0

    print("✓ Summary view test passed")
    print(f"  Stores: {result['capacity']['total_stores']}")
    print(f"  Critical items: {result['inventory_risk']['critical_items']}")
    print(f"  Pricing yield: {result['pricing_yield']['yield_percentage']}%")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_quick_check_view():
    """Test quick_check view for a specific store."""
    from src.tools.tool_get_store_health import get_store_health

    # Test with Brooklyn Store 1
    result = await get_store_health.ainvoke({
        "view": "quick_check",
        "store_id": "store:BK-01"
    })

    # Verify structure
    assert "view" in result
    assert result["view"] == "quick_check"
    assert "error" not in result

    # Verify store info
    assert "store_id" in result
    assert result["store_id"] == "store:BK-01"
    assert "store_name" in result
    assert "store_zone" in result

    # Verify capacity metrics
    assert "capacity" in result
    assert "current_active_orders" in result["capacity"]
    assert "max_capacity" in result["capacity"]
    assert "utilization_pct" in result["capacity"]
    assert "health_status" in result["capacity"]
    assert "recommended_action" in result["capacity"]

    # Verify inventory risk
    assert "inventory_risk" in result
    assert "high_risk_items" in result["inventory_risk"]
    assert "total_revenue_at_risk" in result["inventory_risk"]
    assert "top_risks" in result["inventory_risk"]
    assert isinstance(result["inventory_risk"]["top_risks"], list)

    # Verify recommendations
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)

    print("✓ Quick check view test passed")
    print(f"  Store: {result['store_name']}")
    print(f"  Capacity: {result['capacity']['utilization_pct']}%")
    print(f"  Health: {result['capacity']['health_status']}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_quick_check_missing_store_id():
    """Test quick_check view returns error without store_id."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({"view": "quick_check"})

    # Should return error
    assert "error" in result
    assert "store_id is required" in result["error"]
    assert "recommendations" in result

    print("✓ Quick check error handling test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_capacity_view():
    """Test capacity view returns store utilization."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({
        "view": "capacity",
        "limit": 5
    })

    # Verify structure
    assert "view" in result
    assert result["view"] == "capacity"
    assert "error" not in result

    # Verify stores data
    assert "store_count" in result
    assert "stores" in result
    assert isinstance(result["stores"], list)
    assert len(result["stores"]) <= 5

    # Verify first store has required fields
    if len(result["stores"]) > 0:
        store = result["stores"][0]
        assert "store_id" in store
        assert "store_name" in store
        assert "current_active_orders" in store
        assert "current_utilization_pct" in store
        assert "health_status" in store
        assert "recommended_action" in store

    # Verify recommendations
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)

    print("✓ Capacity view test passed")
    print(f"  Stores returned: {result['store_count']}")
    if result["stores"]:
        print(f"  Top store: {result['stores'][0]['store_name']} at {result['stores'][0]['current_utilization_pct']}%")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_capacity_view_with_store_filter():
    """Test capacity view can filter by store_id."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({
        "view": "capacity",
        "store_id": "store:BK-01"
    })

    # Should return only one store
    assert "stores" in result
    assert len(result["stores"]) == 1
    assert result["stores"][0]["store_id"] == "store:BK-01"

    print("✓ Capacity view filtering test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inventory_risk_view():
    """Test inventory_risk view returns at-risk products."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({
        "view": "inventory_risk",
        "limit": 10
    })

    # Verify structure
    assert "view" in result
    assert result["view"] == "inventory_risk"
    assert "error" not in result

    # Verify items data
    assert "item_count" in result
    assert "total_revenue_at_risk" in result
    assert "items" in result
    assert isinstance(result["items"], list)
    assert len(result["items"]) <= 10

    # Verify first item has required fields (if any items exist)
    if len(result["items"]) > 0:
        item = result["items"][0]
        assert "inventory_id" in item
        assert "product_name" in item
        assert "store_name" in item
        assert "stock_level" in item
        assert "pending_reservations" in item
        assert "revenue_at_risk" in item
        assert "risk_level" in item
        # By default, should only return CRITICAL and HIGH
        assert item["risk_level"] in ["CRITICAL", "HIGH"]

    # Verify recommendations
    assert "recommendations" in result
    assert isinstance(result["recommendations"], list)

    print("✓ Inventory risk view test passed")
    print(f"  Items at risk: {result['item_count']}")
    print(f"  Revenue at risk: ${result['total_revenue_at_risk']}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inventory_risk_with_filters():
    """Test inventory_risk view with store and risk_level filters."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({
        "view": "inventory_risk",
        "store_id": "store:BK-01",
        "risk_level": "CRITICAL",
        "limit": 5
    })

    # All items should be from specified store and risk level
    assert "items" in result
    for item in result["items"]:
        assert item["store_id"] == "store:BK-01"
        assert item["risk_level"] == "CRITICAL"

    print("✓ Inventory risk filtering test passed")
    print(f"  Critical items at Brooklyn: {len(result['items'])}")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_inventory_risk_with_category():
    """Test inventory_risk view with category filter."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({
        "view": "inventory_risk",
        "category": "Produce",
        "limit": 5
    })

    # All items should be from specified category
    assert "items" in result
    for item in result["items"]:
        assert item["category"] == "Produce"

    print("✓ Inventory risk category filtering test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_invalid_view():
    """Test invalid view returns error."""
    from src.tools.tool_get_store_health import get_store_health

    result = await get_store_health.ainvoke({"view": "invalid_view"})

    # Should return error with valid views
    assert "error" in result
    assert "valid_views" in result
    assert "summary" in result["valid_views"]

    print("✓ Invalid view error handling test passed")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_uses_serving_cluster():
    """Test that queries use the serving cluster with indexes."""
    from src.tools.tool_get_store_health import get_store_health
    import asyncpg
    from src.config import get_settings

    # Get a result from the tool
    result = await get_store_health.ainvoke({"view": "summary"})
    assert "error" not in result

    # Verify we can query serving cluster directly
    settings = get_settings()
    conn = await asyncpg.connect(
        host=settings.mz_host,
        port=settings.mz_port,
        user=settings.mz_user,
        password=settings.mz_password,
        database=settings.mz_database,
    )

    try:
        await conn.execute("SET CLUSTER = serving")

        # Verify indexes exist
        indexes = await conn.fetch("""
            SELECT name FROM mz_indexes
            WHERE name IN (
                'pricing_yield_store_idx',
                'inventory_risk_store_idx',
                'inventory_risk_category_idx',
                'store_capacity_store_idx'
            )
        """)

        index_names = [row['name'] for row in indexes]
        assert 'pricing_yield_store_idx' in index_names
        assert 'inventory_risk_store_idx' in index_names
        assert 'inventory_risk_category_idx' in index_names
        assert 'store_capacity_store_idx' in index_names

        print("✓ Serving cluster indexes verified")
        print(f"  Found indexes: {', '.join(index_names)}")

    finally:
        await conn.close()


async def run_all_tests():
    """Run all integration tests."""
    tests = [
        ("Summary View", test_summary_view),
        ("Quick Check View", test_quick_check_view),
        ("Quick Check Error Handling", test_quick_check_missing_store_id),
        ("Capacity View", test_capacity_view),
        ("Capacity View with Filter", test_capacity_view_with_store_filter),
        ("Inventory Risk View", test_inventory_risk_view),
        ("Inventory Risk with Filters", test_inventory_risk_with_filters),
        ("Inventory Risk with Category", test_inventory_risk_with_category),
        ("Invalid View Error", test_invalid_view),
        ("Serving Cluster Indexes", test_uses_serving_cluster),
    ]

    print("\n" + "="*70)
    print("RUNNING GET_STORE_HEALTH INTEGRATION TESTS")
    print("="*70 + "\n")

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            print(f"\nTest: {name}")
            print("-" * 70)
            await test_func()
            passed += 1
        except Exception as e:
            print(f"✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
