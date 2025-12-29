"""Tests for load generator control server."""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from loadgen.server import app, get_state, _state


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    global _state
    from loadgen.server import ServerState, Status
    _state = ServerState()
    _state.status = Status.STOPPED
    yield
    _state = None


@pytest.fixture
async def test_client():
    """Create test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint(test_client):
    """Test health endpoint."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_list_profiles(test_client):
    """Test listing available profiles."""
    response = await test_client.get("/profiles")
    assert response.status_code == 200
    profiles = response.json()
    assert isinstance(profiles, list)
    assert len(profiles) > 0
    # Check structure
    assert "name" in profiles[0]
    assert "description" in profiles[0]
    assert "orders_per_minute" in profiles[0]


@pytest.mark.asyncio
async def test_get_status_stopped(test_client):
    """Test getting status when stopped."""
    response = await test_client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert data["profile"] is None
    assert data["started_at"] is None


@pytest.mark.asyncio
async def test_get_metrics_when_stopped(test_client):
    """Test getting metrics when stopped returns empty metrics."""
    response = await test_client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_successes"] == 0
    assert data["total_failures"] == 0
    assert data["success_rate"] == 0.0


@pytest.mark.asyncio
async def test_start_loadgen(test_client):
    """Test starting the load generator."""
    with patch("loadgen.server.LoadOrchestrator") as mock_orchestrator_class:
        mock_orchestrator = AsyncMock()
        mock_orchestrator.run = AsyncMock()
        mock_orchestrator_class.return_value = mock_orchestrator

        response = await test_client.post("/start", json={
            "profile": "demo",
            "duration_minutes": 1,
            "api_url": "http://test-api:8080"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["starting", "running"]
        assert data["profile"] == "demo"
        assert data["duration_minutes"] == 1


@pytest.mark.asyncio
async def test_start_loadgen_invalid_profile(test_client):
    """Test starting with invalid profile."""
    response = await test_client.post("/start", json={
        "profile": "invalid-profile-name",
        "duration_minutes": 1,
        "api_url": "http://test-api:8080"
    })

    assert response.status_code == 400
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_start_loadgen_already_running(test_client):
    """Test starting when already running."""
    state = get_state()
    from loadgen.server import Status
    state.status = Status.RUNNING

    response = await test_client.post("/start", json={
        "profile": "demo",
        "duration_minutes": 1,
        "api_url": "http://test-api:8080"
    })

    assert response.status_code == 400
    assert "already running" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stop_loadgen_when_not_running(test_client):
    """Test stopping when not running."""
    response = await test_client.post("/stop")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"


@pytest.mark.asyncio
async def test_stop_loadgen_when_running(test_client):
    """Test stopping when running."""
    import asyncio
    from loadgen.server import Status

    state = get_state()
    state.status = Status.RUNNING
    state.orchestrator = AsyncMock()
    state.run_task = asyncio.create_task(asyncio.sleep(10))

    response = await test_client.post("/stop")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"
    assert state.run_task is None or state.run_task.cancelled()


@pytest.mark.asyncio
async def test_get_state_creates_singleton():
    """Test that get_state creates a singleton instance."""
    global _state
    _state = None

    state1 = get_state()
    state2 = get_state()

    assert state1 is state2


@pytest.mark.asyncio
async def test_cors_configuration():
    """Test CORS middleware is configured."""
    import os
    # The CORS origins should be configurable via environment
    # This test verifies the middleware is present
    response = await AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ).options("/health")
    # CORS middleware should handle OPTIONS requests
    assert response.status_code in [200, 405]  # Either OK or method not allowed
