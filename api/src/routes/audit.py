"""Audit routes for tracking database writes."""

from typing import Optional

from fastapi import APIRouter, Query

from src.audit.write_store import get_write_store

router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("/writes")
async def get_writes(
    since_ts: Optional[float] = Query(None, description="Only return events after this Unix timestamp"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of events to return"),
):
    """Get recent write events from the audit store.

    Returns write events (INSERT/UPDATE operations on triples) that triggered
    propagation through Materialize to search indexes.
    """
    store = get_write_store()
    events = store.get_events(since_ts=since_ts, limit=limit)
    return {"events": events}


@router.get("/writes/health")
async def writes_health():
    """Health check for the write audit store."""
    store = get_write_store()
    return {
        "status": "healthy",
        "event_count": len(store),
    }
