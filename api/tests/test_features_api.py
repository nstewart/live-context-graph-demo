"""Features API tests."""

import os
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_bundling_feature_disabled_by_default(async_client: AsyncClient):
    """Test bundling feature returns disabled when env var is not set."""
    with patch.dict(os.environ, {"ENABLE_DELIVERY_BUNDLING": "false"}):
        response = await async_client.get("/api/features/bundling")
        assert response.status_code == 200
        data = response.json()
        assert data["feature"] == "delivery_bundling"
        assert data["enabled"] is False
        assert data["enable_command"] == "make up-agent-bundling"


@pytest.mark.asyncio
async def test_bundling_feature_enabled(async_client: AsyncClient):
    """Test bundling feature returns enabled when env var is set."""
    with patch.dict(os.environ, {"ENABLE_DELIVERY_BUNDLING": "true"}):
        response = await async_client.get("/api/features/bundling")
        assert response.status_code == 200
        data = response.json()
        assert data["feature"] == "delivery_bundling"
        assert data["enabled"] is True
        assert data["enable_command"] is None


@pytest.mark.asyncio
async def test_list_features(async_client: AsyncClient):
    """Test list features endpoint."""
    response = await async_client.get("/api/features")
    assert response.status_code == 200
    data = response.json()
    assert "features" in data
    assert "delivery_bundling" in data["features"]
    assert "enabled" in data["features"]["delivery_bundling"]
    assert "description" in data["features"]["delivery_bundling"]
    assert data["features"]["delivery_bundling"]["cpu_intensive"] is True


@pytest.mark.asyncio
async def test_bundling_feature_case_insensitive(async_client: AsyncClient):
    """Test that ENABLE_DELIVERY_BUNDLING is case insensitive."""
    with patch.dict(os.environ, {"ENABLE_DELIVERY_BUNDLING": "TRUE"}):
        response = await async_client.get("/api/features/bundling")
        assert response.status_code == 200
        assert response.json()["enabled"] is True

    with patch.dict(os.environ, {"ENABLE_DELIVERY_BUNDLING": "True"}):
        response = await async_client.get("/api/features/bundling")
        assert response.status_code == 200
        assert response.json()["enabled"] is True
