"""Plugin Router / Dispatcher FastAPI routes.

Exposes the dispatch endpoint that routes calls to the active plugin
for a given dimension through the Plugin Router service.

Requirements: 2.2, 2.3
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from conviction_room.models.plugin import PluginError
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.router import PluginRouterService

router = APIRouter(prefix="/dispatch", tags=["router"])

# Module-level service instances
_registry = PluginRegistryService()
_cost_governor = CostGovernorService()
_router_service = PluginRouterService(_registry, _cost_governor)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_status(error: PluginError) -> int:
    """Map a PluginError to an HTTP status code."""
    if error.error_code == "NO_ACTIVE_PLUGIN":
        return 404
    if error.error_code == "BUDGET_EXCEEDED":
        return 403
    return 400


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/{dimension}/{endpoint}")
def dispatch(dimension: str, endpoint: str, payload: dict) -> dict:
    """Route a call to the active plugin for the given dimension.

    Delegates to ``PluginRouterService.dispatch()`` and returns the
    response or raises an HTTPException with the PluginError details.
    """
    result = _router_service.dispatch(dimension, endpoint, payload)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=_error_status(result),
            detail=result.model_dump(mode="json"),
        )
    return result
