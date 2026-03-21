"""Plugin Registry FastAPI routes.

Exposes endpoints for plugin registration, discovery, activation,
deactivation, deletion, and querying the active plugin per dimension.

Requirements: 2.1, 2.2, 2.5, 2.6
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from conviction_room.contracts.base import PluginContractBase
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.registry import PluginRegistryService

router = APIRouter(prefix="/registry", tags=["registry"])

# Module-level service instance
_registry = PluginRegistryService()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RegisterPluginRequest(BaseModel):
    """Request body for POST /registry/plugins."""

    plugin: PluginMetadata
    contract: PluginContractBase
    plugin_endpoints: list[dict]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_status(error: PluginError) -> int:
    """Map a PluginError to an HTTP status code."""
    if error.error_code == "PLUGIN_NOT_FOUND":
        return 404
    if error.error_code == "CONTRACT_VALIDATION_FAILED":
        return 400
    return 400


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/plugins", status_code=201)
def register_plugin(body: RegisterPluginRequest) -> PluginMetadata:
    """Register a new plugin after contract validation."""
    result = _registry.register(body.plugin, body.contract, body.plugin_endpoints)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=_error_status(result),
            detail=result.model_dump(mode="json"),
        )
    return result


@router.get("/plugins")
def list_plugins(
    dimension: str | None = Query(default=None),
    status: str | None = Query(default=None),
    version: str | None = Query(default=None),
) -> list[PluginMetadata]:
    """List plugins with optional filters (dimension, status, version)."""
    return _registry.query(dimension=dimension, status=status, version=version)


@router.get("/plugins/{plugin_id}")
def get_plugin(plugin_id: UUID) -> PluginMetadata:
    """Get plugin details by ID."""
    plugin = _registry.get(plugin_id)
    if plugin is None:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.put("/plugins/{plugin_id}/activate")
def activate_plugin(plugin_id: UUID) -> PluginMetadata:
    """Activate a plugin for its dimension (atomic swap)."""
    result = _registry.activate(plugin_id)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=_error_status(result),
            detail=result.model_dump(mode="json"),
        )
    return result


@router.put("/plugins/{plugin_id}/deactivate")
def deactivate_plugin(plugin_id: UUID) -> PluginMetadata:
    """Deactivate a plugin."""
    result = _registry.deactivate(plugin_id)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=_error_status(result),
            detail=result.model_dump(mode="json"),
        )
    return result


@router.delete("/plugins/{plugin_id}", status_code=200)
def delete_plugin(plugin_id: UUID) -> dict:
    """Delete a plugin from the registry."""
    deleted = _registry.delete(plugin_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"deleted": True}


@router.get("/dimensions/{dimension}/active")
def get_active_plugin(dimension: str) -> PluginMetadata:
    """Get the active plugin for a dimension."""
    result = _registry.get_active(dimension)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=_error_status(result),
            detail=result.model_dump(mode="json"),
        )
    return result
