"""Load Generator control endpoints - proxies to load-generator service."""

import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/loadgen", tags=["Load Generator"])

# Load generator service URL (runs as separate container)
LOADGEN_SERVICE_URL = os.environ.get("LOADGEN_SERVICE_URL", "http://load-generator:8084")


class ProfileInfo(BaseModel):
    """Profile information."""

    name: str
    description: str
    orders_per_minute: float
    concurrent_workflows: int
    duration_minutes: Optional[int]


class StartRequest(BaseModel):
    """Request to start load generation."""

    profile: str = "demo"
    duration_minutes: Optional[int] = None
    api_url: Optional[str] = None


class StatusResponse(BaseModel):
    """Load generator status response."""

    status: str
    profile: Optional[str] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    pid: Optional[int] = None  # Kept for backwards compatibility


class MetricsResponse(BaseModel):
    """Metrics from load generator."""

    total_successes: int = 0
    total_failures: int = 0
    success_rate: float = 0.0
    throughput_per_min: float = 0.0
    avg_latency_ms: float = 0.0
    orders_created: int = 0
    status_transitions: int = 0
    customers_created: int = 0
    inventory_updates: int = 0


async def _proxy_get(path: str) -> dict:
    """Proxy GET request to load generator service."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{LOADGEN_SERVICE_URL}{path}")
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Load generator service unavailable")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


async def _proxy_post(path: str, data: dict = None) -> dict:
    """Proxy POST request to load generator service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(f"{LOADGEN_SERVICE_URL}{path}", json=data)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Load generator service unavailable")
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)


@router.get("/profiles", response_model=list[ProfileInfo])
async def list_profiles():
    """List available load profiles."""
    result = await _proxy_get("/profiles")
    return result


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current load generator status."""
    result = await _proxy_get("/status")
    return StatusResponse(**result, pid=None)


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get current metrics from running load generator."""
    result = await _proxy_get("/metrics")
    return MetricsResponse(**result)


@router.post("/start", response_model=StatusResponse)
async def start_loadgen(request: StartRequest):
    """Start the load generator."""
    # Default API URL points to API container from within docker network
    api_url = request.api_url or "http://api:8080"

    result = await _proxy_post("/start", {
        "profile": request.profile,
        "duration_minutes": request.duration_minutes,
        "api_url": api_url,
    })
    return StatusResponse(**result, pid=None)


@router.post("/stop", response_model=StatusResponse)
async def stop_loadgen():
    """Stop the load generator."""
    result = await _proxy_post("/stop")
    return StatusResponse(**result, pid=None)


# Backwards compatibility endpoint
@router.get("/output")
async def get_output():
    """Get recent output from the load generator (deprecated - use /metrics)."""
    return {"lines": ["Use /loadgen/metrics for live metrics"]}
