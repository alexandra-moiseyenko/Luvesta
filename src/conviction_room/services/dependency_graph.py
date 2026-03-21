"""Dimension Dependency Graph service for Conviction Room.

Maintains the directed acyclic graph (DAG) of dimension dependencies.
Provides cycle detection, topological ordering, dependency queries,
and tier classification.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError


class DependencyGraphService:
    """In-memory dimension dependency graph.

    Stores a ``DimensionGraph`` and exposes methods for querying
    topological order, dependencies, and tier classification.
    Validates acyclicity on every load/update.
    """

    def __init__(self) -> None:
        self._graph: DimensionGraph = DimensionGraph(nodes=[])

    # ------------------------------------------------------------------
    # load_graph
    # ------------------------------------------------------------------

    def load_graph(self, graph: DimensionGraph) -> None:
        """Load or replace the graph after validating for cycles.

        Raises ``ValueError`` if the graph contains a cycle.
        """
        cycle = _detect_cycle(graph)
        if cycle is not None:
            raise ValueError(
                f"Cycle detected in dimension dependency graph: {' -> '.join(cycle)}"
            )
        self._graph = _classify_tiers(graph)

    # ------------------------------------------------------------------
    # get_graph
    # ------------------------------------------------------------------

    def get_graph(self) -> DimensionGraph:
        """Return the current dimension dependency graph."""
        return self._graph

    # ------------------------------------------------------------------
    # get_topological_order
    # ------------------------------------------------------------------

    def get_topological_order(self) -> list[str]:
        """Return dimensions in topological order (Kahn's algorithm).

        For every edge (u, v) — meaning v depends on u — u appears
        before v in the returned list.
        """
        return _topological_sort(self._graph)

    # ------------------------------------------------------------------
    # get_dependencies
    # ------------------------------------------------------------------

    def get_dependencies(self, dimension: str) -> list[str]:
        """Return upstream dependencies for *dimension*.

        Returns an empty list if the dimension has no dependencies or
        is not found in the graph.
        """
        for node in self._graph.nodes:
            if node.dimension == dimension:
                return list(node.depends_on)
        return []

    # ------------------------------------------------------------------
    # get_tier
    # ------------------------------------------------------------------

    def get_tier(self, dimension: str) -> str:
        """Return the tier classification for *dimension*.

        Returns ``"foundation"``, ``"mid-tier"``, or ``"leaf"``.
        Raises ``KeyError`` if the dimension is not in the graph.
        """
        for node in self._graph.nodes:
            if node.dimension == dimension:
                return node.tier
        raise KeyError(f"Dimension '{dimension}' not found in graph")

    # ------------------------------------------------------------------
    # update_graph
    # ------------------------------------------------------------------

    def update_graph(self, graph: DimensionGraph) -> DimensionGraph | PluginError:
        """Validate the new graph for cycles, then replace the current one.

        Returns the updated ``DimensionGraph`` on success, or a
        ``PluginError`` with ``error_code="CYCLE_DETECTED"`` on failure.
        """
        cycle = _detect_cycle(graph)
        if cycle is not None:
            return PluginError(
                error_code="CYCLE_DETECTED",
                message="Dimension dependency graph contains a cycle",
                details=[" -> ".join(cycle)],
            )
        self._graph = _classify_tiers(graph)
        return self._graph


# ======================================================================
# Private helpers
# ======================================================================


def _detect_cycle(graph: DimensionGraph) -> list[str] | None:
    """DFS-based cycle detection.

    Returns the cycle path as a list of dimension names if a cycle is
    found, or ``None`` if the graph is acyclic.
    """
    adjacency: dict[str, list[str]] = {}
    for node in graph.nodes:
        adjacency[node.dimension] = list(node.depends_on)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {dim: WHITE for dim in adjacency}
    parent: dict[str, str | None] = {dim: None for dim in adjacency}

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        for v in adjacency.get(u, []):
            if v not in color:
                # dependency references a dimension not in the graph — skip
                continue
            if color[v] == GRAY:
                # Back edge found → reconstruct cycle
                cycle = [v, u]
                cur = u
                while cur != v:
                    cur = parent[cur]  # type: ignore[assignment]
                    if cur is None:
                        break
                    cycle.append(cur)
                cycle.reverse()
                return cycle
            if color[v] == WHITE:
                parent[v] = u
                result = dfs(v)
                if result is not None:
                    return result
        color[u] = BLACK
        return None

    for dim in adjacency:
        if color[dim] == WHITE:
            result = dfs(dim)
            if result is not None:
                return result
    return None


def _topological_sort(graph: DimensionGraph) -> list[str]:
    """Kahn's algorithm for topological sorting.

    Returns dimensions ordered so that for every edge (u, v) — where v
    depends on u — u appears before v.
    """
    node_set = {node.dimension for node in graph.nodes}
    in_degree: dict[str, int] = {node.dimension: 0 for node in graph.nodes}
    # adjacency: u -> list of v where v depends on u
    forward: dict[str, list[str]] = {node.dimension: [] for node in graph.nodes}

    for node in graph.nodes:
        for dep in node.depends_on:
            if dep in node_set:
                in_degree[node.dimension] += 1
                forward.setdefault(dep, []).append(node.dimension)

    queue = sorted(dim for dim, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while queue:
        u = queue.pop(0)
        order.append(u)
        for v in sorted(forward.get(u, [])):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    return order


def _classify_tiers(graph: DimensionGraph) -> DimensionGraph:
    """Recompute tier classifications based on graph structure.

    - ``"foundation"``: no upstream dependencies (depends_on is empty)
    - ``"mid-tier"``: depends only on foundation dimensions
    - ``"leaf"``: depends on any non-foundation dimension
    """
    node_map = {node.dimension: node for node in graph.nodes}
    tier_map: dict[str, str] = {}

    # First pass: identify foundations
    for node in graph.nodes:
        if not node.depends_on:
            tier_map[node.dimension] = "foundation"

    # Second pass: classify mid-tier and leaf
    for node in graph.nodes:
        if node.dimension in tier_map:
            continue
        all_deps_foundation = all(
            tier_map.get(dep) == "foundation" for dep in node.depends_on
        )
        if all_deps_foundation:
            tier_map[node.dimension] = "mid-tier"
        else:
            tier_map[node.dimension] = "leaf"

    # Build new graph with corrected tiers
    new_nodes = [
        DimensionNode(
            dimension=node.dimension,
            tier=tier_map.get(node.dimension, "foundation"),
            depends_on=node.depends_on,
        )
        for node in graph.nodes
    ]
    return DimensionGraph(nodes=new_nodes)
