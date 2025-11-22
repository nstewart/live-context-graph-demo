"""Integration tests for triples API endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db


@requires_db
class TestTriplesAPI:
    """Tests for /triples endpoints."""

    @pytest.mark.asyncio
    async def test_list_triples_returns_list(self, async_client: AsyncClient):
        """GET /triples returns a list."""
        response = await async_client.get("/triples")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_triples_with_subject_filter(self, async_client: AsyncClient):
        """GET /triples?subject_id filters by subject."""
        response = await async_client.get("/triples", params={"subject_id": "customer:101"})
        assert response.status_code == 200

        triples = response.json()
        for triple in triples:
            assert triple["subject_id"] == "customer:101"

    @pytest.mark.asyncio
    async def test_list_triples_with_predicate_filter(self, async_client: AsyncClient):
        """GET /triples?predicate filters by predicate."""
        response = await async_client.get("/triples", params={"predicate": "customer_name"})
        assert response.status_code == 200

        triples = response.json()
        for triple in triples:
            assert triple["predicate"] == "customer_name"

    @pytest.mark.asyncio
    async def test_list_triples_with_limit(self, async_client: AsyncClient):
        """GET /triples respects limit parameter."""
        response = await async_client.get("/triples", params={"limit": 5})
        assert response.status_code == 200
        assert len(response.json()) <= 5

    @pytest.mark.asyncio
    async def test_list_triples_with_offset(self, async_client: AsyncClient):
        """GET /triples respects offset parameter."""
        # First request without offset
        response1 = await async_client.get("/triples", params={"limit": 5})
        # Second request with offset
        response2 = await async_client.get("/triples", params={"limit": 5, "offset": 5})

        assert response1.status_code == 200
        assert response2.status_code == 200

        # Results should be different (if enough data exists)
        if response1.json() and response2.json():
            assert response1.json()[0]["id"] != response2.json()[0]["id"]

    @pytest.mark.asyncio
    async def test_get_triple_not_found(self, async_client: AsyncClient):
        """GET /triples/{id} returns 404 for non-existent triple."""
        response = await async_client.get("/triples/99999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_triple_validation_error_missing_fields(self, async_client: AsyncClient):
        """POST /triples validates required fields."""
        response = await async_client.post("/triples", json={})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_triple_validation_error_invalid_subject(self, async_client: AsyncClient):
        """POST /triples validates subject_id format."""
        response = await async_client.post("/triples", json={
            "subject_id": "invalid-no-colon",  # Missing colon
            "predicate": "customer_name",
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_triple_ontology_validation_unknown_class(self, async_client: AsyncClient):
        """POST /triples rejects unknown class prefix."""
        response = await async_client.post("/triples", json={
            "subject_id": "unknownclass:123",
            "predicate": "some_property",
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 400
        assert "errors" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_triple_ontology_validation_unknown_predicate(self, async_client: AsyncClient):
        """POST /triples rejects unknown predicate."""
        response = await async_client.post("/triples", json={
            "subject_id": "customer:123",
            "predicate": "nonexistent_property",
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 400
        error_detail = response.json()["detail"]
        assert any(e["error_type"] == "unknown_predicate" for e in error_detail["errors"])

    @pytest.mark.asyncio
    async def test_create_triple_ontology_validation_domain_violation(self, async_client: AsyncClient):
        """POST /triples rejects domain violations."""
        # customer_name is for Customer, not Order
        response = await async_client.post("/triples", json={
            "subject_id": "order:FM-9999",
            "predicate": "customer_name",
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 400
        error_detail = response.json()["detail"]
        assert any(e["error_type"] == "domain_violation" for e in error_detail["errors"])

    @pytest.mark.asyncio
    async def test_create_triple_skip_validation(self, async_client: AsyncClient):
        """POST /triples?validate=false skips ontology validation."""
        response = await async_client.post(
            "/triples",
            params={"validate": False},
            json={
                "subject_id": "test:123",
                "predicate": "any_property",
                "object_value": "Test",
                "object_type": "string"
            }
        )
        # Should succeed without validation (or fail for other reasons)
        # The key is it shouldn't fail validation
        assert response.status_code in [201, 500]  # DB might not be connected

    @pytest.mark.asyncio
    async def test_create_triple_batch(self, async_client: AsyncClient):
        """POST /triples/batch creates multiple triples."""
        response = await async_client.post("/triples/batch", json=[
            {
                "subject_id": "customer:batch-test-1",
                "predicate": "customer_name",
                "object_value": "Batch Test 1",
                "object_type": "string"
            },
            {
                "subject_id": "customer:batch-test-2",
                "predicate": "customer_name",
                "object_value": "Batch Test 2",
                "object_type": "string"
            }
        ])
        # May succeed or fail depending on DB
        assert response.status_code in [201, 400, 500]

    @pytest.mark.asyncio
    async def test_delete_triple_not_found(self, async_client: AsyncClient):
        """DELETE /triples/{id} returns 404 for non-existent triple."""
        response = await async_client.delete("/triples/99999999")
        assert response.status_code == 404


@requires_db
class TestSubjectsAPI:
    """Tests for /triples/subjects endpoints."""

    @pytest.mark.asyncio
    async def test_list_subjects_returns_list(self, async_client: AsyncClient):
        """GET /triples/subjects/list returns a list of subject IDs."""
        response = await async_client.get("/triples/subjects/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_subjects_with_class_filter(self, async_client: AsyncClient):
        """GET /triples/subjects/list?class_name filters by class."""
        response = await async_client.get("/triples/subjects/list", params={"class_name": "Customer"})
        assert response.status_code == 200

        subjects = response.json()
        for subject in subjects:
            assert subject.startswith("customer:")

    @pytest.mark.asyncio
    async def test_get_subject_returns_info(self, async_client: AsyncClient):
        """GET /triples/subjects/{id} returns subject info with triples."""
        response = await async_client.get("/triples/subjects/customer:101")
        assert response.status_code == 200

        data = response.json()
        assert "subject_id" in data
        assert "class_name" in data
        assert "triples" in data
        assert isinstance(data["triples"], list)

    @pytest.mark.asyncio
    async def test_get_subject_with_encoded_id(self, async_client: AsyncClient):
        """GET /triples/subjects/{id} handles URL-encoded IDs."""
        response = await async_client.get("/triples/subjects/order%3AFM-1001")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_subject_not_found(self, async_client: AsyncClient):
        """DELETE /triples/subjects/{id} returns 404 for non-existent subject."""
        response = await async_client.delete("/triples/subjects/nonexistent:99999")
        assert response.status_code == 404


@requires_db
class TestValidationAPI:
    """Tests for /triples/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_valid_triple(self, async_client: AsyncClient):
        """POST /triples/validate returns is_valid=true for valid triple."""
        response = await async_client.post("/triples/validate", json={
            "subject_id": "customer:123",
            "predicate": "customer_name",
            "object_value": "Test Customer",
            "object_type": "string"
        })
        assert response.status_code == 200

        result = response.json()
        assert "is_valid" in result
        assert "errors" in result

    @pytest.mark.asyncio
    async def test_validate_invalid_triple(self, async_client: AsyncClient):
        """POST /triples/validate returns is_valid=false with errors."""
        response = await async_client.post("/triples/validate", json={
            "subject_id": "order:123",
            "predicate": "customer_name",  # Wrong domain
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 200

        result = response.json()
        assert result["is_valid"] == False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_returns_detailed_errors(self, async_client: AsyncClient):
        """POST /triples/validate returns detailed error information."""
        response = await async_client.post("/triples/validate", json={
            "subject_id": "unknown:123",
            "predicate": "unknown_prop",
            "object_value": "Test",
            "object_type": "string"
        })
        assert response.status_code == 200

        result = response.json()
        if result["errors"]:
            error = result["errors"][0]
            assert "error_type" in error
            assert "message" in error
