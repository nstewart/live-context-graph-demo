"""HTTP control server for load generator with separate demand/supply control."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from loadgen.config import PROFILES, SUPPLY_CONFIGS, LoadProfile, SupplyConfig, get_profile, get_supply_config
from loadgen.demand_orchestrator import DemandOrchestrator
from loadgen.supply_orchestrator import SupplyOrchestrator

logger = logging.getLogger(__name__)


class Status(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    STARTING = "starting"
    STOPPING = "stopping"


class ProfileInfo(BaseModel):
    name: str
    description: str
    orders_per_minute: float
    concurrent_workflows: int
    duration_minutes: Optional[int]


class SupplyConfigInfo(BaseModel):
    name: str
    dispatch_interval_seconds: float
    picking_duration_seconds: float
    delivery_duration_seconds: float


class StartDemandRequest(BaseModel):
    profile: str = "demo"
    duration_minutes: Optional[int] = None
    api_url: str = "http://api:8080"


class StartSupplyRequest(BaseModel):
    profile: str = "demo"  # Used for duration
    supply_config: str = "normal"
    dispatch_interval_seconds: Optional[float] = None
    picking_duration_seconds: Optional[float] = None
    delivery_duration_seconds: Optional[float] = None
    duration_minutes: Optional[int] = None
    api_url: str = "http://api:8080"


class StartBothRequest(BaseModel):
    profile: str = "demo"
    supply_config: str = "normal"
    duration_minutes: Optional[int] = None
    api_url: str = "http://api:8080"


class StatusResponse(BaseModel):
    status: Status
    profile: Optional[str] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class SupplyStatusResponse(BaseModel):
    status: Status
    supply_config: Optional[str] = None
    dispatch_interval_seconds: Optional[float] = None
    picking_duration_seconds: Optional[float] = None
    delivery_duration_seconds: Optional[float] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class CombinedStatusResponse(BaseModel):
    demand: StatusResponse
    supply: SupplyStatusResponse


class MetricsResponse(BaseModel):
    total_successes: int = 0
    total_failures: int = 0
    success_rate: float = 0.0
    throughput_per_min: float = 0.0
    avg_latency_ms: float = 0.0
    orders_created: int = 0
    customers_created: int = 0
    inventory_updates: int = 0
    cancellations: int = 0


class SupplyMetricsResponse(BaseModel):
    total_successes: int = 0
    dispatch_assigns: int = 0
    dispatch_completes: int = 0
    throughput_per_min: float = 0.0


@dataclass
class DemandState:
    status: Status = Status.STOPPED
    orchestrator: Optional[DemandOrchestrator] = None
    run_task: Optional[asyncio.Task] = None
    profile: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None


@dataclass
class SupplyState:
    status: Status = Status.STOPPED
    orchestrator: Optional[SupplyOrchestrator] = None
    run_task: Optional[asyncio.Task] = None
    supply_config_name: Optional[str] = None
    supply_config: Optional[SupplyConfig] = None
    started_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None


@dataclass
class ServerState:
    demand: DemandState = field(default_factory=DemandState)
    supply: SupplyState = field(default_factory=SupplyState)


# Global state instance
_state: Optional[ServerState] = None


def get_state() -> ServerState:
    """Get or create the global state instance."""
    global _state
    if _state is None:
        _state = ServerState()
    return _state


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Load generator control server starting...")
    yield
    # Stop both orchestrators on shutdown
    state = get_state()

    if state.demand.orchestrator and state.demand.status == Status.RUNNING:
        logger.info("Stopping demand generator on shutdown...")
        state.demand.orchestrator.stop_requested = True
        if state.demand.run_task:
            state.demand.run_task.cancel()
            try:
                await state.demand.run_task
            except asyncio.CancelledError:
                pass

    if state.supply.orchestrator and state.supply.status == Status.RUNNING:
        logger.info("Stopping supply generator on shutdown...")
        state.supply.orchestrator.stop_requested = True
        if state.supply.run_task:
            state.supply.run_task.cancel()
            try:
                await state.supply.run_task
            except asyncio.CancelledError:
                pass

    logger.info("Load generator control server stopped")


app = FastAPI(
    title="Load Generator Control",
    description="Control API for FreshMart load generator with separate demand/supply control",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/profiles", response_model=list[ProfileInfo])
async def list_profiles():
    """List available load profiles."""
    return [
        ProfileInfo(
            name=p.name,
            description=p.description,
            orders_per_minute=p.orders_per_minute,
            concurrent_workflows=p.concurrent_workflows,
            duration_minutes=p.duration_minutes,
        )
        for p in PROFILES.values()
    ]


@app.get("/supply-configs", response_model=list[SupplyConfigInfo])
async def list_supply_configs():
    """List available supply configurations."""
    return [
        SupplyConfigInfo(
            name=name,
            dispatch_interval_seconds=config.dispatch_interval_seconds,
            picking_duration_seconds=config.picking_duration_seconds,
            delivery_duration_seconds=config.delivery_duration_seconds,
        )
        for name, config in SUPPLY_CONFIGS.items()
    ]


# ============== DEMAND ENDPOINTS ==============

@app.get("/demand/status", response_model=StatusResponse)
async def get_demand_status(state: ServerState = Depends(get_state)):
    """Get demand generator status."""
    if state.demand.run_task and state.demand.run_task.done():
        state.demand.status = Status.STOPPED
        state.demand.run_task = None
        state.demand.orchestrator = None

    return StatusResponse(
        status=state.demand.status,
        profile=state.demand.profile,
        started_at=state.demand.started_at.isoformat() if state.demand.started_at else None,
        duration_minutes=state.demand.duration_minutes,
    )


@app.get("/demand/metrics", response_model=MetricsResponse)
async def get_demand_metrics(state: ServerState = Depends(get_state)):
    """Get demand generator metrics."""
    if not state.demand.orchestrator or state.demand.status != Status.RUNNING:
        return MetricsResponse()

    try:
        summary = state.demand.orchestrator.metrics.get_summary()
        return MetricsResponse(
            total_successes=summary.get("total_successes", 0),
            total_failures=summary.get("total_failures", 0),
            success_rate=summary.get("success_rate", 0.0),
            throughput_per_min=summary.get("throughput_per_min", 0.0),
            avg_latency_ms=summary.get("avg_latency_ms", 0.0),
            orders_created=summary.get("orders_created", 0),
            customers_created=summary.get("customers_created", 0),
            inventory_updates=summary.get("inventory_updates", 0),
            cancellations=summary.get("cancellations", 0),
        )
    except Exception as e:
        logger.error(f"Error getting demand metrics: {e}")
        return MetricsResponse()


@app.post("/demand/start", response_model=StatusResponse)
async def start_demand(request: StartDemandRequest, state: ServerState = Depends(get_state)):
    """Start the demand generator."""
    if state.demand.status == Status.RUNNING:
        raise HTTPException(status_code=400, detail="Demand generator is already running")

    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    state.demand.status = Status.STARTING
    state.demand.profile = request.profile
    state.demand.started_at = datetime.utcnow()
    state.demand.duration_minutes = request.duration_minutes or profile.duration_minutes

    orchestrator = DemandOrchestrator(
        api_url=request.api_url,
        profile=profile,
    )
    state.demand.orchestrator = orchestrator

    async def run_orchestrator():
        try:
            state.demand.status = Status.RUNNING
            await orchestrator.run(duration_minutes=state.demand.duration_minutes)
        except asyncio.CancelledError:
            logger.info("Demand generator cancelled")
        except Exception as e:
            logger.error(f"Demand generator error: {e}")
        finally:
            state.demand.status = Status.STOPPED
            state.demand.orchestrator = None
            state.demand.run_task = None

    state.demand.run_task = asyncio.create_task(run_orchestrator())
    await asyncio.sleep(0.5)

    return StatusResponse(
        status=state.demand.status,
        profile=state.demand.profile,
        started_at=state.demand.started_at.isoformat() if state.demand.started_at else None,
        duration_minutes=state.demand.duration_minutes,
    )


@app.post("/demand/stop", response_model=StatusResponse)
async def stop_demand(state: ServerState = Depends(get_state)):
    """Stop the demand generator."""
    if state.demand.status != Status.RUNNING or not state.demand.orchestrator:
        return StatusResponse(status=Status.STOPPED)

    state.demand.status = Status.STOPPING
    logger.info("Stopping demand generator...")

    state.demand.orchestrator.stop_requested = True

    if state.demand.run_task:
        state.demand.run_task.cancel()
        try:
            await asyncio.wait_for(state.demand.run_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    state.demand.status = Status.STOPPED
    state.demand.orchestrator = None
    state.demand.run_task = None
    state.demand.profile = None
    state.demand.started_at = None
    state.demand.duration_minutes = None

    return StatusResponse(status=Status.STOPPED)


# ============== SUPPLY ENDPOINTS ==============

@app.get("/supply/status", response_model=SupplyStatusResponse)
async def get_supply_status(state: ServerState = Depends(get_state)):
    """Get supply generator status."""
    if state.supply.run_task and state.supply.run_task.done():
        state.supply.status = Status.STOPPED
        state.supply.run_task = None
        state.supply.orchestrator = None

    return SupplyStatusResponse(
        status=state.supply.status,
        supply_config=state.supply.supply_config_name,
        dispatch_interval_seconds=state.supply.supply_config.dispatch_interval_seconds if state.supply.supply_config else None,
        picking_duration_seconds=state.supply.supply_config.picking_duration_seconds if state.supply.supply_config else None,
        delivery_duration_seconds=state.supply.supply_config.delivery_duration_seconds if state.supply.supply_config else None,
        started_at=state.supply.started_at.isoformat() if state.supply.started_at else None,
        duration_minutes=state.supply.duration_minutes,
    )


@app.get("/supply/metrics", response_model=SupplyMetricsResponse)
async def get_supply_metrics(state: ServerState = Depends(get_state)):
    """Get supply generator metrics."""
    if not state.supply.orchestrator or state.supply.status != Status.RUNNING:
        return SupplyMetricsResponse()

    try:
        summary = state.supply.orchestrator.metrics.get_summary()
        return SupplyMetricsResponse(
            total_successes=summary.get("total_successes", 0),
            dispatch_assigns=summary.get("dispatch_assigns", 0),
            dispatch_completes=summary.get("dispatch_completes", 0),
            throughput_per_min=summary.get("throughput_per_min", 0.0),
        )
    except Exception as e:
        logger.error(f"Error getting supply metrics: {e}")
        return SupplyMetricsResponse()


@app.post("/supply/start", response_model=SupplyStatusResponse)
async def start_supply(request: StartSupplyRequest, state: ServerState = Depends(get_state)):
    """Start the supply generator."""
    if state.supply.status == Status.RUNNING:
        raise HTTPException(status_code=400, detail="Supply generator is already running")

    try:
        profile = get_profile(request.profile)
        base_config = get_supply_config(request.supply_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Apply any overrides
    supply_config = SupplyConfig(
        dispatch_interval_seconds=request.dispatch_interval_seconds or base_config.dispatch_interval_seconds,
        picking_duration_seconds=request.picking_duration_seconds or base_config.picking_duration_seconds,
        delivery_duration_seconds=request.delivery_duration_seconds or base_config.delivery_duration_seconds,
    )

    state.supply.status = Status.STARTING
    state.supply.supply_config_name = request.supply_config
    state.supply.supply_config = supply_config
    state.supply.started_at = datetime.utcnow()
    state.supply.duration_minutes = request.duration_minutes or profile.duration_minutes

    orchestrator = SupplyOrchestrator(
        api_url=request.api_url,
        profile=profile,
        supply_config=supply_config,
    )
    state.supply.orchestrator = orchestrator

    async def run_orchestrator():
        try:
            state.supply.status = Status.RUNNING
            await orchestrator.run(duration_minutes=state.supply.duration_minutes)
        except asyncio.CancelledError:
            logger.info("Supply generator cancelled")
        except Exception as e:
            logger.error(f"Supply generator error: {e}")
        finally:
            state.supply.status = Status.STOPPED
            state.supply.orchestrator = None
            state.supply.run_task = None

    state.supply.run_task = asyncio.create_task(run_orchestrator())
    await asyncio.sleep(0.5)

    return SupplyStatusResponse(
        status=state.supply.status,
        supply_config=state.supply.supply_config_name,
        dispatch_interval_seconds=supply_config.dispatch_interval_seconds,
        picking_duration_seconds=supply_config.picking_duration_seconds,
        delivery_duration_seconds=supply_config.delivery_duration_seconds,
        started_at=state.supply.started_at.isoformat() if state.supply.started_at else None,
        duration_minutes=state.supply.duration_minutes,
    )


@app.post("/supply/stop", response_model=SupplyStatusResponse)
async def stop_supply(state: ServerState = Depends(get_state)):
    """Stop the supply generator."""
    if state.supply.status != Status.RUNNING or not state.supply.orchestrator:
        return SupplyStatusResponse(status=Status.STOPPED)

    state.supply.status = Status.STOPPING
    logger.info("Stopping supply generator...")

    state.supply.orchestrator.stop_requested = True

    if state.supply.run_task:
        state.supply.run_task.cancel()
        try:
            await asyncio.wait_for(state.supply.run_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    state.supply.status = Status.STOPPED
    state.supply.orchestrator = None
    state.supply.run_task = None
    state.supply.supply_config_name = None
    state.supply.supply_config = None
    state.supply.started_at = None
    state.supply.duration_minutes = None

    return SupplyStatusResponse(status=Status.STOPPED)


# ============== COMBINED ENDPOINTS (backward compatible) ==============

@app.get("/status", response_model=CombinedStatusResponse)
async def get_status(state: ServerState = Depends(get_state)):
    """Get combined status of both generators."""
    demand_status = await get_demand_status(state)
    supply_status = await get_supply_status(state)
    return CombinedStatusResponse(demand=demand_status, supply=supply_status)


@app.post("/start", response_model=CombinedStatusResponse)
async def start_both(request: StartBothRequest, state: ServerState = Depends(get_state)):
    """Start both demand and supply generators."""
    demand_request = StartDemandRequest(
        profile=request.profile,
        duration_minutes=request.duration_minutes,
        api_url=request.api_url,
    )
    supply_request = StartSupplyRequest(
        profile=request.profile,
        supply_config=request.supply_config,
        duration_minutes=request.duration_minutes,
        api_url=request.api_url,
    )

    demand_status = await start_demand(demand_request, state)
    supply_status = await start_supply(supply_request, state)

    return CombinedStatusResponse(demand=demand_status, supply=supply_status)


@app.post("/stop", response_model=CombinedStatusResponse)
async def stop_both(state: ServerState = Depends(get_state)):
    """Stop both demand and supply generators."""
    demand_status = await stop_demand(state)
    supply_status = await stop_supply(state)
    return CombinedStatusResponse(demand=demand_status, supply=supply_status)


@app.get("/metrics")
async def get_all_metrics(state: ServerState = Depends(get_state)):
    """Get metrics from both generators."""
    demand_metrics = await get_demand_metrics(state)
    supply_metrics = await get_supply_metrics(state)
    return {
        "demand": demand_metrics.model_dump(),
        "supply": supply_metrics.model_dump(),
    }


def main():
    """Run the control server."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    uvicorn.run(app, host="0.0.0.0", port=8084)


if __name__ == "__main__":
    main()
