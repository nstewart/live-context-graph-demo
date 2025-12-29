"""Tests for load generator proxy endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_list_profiles_success(async_client: AsyncClient):
    """Test listing load generator profiles."""
    mock_profiles = [
        {
            "name": "demo",
            "description": "Demo profile",
            "orders_per_minute": 10.0,
            "concurrent_workflows": 5,
            "duration_minutes": None,
        }
    ]

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_profiles
        mock_response.raise_for_status = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/profiles")

        assert response.status_code == 200
        assert response.json() == mock_profiles


@pytest.mark.asyncio
async def test_get_status_success(async_client: AsyncClient):
    """Test getting load generator status."""
    mock_status = {
        "status": "stopped",
        "profile": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_status
        mock_response.raise_for_status = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["pid"] is None  # Backwards compatibility field


@pytest.mark.asyncio
async def test_get_metrics_success(async_client: AsyncClient):
    """Test getting load generator metrics."""
    mock_metrics = {
        "total_successes": 100,
        "total_failures": 5,
        "success_rate": 95.0,
        "throughput_per_min": 10.5,
        "avg_latency_ms": 250.0,
        "orders_created": 50,
        "status_transitions": 200,
        "customers_created": 25,
        "inventory_updates": 75,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_metrics
        mock_response.raise_for_status = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/metrics")

        assert response.status_code == 200
        assert response.json() == mock_metrics


@pytest.mark.asyncio
async def test_start_loadgen_success(async_client: AsyncClient):
    """Test starting the load generator."""
    mock_status = {
        "status": "running",
        "profile": "demo",
        "started_at": "2024-01-01T00:00:00",
        "duration_minutes": 10,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_status
        mock_response.raise_for_status = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/start", json={
            "profile": "demo",
            "duration_minutes": 10,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["profile"] == "demo"
        assert data["pid"] is None


@pytest.mark.asyncio
async def test_stop_loadgen_success(async_client: AsyncClient):
    """Test stopping the load generator."""
    mock_status = {
        "status": "stopped",
        "profile": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_status
        mock_response.raise_for_status = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


@pytest.mark.asyncio
async def test_service_unavailable(async_client: AsyncClient):
    """Test handling when load generator service is unavailable."""
    import httpx

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection failed")
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/status")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deprecated_output_endpoint(async_client: AsyncClient):
    """Test the deprecated output endpoint."""
    response = await async_client.get("/loadgen/output")

    assert response.status_code == 200
    data = response.json()
    assert "lines" in data
    assert "metrics" in data["lines"][0].lower()
