"""Feature flags API - Check which optional features are enabled."""

import os

from fastapi import APIRouter

router = APIRouter(prefix="/api/features", tags=["Features"])


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
