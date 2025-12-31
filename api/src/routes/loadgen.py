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

# Shared HTTP client for connection pooling
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client for connection pooling."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def close_http_client():
    """Close the shared HTTP client (called on shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# ============== Request/Response Models ==============

class ProfileInfo(BaseModel):
    """Profile information."""
    name: str
    description: str
    orders_per_minute: float
    concurrent_workflows: int
    duration_minutes: Optional[int]


class SupplyConfigInfo(BaseModel):
    """Supply configuration information."""
    name: str
    dispatch_interval_seconds: float
    picking_duration_seconds: float
    delivery_duration_seconds: float


# Demand models
class DemandStatusResponse(BaseModel):
    """Demand generator status."""
    status: str
    profile: Optional[str] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class DemandMetricsResponse(BaseModel):
    """Demand generator metrics."""
    total_successes: int = 0
    total_failures: int = 0
    success_rate: float = 0.0
    throughput_per_min: float = 0.0
    avg_latency_ms: float = 0.0
    orders_created: int = 0
    customers_created: int = 0
    inventory_updates: int = 0
    cancellations: int = 0


class StartDemandRequest(BaseModel):
    """Request to start demand generation."""
    profile: str = "demo"
    duration_minutes: Optional[int] = None
    api_url: Optional[str] = None


# Supply models
class SupplyStatusResponse(BaseModel):
    """Supply generator status."""
    status: str
    supply_config: Optional[str] = None
    dispatch_interval_seconds: Optional[float] = None
    picking_duration_seconds: Optional[float] = None
    delivery_duration_seconds: Optional[float] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class SupplyMetricsResponse(BaseModel):
    """Supply generator metrics."""
    total_successes: int = 0
    dispatch_assigns: int = 0
    dispatch_completes: int = 0
    throughput_per_min: float = 0.0


class StartSupplyRequest(BaseModel):
    """Request to start supply generation."""
    profile: str = "demo"
    supply_config: str = "normal"
    dispatch_interval_seconds: Optional[float] = None
    picking_duration_seconds: Optional[float] = None
    delivery_duration_seconds: Optional[float] = None
    duration_minutes: Optional[int] = None
    api_url: Optional[str] = None


# Combined models
class CombinedStatusResponse(BaseModel):
    """Combined status of both generators."""
    demand: DemandStatusResponse
    supply: SupplyStatusResponse


class CombinedMetricsResponse(BaseModel):
    """Combined metrics from both generators."""
    demand: DemandMetricsResponse
    supply: SupplyMetricsResponse


class StartBothRequest(BaseModel):
    """Request to start both generators."""
    profile: str = "demo"
    supply_config: str = "normal"
    duration_minutes: Optional[int] = None
    api_url: Optional[str] = None


# Legacy models (backward compatibility)
class StatusResponse(BaseModel):
    """Load generator status response (legacy)."""
    status: str
    profile: Optional[str] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    pid: Optional[int] = None  # Kept for backwards compatibility


class StartRequest(BaseModel):
    """Request to start load generation (legacy)."""
    profile: str = "demo"
    duration_minutes: Optional[int] = None
    api_url: Optional[str] = None


# ============== Proxy Helpers ==============

async def _proxy_get(path: str) -> dict:
    """Proxy GET request to load generator service."""
    client = get_http_client()
    try:
        response = await client.get(f"{LOADGEN_SERVICE_URL}{path}")
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Load generator service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Load generator request failed")
    except Exception as e:
        logger.error(f"Unexpected error proxying GET {path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def _proxy_post(path: str, data: dict = None) -> dict:
    """Proxy POST request to load generator service."""
    client = get_http_client()
    try:
        response = await client.post(f"{LOADGEN_SERVICE_URL}{path}", json=data)
        response.raise_for_status()
        return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Load generator service unavailable")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Load generator request failed")
    except Exception as e:
        logger.error(f"Unexpected error proxying POST {path}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============== Profile & Config Endpoints ==============

@router.get("/profiles", response_model=list[ProfileInfo])
async def list_profiles():
    """List available load profiles."""
    result = await _proxy_get("/profiles")
    return result


@router.get("/supply-configs", response_model=list[SupplyConfigInfo])
async def list_supply_configs():
    """List available supply configurations."""
    result = await _proxy_get("/supply-configs")
    return result


# ============== Demand Endpoints ==============

@router.get("/demand/status", response_model=DemandStatusResponse)
async def get_demand_status():
    """Get demand generator status."""
    result = await _proxy_get("/demand/status")
    return DemandStatusResponse(**result)


@router.get("/demand/metrics", response_model=DemandMetricsResponse)
async def get_demand_metrics():
    """Get demand generator metrics."""
    result = await _proxy_get("/demand/metrics")
    return DemandMetricsResponse(**result)


@router.post("/demand/start", response_model=DemandStatusResponse)
async def start_demand(request: StartDemandRequest):
    """Start the demand generator."""
    api_url = request.api_url or "http://api:8080"
    result = await _proxy_post("/demand/start", {
        "profile": request.profile,
        "duration_minutes": request.duration_minutes,
        "api_url": api_url,
    })
    return DemandStatusResponse(**result)


@router.post("/demand/stop", response_model=DemandStatusResponse)
async def stop_demand():
    """Stop the demand generator."""
    result = await _proxy_post("/demand/stop")
    return DemandStatusResponse(**result)


# ============== Supply Endpoints ==============

@router.get("/supply/status", response_model=SupplyStatusResponse)
async def get_supply_status():
    """Get supply generator status."""
    result = await _proxy_get("/supply/status")
    return SupplyStatusResponse(**result)


@router.get("/supply/metrics", response_model=SupplyMetricsResponse)
async def get_supply_metrics():
    """Get supply generator metrics."""
    result = await _proxy_get("/supply/metrics")
    return SupplyMetricsResponse(**result)


@router.post("/supply/start", response_model=SupplyStatusResponse)
async def start_supply(request: StartSupplyRequest):
    """Start the supply generator."""
    api_url = request.api_url or "http://api:8080"
    result = await _proxy_post("/supply/start", {
        "profile": request.profile,
        "supply_config": request.supply_config,
        "dispatch_interval_seconds": request.dispatch_interval_seconds,
        "picking_duration_seconds": request.picking_duration_seconds,
        "delivery_duration_seconds": request.delivery_duration_seconds,
        "duration_minutes": request.duration_minutes,
        "api_url": api_url,
    })
    return SupplyStatusResponse(**result)


@router.post("/supply/stop", response_model=SupplyStatusResponse)
async def stop_supply():
    """Stop the supply generator."""
    result = await _proxy_post("/supply/stop")
    return SupplyStatusResponse(**result)


# ============== Combined Endpoints ==============

@router.get("/status", response_model=CombinedStatusResponse)
async def get_combined_status():
    """Get combined status of both generators."""
    result = await _proxy_get("/status")
    return CombinedStatusResponse(**result)


@router.get("/metrics", response_model=CombinedMetricsResponse)
async def get_combined_metrics():
    """Get combined metrics from both generators."""
    result = await _proxy_get("/metrics")
    return CombinedMetricsResponse(**result)


@router.post("/start", response_model=CombinedStatusResponse)
async def start_both(request: StartBothRequest):
    """Start both demand and supply generators."""
    api_url = request.api_url or "http://api:8080"
    result = await _proxy_post("/start", {
        "profile": request.profile,
        "supply_config": request.supply_config,
        "duration_minutes": request.duration_minutes,
        "api_url": api_url,
    })
    return CombinedStatusResponse(**result)


@router.post("/stop", response_model=CombinedStatusResponse)
async def stop_both():
    """Stop both demand and supply generators."""
    result = await _proxy_post("/stop")
    return CombinedStatusResponse(**result)


# ============== Legacy/Utility Endpoints ==============

@router.get("/output")
async def get_output():
    """Get recent output from the load generator (deprecated - use /metrics)."""
    return {"lines": ["Use /loadgen/metrics for live metrics"]}
