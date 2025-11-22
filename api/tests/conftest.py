"""Pytest configuration and fixtures for API tests."""

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.ontology.models import OntologyClass, OntologyProperty
from src.triples.models import Triple


# Check if database is available for integration tests
def is_db_available():
    """Check if database connection is configured."""
    return os.environ.get("DATABASE_URL") or os.environ.get("PG_HOST")


# Skip marker for integration tests when DB not available
requires_db = pytest.mark.skipif(
    not is_db_available(),
    reason="Database not available - set DATABASE_URL or PG_HOST to run integration tests"
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for API testing."""
    # Reset global database engines to avoid connection pool issues
    import src.db.client as db_client
    db_client._pg_engine = None
    db_client._mz_engine = None
    db_client._pg_session_factory = None
    db_client._mz_session_factory = None

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    # Cleanup connections after test
    await db_client.close_connections()


# =============================================================================
# Mock Data Fixtures
# =============================================================================


@pytest.fixture
def sample_ontology_class() -> dict:
    """Sample ontology class data for creation."""
    return {
        "class_name": "TestEntity",
        "prefix": "test_entity",
        "description": "A test entity class for testing",
    }


@pytest.fixture
def sample_ontology_class_model() -> OntologyClass:
    """Sample OntologyClass model instance."""
    from datetime import datetime
    return OntologyClass(
        id=1,
        class_name="Customer",
        prefix="customer",
        description="A customer entity",
        parent_class_id=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_ontology_property() -> dict:
    """Sample ontology property data for creation."""
    return {
        "prop_name": "test_property",
        "domain_class_id": 1,
        "range_kind": "string",
        "is_multi_valued": False,
        "is_required": True,
        "description": "A test property",
    }


@pytest.fixture
def sample_ontology_property_model() -> OntologyProperty:
    """Sample OntologyProperty model instance."""
    from datetime import datetime
    return OntologyProperty(
        id=1,
        prop_name="customer_name",
        domain_class_id=1,
        range_kind="string",
        range_class_id=None,
        is_multi_valued=False,
        is_required=True,
        description="Customer full name",
        domain_class_name="Customer",
        range_class_name=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_triple() -> dict:
    """Sample triple data for creation."""
    return {
        "subject_id": "customer:test-123",
        "predicate": "customer_name",
        "object_value": "Test Customer",
        "object_type": "string",
    }


@pytest.fixture
def sample_triple_model() -> Triple:
    """Sample Triple model instance."""
    from datetime import datetime
    from src.triples.models import ObjectType
    return Triple(
        id=1,
        subject_id="customer:123",
        predicate="customer_name",
        object_value="John Doe",
        object_type=ObjectType.STRING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_order_triple() -> dict:
    """Sample order triple for testing."""
    return {
        "subject_id": "order:FM-TEST-001",
        "predicate": "order_status",
        "object_value": "CREATED",
        "object_type": "string",
    }


@pytest.fixture
def sample_entity_ref_triple() -> dict:
    """Sample entity reference triple for testing."""
    return {
        "subject_id": "order:FM-TEST-001",
        "predicate": "placed_by",
        "object_value": "customer:123",
        "object_type": "entity_ref",
    }


# =============================================================================
# Mock Service Fixtures
# =============================================================================


@pytest.fixture
def mock_ontology_service():
    """Create a mock ontology service."""
    service = AsyncMock()

    # Default return values
    service.list_classes.return_value = []
    service.list_properties.return_value = []
    service.get_class.return_value = None
    service.get_property.return_value = None

    return service


@pytest.fixture
def mock_triple_service():
    """Create a mock triple service."""
    service = AsyncMock()

    service.list_triples.return_value = []
    service.get_triple.return_value = None
    service.list_subjects.return_value = []

    return service


@pytest.fixture
def mock_freshmart_service():
    """Create a mock FreshMart service."""
    service = AsyncMock()

    service.list_orders.return_value = []
    service.get_order.return_value = None
    service.list_stores.return_value = []
    service.list_courier_schedules.return_value = []

    return service


# =============================================================================
# Database Fixtures (for integration tests)
# =============================================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


# =============================================================================
# Test Data Collections
# =============================================================================


@pytest.fixture
def freshmart_demo_classes() -> list[dict]:
    """FreshMart ontology classes for testing."""
    return [
        {"class_name": "Customer", "prefix": "customer", "description": "A customer"},
        {"class_name": "Store", "prefix": "store", "description": "A store location"},
        {"class_name": "Product", "prefix": "product", "description": "A product"},
        {"class_name": "Order", "prefix": "order", "description": "An order"},
        {"class_name": "Courier", "prefix": "courier", "description": "A courier"},
    ]


@pytest.fixture
def freshmart_demo_properties() -> list[dict]:
    """FreshMart ontology properties for testing."""
    return [
        {"prop_name": "customer_name", "domain_class_id": 1, "range_kind": "string", "is_required": True},
        {"prop_name": "customer_email", "domain_class_id": 1, "range_kind": "string", "is_required": False},
        {"prop_name": "order_status", "domain_class_id": 4, "range_kind": "string", "is_required": True},
        {"prop_name": "order_store", "domain_class_id": 4, "range_kind": "entity_ref", "range_class_id": 2},
        {"prop_name": "placed_by", "domain_class_id": 4, "range_kind": "entity_ref", "range_class_id": 1},
    ]
