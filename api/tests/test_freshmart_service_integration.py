"""Integration tests for FreshMart service with PostgreSQL and Materialize backends.

These tests verify that both read paths work correctly:
- PostgreSQL: Uses regular views (stores_flat, customers_flat, etc.)
- Materialize: Uses materialized views (stores_mv, customers_mv, etc.)
"""

import os
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.freshmart.service import FreshMartService
from src.config import get_settings


def is_pg_available():
    """Check if PostgreSQL is available."""
    return os.environ.get("DATABASE_URL") or os.environ.get("PG_HOST")


def is_mz_available():
    """Check if Materialize is available."""
    return os.environ.get("MZ_HOST") or os.environ.get("MATERIALIZE_URL")


requires_pg = pytest.mark.skipif(
    not is_pg_available(),
    reason="PostgreSQL not available - set DATABASE_URL or PG_HOST"
)

requires_mz = pytest.mark.skipif(
    not is_mz_available(),
    reason="Materialize not available - set MZ_HOST or MATERIALIZE_URL"
)


# =============================================================================
# PostgreSQL Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def pg_session():
    """Create PostgreSQL session for testing."""
    get_settings.cache_clear()
    settings = get_settings()

    engine = create_async_engine(
        settings.pg_dsn,
        echo=False,
        pool_pre_ping=True,
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def pg_service(pg_session: AsyncSession):
    """Create FreshMart service with PostgreSQL backend."""
    return FreshMartService(pg_session, use_materialize=False)


# =============================================================================
# Materialize Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def mz_session():
    """Create Materialize session for testing."""
    get_settings.cache_clear()
    settings = get_settings()

    # Patch the asyncpg dialect to skip JSON codec setup for Materialize
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

    original_setup_json = PGDialect_asyncpg.setup_asyncpg_json_codec
    original_setup_jsonb = PGDialect_asyncpg.setup_asyncpg_jsonb_codec

    async def noop_setup_json(self, conn):
        pass

    async def noop_setup_jsonb(self, conn):
        pass

    # Temporarily patch the dialect
    PGDialect_asyncpg.setup_asyncpg_json_codec = noop_setup_json
    PGDialect_asyncpg.setup_asyncpg_jsonb_codec = noop_setup_jsonb

    try:
        engine = create_async_engine(
            settings.mz_dsn,
            echo=False,
            pool_pre_ping=True,
            connect_args={
                # Disable asyncpg's prepared statement cache (Materialize compatibility)
                "prepared_statement_cache_size": 0,
            },
        )
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with factory() as session:
            # Use the serving cluster for indexed queries
            await session.execute(text("SET CLUSTER = serving"))
            yield session

        await engine.dispose()
    finally:
        # Restore original methods
        PGDialect_asyncpg.setup_asyncpg_json_codec = original_setup_json
        PGDialect_asyncpg.setup_asyncpg_jsonb_codec = original_setup_jsonb


@pytest_asyncio.fixture
async def mz_service(mz_session: AsyncSession):
    """Create FreshMart service with Materialize backend."""
    return FreshMartService(mz_session, use_materialize=True)


# =============================================================================
# PostgreSQL Tests
# =============================================================================


@requires_pg
class TestPostgreSQLReadPath:
    """Test FreshMart queries using PostgreSQL views."""

    @pytest.mark.asyncio
    async def test_list_stores_returns_data(self, pg_service: FreshMartService):
        """list_stores returns stores from PostgreSQL."""
        stores = await pg_service.list_stores()

        assert isinstance(stores, list)
        # Demo data should have stores
        if stores:
            store = stores[0]
            assert store.store_id is not None
            assert store.store_id.startswith("store:")

    @pytest.mark.asyncio
    async def test_list_stores_includes_inventory(self, pg_service: FreshMartService):
        """list_stores includes inventory_items for each store."""
        stores = await pg_service.list_stores()

        assert isinstance(stores, list)
        for store in stores:
            assert hasattr(store, "inventory_items")
            assert isinstance(store.inventory_items, list)
            # Inventory items should have proper structure
            for item in store.inventory_items:
                assert item.inventory_id is not None
                assert item.store_id == store.store_id

    @pytest.mark.asyncio
    async def test_get_store_returns_store_with_inventory(self, pg_service: FreshMartService):
        """get_store returns single store with inventory."""
        # First get list to find a store ID
        stores = await pg_service.list_stores()
        if not stores:
            pytest.skip("No stores in database")

        store_id = stores[0].store_id
        store = await pg_service.get_store(store_id)

        assert store is not None
        assert store.store_id == store_id
        assert hasattr(store, "inventory_items")

    @pytest.mark.asyncio
    async def test_list_orders_returns_data(self, pg_service: FreshMartService):
        """list_orders returns orders from PostgreSQL."""
        orders = await pg_service.list_orders()

        assert isinstance(orders, list)
        if orders:
            order = orders[0]
            assert order.order_id is not None
            assert order.order_id.startswith("order:")

    @pytest.mark.asyncio
    async def test_list_orders_with_filter(self, pg_service: FreshMartService):
        """list_orders filters correctly."""
        from src.freshmart.models import OrderFilter

        filter_ = OrderFilter(status="CREATED")
        orders = await pg_service.list_orders(filter_=filter_)

        assert isinstance(orders, list)
        for order in orders:
            assert order.order_status == "CREATED"

    @pytest.mark.asyncio
    async def test_list_customers_returns_data(self, pg_service: FreshMartService):
        """list_customers returns customers from PostgreSQL."""
        customers = await pg_service.list_customers()

        assert isinstance(customers, list)
        if customers:
            customer = customers[0]
            assert customer.customer_id is not None
            assert customer.customer_id.startswith("customer:")

    @pytest.mark.asyncio
    async def test_list_products_returns_data(self, pg_service: FreshMartService):
        """list_products returns products from PostgreSQL."""
        products = await pg_service.list_products()

        assert isinstance(products, list)
        if products:
            product = products[0]
            assert product.product_id is not None
            assert product.product_id.startswith("product:")

    @pytest.mark.asyncio
    async def test_list_courier_schedules_returns_data(self, pg_service: FreshMartService):
        """list_courier_schedules returns couriers from PostgreSQL."""
        couriers = await pg_service.list_courier_schedules()

        assert isinstance(couriers, list)
        if couriers:
            courier = couriers[0]
            assert courier.courier_id is not None
            assert courier.courier_id.startswith("courier:")
            assert hasattr(courier, "tasks")

    @pytest.mark.asyncio
    async def test_list_store_inventory_returns_data(self, pg_service: FreshMartService):
        """list_store_inventory returns inventory from PostgreSQL."""
        inventory = await pg_service.list_store_inventory()

        assert isinstance(inventory, list)
        if inventory:
            item = inventory[0]
            assert item.inventory_id is not None
            assert item.inventory_id.startswith("inventory:")


# =============================================================================
# Materialize Tests
# =============================================================================


@requires_mz
class TestMaterializeReadPath:
    """Test FreshMart queries using Materialize materialized views."""

    @pytest.mark.asyncio
    async def test_list_stores_returns_data(self, mz_service: FreshMartService):
        """list_stores returns stores from Materialize."""
        stores = await mz_service.list_stores()

        assert isinstance(stores, list)
        if stores:
            store = stores[0]
            assert store.store_id is not None
            assert store.store_id.startswith("store:")

    @pytest.mark.asyncio
    async def test_list_stores_includes_inventory(self, mz_service: FreshMartService):
        """list_stores includes inventory_items for each store."""
        stores = await mz_service.list_stores()

        assert isinstance(stores, list)
        for store in stores:
            assert hasattr(store, "inventory_items")
            assert isinstance(store.inventory_items, list)
            for item in store.inventory_items:
                assert item.inventory_id is not None
                assert item.store_id == store.store_id

    @pytest.mark.asyncio
    async def test_get_store_returns_store_with_inventory(self, mz_service: FreshMartService):
        """get_store returns single store with inventory."""
        stores = await mz_service.list_stores()
        if not stores:
            pytest.skip("No stores in database")

        store_id = stores[0].store_id
        store = await mz_service.get_store(store_id)

        assert store is not None
        assert store.store_id == store_id
        assert hasattr(store, "inventory_items")

    @pytest.mark.asyncio
    async def test_list_orders_returns_data(self, mz_service: FreshMartService):
        """list_orders returns orders from Materialize."""
        orders = await mz_service.list_orders()

        assert isinstance(orders, list)
        if orders:
            order = orders[0]
            assert order.order_id is not None
            assert order.order_id.startswith("order:")

    @pytest.mark.asyncio
    async def test_list_orders_with_filter(self, mz_service: FreshMartService):
        """list_orders filters correctly."""
        from src.freshmart.models import OrderFilter

        filter_ = OrderFilter(status="CREATED")
        orders = await mz_service.list_orders(filter_=filter_)

        assert isinstance(orders, list)
        for order in orders:
            assert order.order_status == "CREATED"

    @pytest.mark.asyncio
    async def test_list_customers_returns_data(self, mz_service: FreshMartService):
        """list_customers returns customers from Materialize."""
        customers = await mz_service.list_customers()

        assert isinstance(customers, list)
        if customers:
            customer = customers[0]
            assert customer.customer_id is not None
            assert customer.customer_id.startswith("customer:")

    @pytest.mark.asyncio
    async def test_list_products_returns_data(self, mz_service: FreshMartService):
        """list_products returns products from Materialize."""
        products = await mz_service.list_products()

        assert isinstance(products, list)
        if products:
            product = products[0]
            assert product.product_id is not None
            assert product.product_id.startswith("product:")

    @pytest.mark.asyncio
    async def test_list_courier_schedules_returns_data(self, mz_service: FreshMartService):
        """list_courier_schedules returns couriers from Materialize."""
        couriers = await mz_service.list_courier_schedules()

        assert isinstance(couriers, list)
        if couriers:
            courier = couriers[0]
            assert courier.courier_id is not None
            assert courier.courier_id.startswith("courier:")
            assert hasattr(courier, "tasks")

    @pytest.mark.asyncio
    async def test_list_store_inventory_returns_data(self, mz_service: FreshMartService):
        """list_store_inventory returns inventory from Materialize."""
        inventory = await mz_service.list_store_inventory()

        assert isinstance(inventory, list)
        if inventory:
            item = inventory[0]
            assert item.inventory_id is not None
            assert item.inventory_id.startswith("inventory:")


# =============================================================================
# Cross-Backend Consistency Tests
# =============================================================================


@requires_pg
@requires_mz
class TestCrossBackendConsistency:
    """Test that PostgreSQL and Materialize return consistent data."""

    @pytest.mark.asyncio
    async def test_stores_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same stores."""
        pg_stores = await pg_service.list_stores()
        mz_stores = await mz_service.list_stores()

        pg_store_ids = sorted([s.store_id for s in pg_stores])
        mz_store_ids = sorted([s.store_id for s in mz_stores])

        assert pg_store_ids == mz_store_ids, "Store IDs should match between backends"

    @pytest.mark.asyncio
    async def test_customers_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same customers."""
        pg_customers = await pg_service.list_customers()
        mz_customers = await mz_service.list_customers()

        pg_customer_ids = sorted([c.customer_id for c in pg_customers])
        mz_customer_ids = sorted([c.customer_id for c in mz_customers])

        assert pg_customer_ids == mz_customer_ids, "Customer IDs should match between backends"

    @pytest.mark.asyncio
    async def test_products_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same products."""
        pg_products = await pg_service.list_products()
        mz_products = await mz_service.list_products()

        pg_product_ids = sorted([p.product_id for p in pg_products])
        mz_product_ids = sorted([p.product_id for p in mz_products])

        assert pg_product_ids == mz_product_ids, "Product IDs should match between backends"

    @pytest.mark.asyncio
    async def test_orders_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same orders."""
        pg_orders = await pg_service.list_orders(limit=100)
        mz_orders = await mz_service.list_orders(limit=100)

        pg_order_ids = sorted([o.order_id for o in pg_orders])
        mz_order_ids = sorted([o.order_id for o in mz_orders])

        assert pg_order_ids == mz_order_ids, "Order IDs should match between backends"

    @pytest.mark.asyncio
    async def test_couriers_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same couriers."""
        pg_couriers = await pg_service.list_courier_schedules()
        mz_couriers = await mz_service.list_courier_schedules()

        pg_courier_ids = sorted([c.courier_id for c in pg_couriers])
        mz_courier_ids = sorted([c.courier_id for c in mz_couriers])

        assert pg_courier_ids == mz_courier_ids, "Courier IDs should match between backends"

    @pytest.mark.asyncio
    async def test_inventory_match_between_backends(
        self, pg_service: FreshMartService, mz_service: FreshMartService
    ):
        """Both backends return the same inventory."""
        pg_inventory = await pg_service.list_store_inventory(limit=1000)
        mz_inventory = await mz_service.list_store_inventory(limit=1000)

        pg_inventory_ids = sorted([i.inventory_id for i in pg_inventory])
        mz_inventory_ids = sorted([i.inventory_id for i in mz_inventory])

        assert pg_inventory_ids == mz_inventory_ids, "Inventory IDs should match between backends"


# =============================================================================
# View Mapping Tests
# =============================================================================


class TestViewMapping:
    """Test that FreshMartService correctly maps view names."""

    def test_pg_view_mapping(self):
        """PostgreSQL uses base view names."""
        from unittest.mock import MagicMock

        service = FreshMartService(MagicMock(), use_materialize=False)

        assert service._get_view("stores_flat") == "stores_flat"
        assert service._get_view("customers_flat") == "customers_flat"
        assert service._get_view("products_flat") == "products_flat"
        assert service._get_view("orders_search_source") == "orders_search_source"
        assert service._get_view("store_inventory_flat") == "store_inventory_flat"
        assert service._get_view("courier_schedule_flat") == "courier_schedule_flat"

    def test_mz_view_mapping(self):
        """Materialize uses _mv suffixed view names."""
        from unittest.mock import MagicMock

        service = FreshMartService(MagicMock(), use_materialize=True)

        assert service._get_view("stores_flat") == "stores_mv"
        assert service._get_view("customers_flat") == "customers_mv"
        assert service._get_view("products_flat") == "products_mv"
        assert service._get_view("orders_search_source") == "orders_search_source_mv"
        assert service._get_view("store_inventory_flat") == "store_inventory_mv"
        assert service._get_view("courier_schedule_flat") == "courier_schedule_mv"
