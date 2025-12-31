"""Tests for load generator proxy endpoints."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch


def create_mock_response(json_data):
    """Create a properly mocked httpx response."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()
    return mock_response


# ============== Profile & Config Tests ==============

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
        mock_instance.get.return_value = create_mock_response(mock_profiles)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/profiles")

        assert response.status_code == 200
        assert response.json() == mock_profiles


@pytest.mark.asyncio
async def test_list_supply_configs_success(async_client: AsyncClient):
    """Test listing supply configurations."""
    mock_configs = [
        {
            "name": "normal",
            "dispatch_interval_seconds": 1.0,
            "picking_duration_seconds": 3.0,
            "delivery_duration_seconds": 3.0,
        },
        {
            "name": "fast",
            "dispatch_interval_seconds": 0.5,
            "picking_duration_seconds": 2.0,
            "delivery_duration_seconds": 2.0,
        },
    ]

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_configs)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/supply-configs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "normal"
        assert data[1]["name"] == "fast"


# ============== Demand Endpoint Tests ==============

@pytest.mark.asyncio
async def test_get_demand_status_success(async_client: AsyncClient):
    """Test getting demand generator status."""
    mock_status = {
        "status": "stopped",
        "profile": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/demand/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["profile"] is None


@pytest.mark.asyncio
async def test_get_demand_metrics_success(async_client: AsyncClient):
    """Test getting demand generator metrics."""
    mock_metrics = {
        "total_successes": 100,
        "total_failures": 5,
        "success_rate": 95.0,
        "throughput_per_min": 10.5,
        "avg_latency_ms": 250.0,
        "orders_created": 50,
        "customers_created": 25,
        "inventory_updates": 75,
        "cancellations": 10,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_metrics)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/demand/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_successes"] == 100
        assert data["orders_created"] == 50
        assert data["cancellations"] == 10


@pytest.mark.asyncio
async def test_start_demand_success(async_client: AsyncClient):
    """Test starting the demand generator."""
    mock_status = {
        "status": "running",
        "profile": "demo",
        "started_at": "2024-01-01T00:00:00",
        "duration_minutes": 10,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/demand/start", json={
            "profile": "demo",
            "duration_minutes": 10,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["profile"] == "demo"


@pytest.mark.asyncio
async def test_stop_demand_success(async_client: AsyncClient):
    """Test stopping the demand generator."""
    mock_status = {
        "status": "stopped",
        "profile": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/demand/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


# ============== Supply Endpoint Tests ==============

@pytest.mark.asyncio
async def test_get_supply_status_success(async_client: AsyncClient):
    """Test getting supply generator status."""
    mock_status = {
        "status": "stopped",
        "supply_config": None,
        "dispatch_interval_seconds": None,
        "picking_duration_seconds": None,
        "delivery_duration_seconds": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/supply/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"
        assert data["supply_config"] is None


@pytest.mark.asyncio
async def test_get_supply_metrics_success(async_client: AsyncClient):
    """Test getting supply generator metrics."""
    mock_metrics = {
        "total_successes": 50,
        "dispatch_assigns": 30,
        "dispatch_completes": 25,
        "throughput_per_min": 5.0,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_metrics)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/supply/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["total_successes"] == 50
        assert data["dispatch_assigns"] == 30
        assert data["dispatch_completes"] == 25


@pytest.mark.asyncio
async def test_start_supply_success(async_client: AsyncClient):
    """Test starting the supply generator."""
    mock_status = {
        "status": "running",
        "supply_config": "normal",
        "dispatch_interval_seconds": 1.0,
        "picking_duration_seconds": 3.0,
        "delivery_duration_seconds": 3.0,
        "started_at": "2024-01-01T00:00:00",
        "duration_minutes": 10,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/supply/start", json={
            "profile": "demo",
            "supply_config": "normal",
            "duration_minutes": 10,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["supply_config"] == "normal"
        assert data["dispatch_interval_seconds"] == 1.0


@pytest.mark.asyncio
async def test_start_supply_with_custom_config(async_client: AsyncClient):
    """Test starting the supply generator with custom timing config."""
    mock_status = {
        "status": "running",
        "supply_config": "normal",
        "dispatch_interval_seconds": 0.5,
        "picking_duration_seconds": 1.0,
        "delivery_duration_seconds": 1.0,
        "started_at": "2024-01-01T00:00:00",
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/supply/start", json={
            "supply_config": "normal",
            "dispatch_interval_seconds": 0.5,
            "picking_duration_seconds": 1.0,
            "delivery_duration_seconds": 1.0,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["dispatch_interval_seconds"] == 0.5
        assert data["picking_duration_seconds"] == 1.0


@pytest.mark.asyncio
async def test_stop_supply_success(async_client: AsyncClient):
    """Test stopping the supply generator."""
    mock_status = {
        "status": "stopped",
        "supply_config": None,
        "dispatch_interval_seconds": None,
        "picking_duration_seconds": None,
        "delivery_duration_seconds": None,
        "started_at": None,
        "duration_minutes": None,
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/supply/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "stopped"


# ============== Combined Endpoint Tests ==============

@pytest.mark.asyncio
async def test_get_combined_status_success(async_client: AsyncClient):
    """Test getting combined status of both generators."""
    mock_status = {
        "demand": {
            "status": "running",
            "profile": "demo",
            "started_at": "2024-01-01T00:00:00",
            "duration_minutes": 10,
        },
        "supply": {
            "status": "stopped",
            "supply_config": None,
            "dispatch_interval_seconds": None,
            "picking_duration_seconds": None,
            "delivery_duration_seconds": None,
            "started_at": None,
            "duration_minutes": None,
        },
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/status")

        assert response.status_code == 200
        data = response.json()
        assert "demand" in data
        assert "supply" in data
        assert data["demand"]["status"] == "running"
        assert data["supply"]["status"] == "stopped"


@pytest.mark.asyncio
async def test_get_combined_metrics_success(async_client: AsyncClient):
    """Test getting combined metrics from both generators."""
    mock_metrics = {
        "demand": {
            "total_successes": 100,
            "total_failures": 5,
            "success_rate": 95.0,
            "throughput_per_min": 10.5,
            "avg_latency_ms": 250.0,
            "orders_created": 50,
            "customers_created": 25,
            "inventory_updates": 75,
            "cancellations": 10,
        },
        "supply": {
            "total_successes": 50,
            "dispatch_assigns": 30,
            "dispatch_completes": 25,
            "throughput_per_min": 5.0,
        },
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = create_mock_response(mock_metrics)
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "demand" in data
        assert "supply" in data
        assert data["demand"]["orders_created"] == 50
        assert data["supply"]["dispatch_assigns"] == 30


@pytest.mark.asyncio
async def test_start_both_success(async_client: AsyncClient):
    """Test starting both generators."""
    mock_status = {
        "demand": {
            "status": "running",
            "profile": "demo",
            "started_at": "2024-01-01T00:00:00",
            "duration_minutes": 10,
        },
        "supply": {
            "status": "running",
            "supply_config": "normal",
            "dispatch_interval_seconds": 1.0,
            "picking_duration_seconds": 3.0,
            "delivery_duration_seconds": 3.0,
            "started_at": "2024-01-01T00:00:00",
            "duration_minutes": 10,
        },
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/start", json={
            "profile": "demo",
            "supply_config": "normal",
            "duration_minutes": 10,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["demand"]["status"] == "running"
        assert data["supply"]["status"] == "running"


@pytest.mark.asyncio
async def test_stop_both_success(async_client: AsyncClient):
    """Test stopping both generators."""
    mock_status = {
        "demand": {
            "status": "stopped",
            "profile": None,
            "started_at": None,
            "duration_minutes": None,
        },
        "supply": {
            "status": "stopped",
            "supply_config": None,
            "dispatch_interval_seconds": None,
            "picking_duration_seconds": None,
            "delivery_duration_seconds": None,
            "started_at": None,
            "duration_minutes": None,
        },
    }

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = create_mock_response(mock_status)
        mock_client.return_value = mock_instance

        response = await async_client.post("/loadgen/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["demand"]["status"] == "stopped"
        assert data["supply"]["status"] == "stopped"


# ============== Error Handling Tests ==============

@pytest.mark.asyncio
async def test_demand_service_unavailable(async_client: AsyncClient):
    """Test handling when load generator service is unavailable for demand status."""
    import httpx

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection failed")
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/demand/status")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_supply_service_unavailable(async_client: AsyncClient):
    """Test handling when load generator service is unavailable for supply status."""
    import httpx

    with patch("src.routes.loadgen.get_http_client") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = httpx.ConnectError("Connection failed")
        mock_client.return_value = mock_instance

        response = await async_client.get("/loadgen/supply/status")

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
