"""Observability FastAPI routes.

Exposes endpoints for querying trace events and aggregate metrics
per plugin or dimension.

Requirements: 12.3, 12.5
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from conviction_room.models.trace import AggregateMetrics, TraceEvent
from conviction_room.services.observability import ObservabilityService

router = APIRouter(tags=["observability"])

# Module-level service instance
_obs_service = ObservabilityService()


# ---------------------------------------------------------------------------
# Trace routes
# ---------------------------------------------------------------------------


@router.get("/traces")
def query_traces(
    dimension: str | None = Query(default=None),
    plugin: UUID | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
) -> list[TraceEvent]:
    """Query traces with optional filters."""
    return _obs_service.query_traces(
        dimension=dimension,
        plugin_id=plugin,
        from_time=from_time,
        to_time=to_time,
    )


@router.get("/traces/{trace_id}")
def get_trace(trace_id: UUID) -> TraceEvent:
    """Return a single trace by ID."""
    trace = _obs_service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


# ---------------------------------------------------------------------------
# Metrics routes
# ---------------------------------------------------------------------------


@router.get("/metrics/plugins/{plugin_id}")
def get_plugin_metrics(
    plugin_id: UUID,
    window: str = Query(default="24h"),
) -> AggregateMetrics:
    """Aggregate metrics for a specific plugin."""
    return _obs_service.get_plugin_metrics(plugin_id, time_window=window)


@router.get("/metrics/dimensions/{dim}")
def get_dimension_metrics(
    dim: str,
    window: str = Query(default="24h"),
) -> AggregateMetrics:
    """Aggregate metrics for a dimension."""
    return _obs_service.get_dimension_metrics(dim, time_window=window)
