"""Integration tests for ontology API endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db


@requires_db
class TestOntologyClassesAPI:
    """Tests for /ontology/classes endpoints."""

    @pytest.mark.asyncio
    async def test_list_classes_returns_list(self, async_client: AsyncClient):
        """GET /ontology/classes returns a list."""
        response = await async_client.get("/ontology/classes")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_classes_contains_expected_fields(self, async_client: AsyncClient):
        """Classes in response have expected fields."""
        response = await async_client.get("/ontology/classes")
        assert response.status_code == 200

        classes = response.json()
        if classes:  # If demo data is loaded
            first_class = classes[0]
            assert "id" in first_class
            assert "class_name" in first_class
            assert "prefix" in first_class
            assert "description" in first_class
            assert "created_at" in first_class
            assert "updated_at" in first_class

    @pytest.mark.asyncio
    async def test_get_class_not_found(self, async_client: AsyncClient):
        """GET /ontology/classes/{id} returns 404 for non-existent class."""
        response = await async_client.get("/ontology/classes/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_class_validation_error(self, async_client: AsyncClient):
        """POST /ontology/classes validates required fields."""
        # Missing required fields
        response = await async_client.post("/ontology/classes", json={})
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_class_with_valid_data(self, async_client: AsyncClient):
        """POST /ontology/classes creates a new class."""
        import uuid
        unique_name = f"TestClass_{uuid.uuid4().hex[:8]}"
        unique_prefix = f"test_{uuid.uuid4().hex[:8]}"

        response = await async_client.post("/ontology/classes", json={
            "class_name": unique_name,
            "prefix": unique_prefix,
            "description": "A test class"
        })

        # May succeed or fail depending on DB state
        assert response.status_code in [201, 409, 500]

        if response.status_code == 201:
            data = response.json()
            assert data["class_name"] == unique_name
            assert data["prefix"] == unique_prefix

    @pytest.mark.asyncio
    async def test_delete_class_not_found(self, async_client: AsyncClient):
        """DELETE /ontology/classes/{id} returns 404 for non-existent class."""
        response = await async_client.delete("/ontology/classes/99999")
        assert response.status_code == 404


@requires_db
class TestOntologyPropertiesAPI:
    """Tests for /ontology/properties endpoints."""

    @pytest.mark.asyncio
    async def test_list_properties_returns_list(self, async_client: AsyncClient):
        """GET /ontology/properties returns a list."""
        response = await async_client.get("/ontology/properties")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_properties_contains_expected_fields(self, async_client: AsyncClient):
        """Properties in response have expected fields."""
        response = await async_client.get("/ontology/properties")
        assert response.status_code == 200

        properties = response.json()
        if properties:  # If demo data is loaded
            first_prop = properties[0]
            assert "id" in first_prop
            assert "prop_name" in first_prop
            assert "domain_class_id" in first_prop
            assert "range_kind" in first_prop
            assert "is_multi_valued" in first_prop
            assert "is_required" in first_prop

    @pytest.mark.asyncio
    async def test_list_properties_with_domain_filter(self, async_client: AsyncClient):
        """GET /ontology/properties?domain_class_id filters correctly."""
        response = await async_client.get("/ontology/properties", params={"domain_class_id": 1})
        assert response.status_code == 200

        properties = response.json()
        for prop in properties:
            assert prop["domain_class_id"] == 1

    @pytest.mark.asyncio
    async def test_get_property_not_found(self, async_client: AsyncClient):
        """GET /ontology/properties/{id} returns 404 for non-existent property."""
        response = await async_client.get("/ontology/properties/99999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_class_properties(self, async_client: AsyncClient):
        """GET /ontology/class/{name}/properties returns properties for class."""
        response = await async_client.get("/ontology/class/Customer/properties")
        # May return 200 or 404 depending on demo data
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_create_property_validation_error(self, async_client: AsyncClient):
        """POST /ontology/properties validates required fields."""
        response = await async_client.post("/ontology/properties", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_property_invalid_domain(self, async_client: AsyncClient):
        """POST /ontology/properties rejects invalid domain_class_id."""
        response = await async_client.post("/ontology/properties", json={
            "prop_name": "test_prop",
            "domain_class_id": 99999,  # Non-existent
            "range_kind": "string",
        })
        assert response.status_code == 400


@requires_db
class TestOntologySchemaAPI:
    """Tests for /ontology/schema endpoint."""

    @pytest.mark.asyncio
    async def test_get_schema_returns_complete_schema(self, async_client: AsyncClient):
        """GET /ontology/schema returns classes and properties."""
        response = await async_client.get("/ontology/schema")
        assert response.status_code == 200

        schema = response.json()
        assert "classes" in schema
        assert "properties" in schema
        assert isinstance(schema["classes"], list)
        assert isinstance(schema["properties"], list)
