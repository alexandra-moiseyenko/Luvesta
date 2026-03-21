"""Dimension Dependency Graph FastAPI routes.

Exposes endpoints for querying and updating the dimension dependency DAG:
full graph, topological order, per-dimension dependencies and tier,
and validated graph updates.

Requirements: 3.1, 3.2, 3.5
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from conviction_room.models.graph import DimensionGraph
from conviction_room.models.plugin import PluginError
from conviction_room.services.dependency_graph import DependencyGraphService

router = APIRouter(prefix="/dimensions", tags=["dependency-graph"])

# Module-level service instance
_graph_service = DependencyGraphService()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/graph")
def get_graph() -> dict:
    """Return the full DAG as an adjacency list."""
    graph = _graph_service.get_graph()
    adjacency: dict[str, list[str]] = {}
    for node in graph.nodes:
        adjacency[node.dimension] = list(node.depends_on)
    return {"adjacency": adjacency}


@router.get("/order")
def get_order() -> dict:
    """Return the topological ordering of dimensions."""
    order = _graph_service.get_topological_order()
    return {"order": order}


@router.get("/{dim}/dependencies")
def get_dependencies(dim: str) -> dict:
    """Return upstream dependencies for a dimension."""
    deps = _graph_service.get_dependencies(dim)
    return {"dimension": dim, "dependencies": deps}


@router.get("/{dim}/tier")
def get_tier(dim: str) -> dict:
    """Return the tier classification for a dimension."""
    try:
        tier = _graph_service.get_tier(dim)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Dimension '{dim}' not found in graph")
    return {"dimension": dim, "tier": tier}


@router.put("/graph")
def update_graph(graph: DimensionGraph) -> DimensionGraph:
    """Update the DAG (validated for cycles).

    Returns the updated graph on success, or HTTP 400 with cycle details
    on failure.
    """
    result = _graph_service.update_graph(graph)
    if isinstance(result, PluginError):
        raise HTTPException(
            status_code=400,
            detail=result.model_dump(mode="json"),
        )
    return result
