"""Feature flags API - Check which optional features are enabled."""

import logging
import os

from fastapi import APIRouter
from sqlalchemy import text

from src.db.client import get_pg_session_factory
from src.demo_label import brand_name, label_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/features", tags=["Features"])


async def _seeded_label() -> str | None:
    """The label that seeded the database, or None if unknown."""
    try:
        factory = get_pg_session_factory()
        async with factory() as session:
            result = await session.execute(text("SELECT label FROM demo_label WHERE id = 1"))
            row = result.first()
            return row[0] if row else None
    except Exception as exc:  # table missing on an older DB, or DB unavailable
        logger.debug("could not read demo_label: %s", exc)
        return None


@router.get("/label")
async def get_label_status():
    """Which white-label skin is active, and which one seeded the data.

    `active` is what this API process was started with; `seeded` is what
    produced the rows currently in Postgres. They disagree when a UI or API is
    running against data from a different label -- e.g. `npm run dev` without
    `make label`, or a deploy where the resolved artifacts were not regenerated.
    """
    active = label_name()
    seeded = await _seeded_label()
    return {
        "active": active,
        "brand": brand_name(),
        "seeded": seeded,
        "matches": seeded is None or seeded == active,
        "hint": (
            None
            if seeded is None or seeded == active
            else f"data was seeded with '{seeded}' but this process is running "
                 f"'{active}'. Re-run: make up LABEL={active}"
        ),
    }


@router.get("/bundling")
async def get_bundling_status():
    """Check if delivery bundling feature is enabled.

    Delivery bundling uses Materialize's WITH MUTUALLY RECURSIVE to group
    compatible orders. This is CPU intensive (~460s compute time) and disabled
    by default.

    Enable with: make up-agent-bundling
    """
    enabled = os.getenv("ENABLE_DELIVERY_BUNDLING", "false").lower() == "true"
    return {
        "feature": "delivery_bundling",
        "enabled": enabled,
        "description": "Mutually recursive constraint satisfaction for order bundling",
        "enable_command": "make up-agent-bundling" if not enabled else None,
    }


@router.get("")
async def list_features():
    """List all feature flags and their status."""
    bundling_enabled = os.getenv("ENABLE_DELIVERY_BUNDLING", "false").lower() == "true"

    return {
        "features": {
            "delivery_bundling": {
                "enabled": bundling_enabled,
                "description": "Mutually recursive constraint satisfaction for order bundling",
                "cpu_intensive": True,
            }
        }
    }
