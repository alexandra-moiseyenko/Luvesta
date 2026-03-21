"""FastAPI application entry point for Conviction Room.

Wires all API routers, configures error handling for PluginError,
and loads the default Dimension Dependency Graph at startup.

Requirements: 1.1, 2.2, 3.1, 7.2, 12.1
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from conviction_room.api import (
    benchmark,
    cost_governor,
    dependency_graph,
    observability,
    registry,
    router as dispatch_router,
    test_harness,
)
from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Conviction Room",
    description="Modular plugin architecture for adversarial investment research",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Register all API routers
# ---------------------------------------------------------------------------

app.include_router(registry.router)
app.include_router(dispatch_router.router)
app.include_router(dependency_graph.router)
app.include_router(cost_governor.router)
app.include_router(benchmark.router)
app.include_router(observability.router)
app.include_router(test_harness.router)

# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@app.exception_handler(PluginError)
async def plugin_error_handler(_request: Request, exc: PluginError) -> JSONResponse:
    """Return a structured JSON response for PluginError exceptions."""
    return JSONResponse(
        status_code=400,
        content=exc.model_dump(mode="json"),
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check() -> dict:
    """System health check endpoint."""
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# Startup: load default Dimension Dependency Graph
# ---------------------------------------------------------------------------

_DEFAULT_GRAPH = DimensionGraph(
    nodes=[
        DimensionNode(dimension="persistence", tier="foundation", depends_on=[]),
        DimensionNode(dimension="model_provider", tier="foundation", depends_on=[]),
        DimensionNode(dimension="retrieval", tier="mid-tier", depends_on=["persistence"]),
        DimensionNode(dimension="context_memory", tier="mid-tier", depends_on=["persistence"]),
        DimensionNode(dimension="data_provider", tier="mid-tier", depends_on=["persistence"]),
        DimensionNode(dimension="orchestration", tier="leaf", depends_on=["retrieval", "model_provider", "context_memory"]),
    ]
)


@app.on_event("startup")
async def load_default_graph() -> None:
    """Load the default dimension dependency graph at startup."""
    from conviction_room.api.dependency_graph import _graph_service

    try:
        _graph_service.load_graph(_DEFAULT_GRAPH)
        logger.info("Loaded default dimension dependency graph with %d nodes", len(_DEFAULT_GRAPH.nodes))
    except ValueError as exc:
        logger.error("Failed to load default dependency graph: %s", exc)
