"""HTTP control server for load generator."""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from loadgen.config import PROFILES, LoadProfile, get_profile
from loadgen.orchestrator import LoadOrchestrator

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


class StartRequest(BaseModel):
    profile: str = "demo"
    duration_minutes: Optional[int] = None
    api_url: str = "http://api:8080"


class StatusResponse(BaseModel):
    status: Status
    profile: Optional[str] = None
    started_at: Optional[str] = None
    duration_minutes: Optional[int] = None


class MetricsResponse(BaseModel):
    total_successes: int = 0
    total_failures: int = 0
    success_rate: float = 0.0
    throughput_per_min: float = 0.0
    avg_latency_ms: float = 0.0
    orders_created: int = 0
    status_transitions: int = 0
    customers_created: int = 0
    inventory_updates: int = 0


@dataclass
class ServerState:
    status: Status = Status.STOPPED
    orchestrator: Optional[LoadOrchestrator] = None
    run_task: Optional[asyncio.Task] = None
    profile: Optional[str] = None
    started_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None


state = ServerState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Load generator control server starting...")
    yield
    # Stop orchestrator on shutdown
    if state.orchestrator and state.status == Status.RUNNING:
        logger.info("Stopping load generator on shutdown...")
        state.orchestrator.stop_requested = True
        if state.run_task:
            state.run_task.cancel()
            try:
                await state.run_task
            except asyncio.CancelledError:
                pass
    logger.info("Load generator control server stopped")


app = FastAPI(
    title="Load Generator Control",
    description="Control API for FreshMart load generator",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current load generator status."""
    # Check if task is done
    if state.run_task and state.run_task.done():
        state.status = Status.STOPPED
        state.run_task = None
        state.orchestrator = None

    return StatusResponse(
        status=state.status,
        profile=state.profile,
        started_at=state.started_at.isoformat() if state.started_at else None,
        duration_minutes=state.duration_minutes,
    )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get current metrics from running load generator."""
    if not state.orchestrator or state.status != Status.RUNNING:
        return MetricsResponse()

    try:
        summary = state.orchestrator.metrics.get_summary()
        return MetricsResponse(
            total_successes=summary.get("total_successes", 0),
            total_failures=summary.get("total_failures", 0),
            success_rate=summary.get("success_rate", 0.0),
            throughput_per_min=summary.get("throughput_per_min", 0.0),
            avg_latency_ms=summary.get("avg_latency_ms", 0.0),
            orders_created=summary.get("orders_created", 0),
            status_transitions=summary.get("status_transitions", 0),
            customers_created=summary.get("customers_created", 0),
            inventory_updates=summary.get("inventory_updates", 0),
        )
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return MetricsResponse()


@app.post("/start", response_model=StatusResponse)
async def start(request: StartRequest):
    """Start the load generator."""
    global state

    if state.status == Status.RUNNING:
        raise HTTPException(status_code=400, detail="Load generator is already running")

    # Get profile
    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    state.status = Status.STARTING
    state.profile = request.profile
    state.started_at = datetime.utcnow()
    state.duration_minutes = request.duration_minutes or profile.duration_minutes

    # Create orchestrator
    orchestrator = LoadOrchestrator(
        api_url=request.api_url,
        profile=profile,
    )
    state.orchestrator = orchestrator

    # Start in background
    async def run_orchestrator():
        try:
            state.status = Status.RUNNING
            await orchestrator.run(duration_minutes=state.duration_minutes)
        except asyncio.CancelledError:
            logger.info("Load generator cancelled")
        except Exception as e:
            logger.error(f"Load generator error: {e}")
        finally:
            state.status = Status.STOPPED
            state.orchestrator = None
            state.run_task = None

    state.run_task = asyncio.create_task(run_orchestrator())

    # Wait briefly for startup
    await asyncio.sleep(0.5)

    return StatusResponse(
        status=state.status,
        profile=state.profile,
        started_at=state.started_at.isoformat() if state.started_at else None,
        duration_minutes=state.duration_minutes,
    )


@app.post("/stop", response_model=StatusResponse)
async def stop():
    """Stop the load generator."""
    global state

    if state.status != Status.RUNNING or not state.orchestrator:
        return StatusResponse(
            status=Status.STOPPED,
            profile=None,
            started_at=None,
            duration_minutes=None,
        )

    state.status = Status.STOPPING
    logger.info("Stopping load generator...")

    # Signal stop
    state.orchestrator.stop_requested = True

    # Cancel task
    if state.run_task:
        state.run_task.cancel()
        try:
            await asyncio.wait_for(state.run_task, timeout=10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    state.status = Status.STOPPED
    state.orchestrator = None
    state.run_task = None
    state.profile = None
    state.started_at = None
    state.duration_minutes = None

    return StatusResponse(
        status=Status.STOPPED,
        profile=None,
        started_at=None,
        duration_minutes=None,
    )


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
