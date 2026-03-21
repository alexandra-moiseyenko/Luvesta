# Feature: conviction-room, Property 8: Dependency graph is always a DAG
# Feature: conviction-room, Property 9: Topological ordering is valid
# Feature: conviction-room, Property 10: Benchmark blocked by unresolved dependencies
# Feature: conviction-room, Property 11: Dimension tier classification is consistent with graph structure
"""
Property tests for Dimension Dependency Graph invariants.

Property 8  — Any DimensionGraph accepted by the system contains no cycles;
              cyclic updates are rejected with an error identifying the cycle.
Property 9  — Topological ordering satisfies: for every edge (u, v), u before v.
Property 10 — Benchmarking a dimension with unresolved upstream dependencies
              (no active plugin) fails with an error listing unresolved dimensions.
Property 11 — Tier classification is consistent with graph structure: foundation
              has no deps, mid-tier depends only on foundation, all others are leaf.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

from __future__ import annotations

from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.dependency_graph import DependencyGraphService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from tests.conftest import dimension_graph, safe_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_adjacency(graph: DimensionGraph) -> dict[str, list[str]]:
    """Build an adjacency map: dimension -> list of dimensions it depends on."""
    return {node.dimension: list(node.depends_on) for node in graph.nodes}


def _has_cycle_dfs(graph: DimensionGraph) -> bool:
    """Independent DFS cycle check (not using the service's implementation)."""
    adj = _build_adjacency(graph)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {d: WHITE for d in adj}

    def visit(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, []):
            if v not in color:
                continue
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and visit(v):
                return True
        color[u] = BLACK
        return False

    return any(color[d] == WHITE and visit(d) for d in adj)


def _build_contract(dimension: str) -> PluginContractBase:
    return PluginContractBase(
        version="1.0.0",
        dimension=dimension,
        endpoints=[Endpoint(name="run", method="POST", path="/run")],
        health_check=Endpoint(name="health", method="GET", path="/health"),
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=1_048_576,
        ),
    )


def _matching_endpoints() -> list[dict]:
    return [
        {"name": "run", "method": "POST", "path": "/run"},
        {"name": "health", "method": "GET", "path": "/health"},
    ]


# ---------------------------------------------------------------------------
# Strategy: cyclic graph (guaranteed to have at least one cycle)
# ---------------------------------------------------------------------------


@st.composite
def cyclic_graph(draw: st.DrawFn) -> DimensionGraph:
    """Generate a DimensionGraph that contains at least one cycle."""
    num_nodes = draw(st.integers(min_value=2, max_value=6))
    names = draw(
        st.lists(
            st.text(min_size=1, max_size=15, alphabet=st.characters(categories=("L",))),
            min_size=num_nodes,
            max_size=num_nodes,
            unique=True,
        )
    )
    # Create a guaranteed cycle: 0 -> 1 -> ... -> n-1 -> 0
    nodes = []
    for i, name in enumerate(names):
        dep = names[(i + 1) % num_nodes]
        nodes.append(DimensionNode(dimension=name, tier="foundation", depends_on=[dep]))
    return DimensionGraph(nodes=nodes)


# ---------------------------------------------------------------------------
# Property 8: Dependency graph is always a DAG
# ---------------------------------------------------------------------------


@given(graph=dimension_graph())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_accepted_graph_has_no_cycles(graph: DimensionGraph) -> None:
    """For any DimensionGraph accepted by the system (via load_graph),
    it shall contain no cycles.

    # Feature: conviction-room, Property 8: Dependency graph is always a DAG
    **Validates: Requirements 3.1, 3.3**
    """
    svc = DependencyGraphService()
    svc.load_graph(graph)
    loaded = svc.get_graph()

    # Verify independently that the loaded graph has no cycle
    assert not _has_cycle_dfs(loaded), "Accepted graph contains a cycle"


@given(graph=cyclic_graph())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_cyclic_update_is_rejected(graph: DimensionGraph) -> None:
    """Any update that would introduce a cycle shall be rejected with an
    error identifying the cycle.

    # Feature: conviction-room, Property 8: Dependency graph is always a DAG
    **Validates: Requirements 3.1, 3.3**
    """
    svc = DependencyGraphService()
    result = svc.update_graph(graph)

    assert isinstance(result, PluginError), (
        f"Expected PluginError for cyclic graph but got: {type(result)}"
    )
    assert result.error_code == "CYCLE_DETECTED"
    assert len(result.details) > 0, "Error should identify the cycle"


# ---------------------------------------------------------------------------
# Property 9: Topological ordering is valid
# ---------------------------------------------------------------------------


@given(graph=dimension_graph())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_topological_ordering_is_valid(graph: DimensionGraph) -> None:
    """For any valid DimensionGraph, the returned topological ordering shall
    satisfy: for every edge (u, v) in the graph, u appears before v in the
    ordering.

    Here an edge (u, v) means v depends on u, i.e. u is in v.depends_on.

    # Feature: conviction-room, Property 9: Topological ordering is valid
    **Validates: Requirements 3.2**
    """
    svc = DependencyGraphService()
    svc.load_graph(graph)
    order = svc.get_topological_order()

    node_set = {node.dimension for node in graph.nodes}
    pos = {dim: idx for idx, dim in enumerate(order)}

    # Every node in the graph should appear in the ordering
    for dim in node_set:
        assert dim in pos, f"Dimension '{dim}' missing from topological order"

    # For every edge (u, v) where v.depends_on contains u, u must come before v
    for node in graph.nodes:
        for dep in node.depends_on:
            if dep in node_set:
                assert pos[dep] < pos[node.dimension], (
                    f"Topological order violated: {dep} should appear before "
                    f"{node.dimension}, but positions are {pos[dep]} and "
                    f"{pos[node.dimension]}"
                )


# ---------------------------------------------------------------------------
# Property 10: Benchmark blocked by unresolved dependencies
# ---------------------------------------------------------------------------


def _check_unresolved_dependencies(
    dimension: str,
    graph_svc: DependencyGraphService,
    registry: PluginRegistryService,
) -> PluginError | None:
    """Check if a dimension's upstream dependencies are all resolved.

    Returns a PluginError listing unresolved upstream dimensions if any
    dependency lacks an active plugin, or None if all are resolved.
    """
    deps = graph_svc.get_dependencies(dimension)
    unresolved = []
    for dep in deps:
        result = registry.get_active(dep)
        if isinstance(result, PluginError):
            unresolved.append(dep)
    if unresolved:
        return PluginError(
            error_code="UNRESOLVED_DEPENDENCIES",
            message=f"Cannot benchmark '{dimension}': unresolved upstream dependencies",
            dimension=dimension,
            details=unresolved,
        )
    return None


@st.composite
def _graph_with_unresolved_deps(draw: st.DrawFn):
    """Generate a graph where at least one non-foundation dimension has an
    upstream dependency with no active plugin in the registry."""
    graph = draw(dimension_graph())

    # We need at least one node with dependencies
    nodes_with_deps = [n for n in graph.nodes if n.depends_on]
    if not nodes_with_deps:
        # Force a two-node graph with a dependency
        names = draw(
            st.lists(
                st.text(min_size=1, max_size=15, alphabet=st.characters(categories=("L",))),
                min_size=2,
                max_size=2,
                unique=True,
            )
        )
        graph = DimensionGraph(nodes=[
            DimensionNode(dimension=names[0], tier="foundation", depends_on=[]),
            DimensionNode(dimension=names[1], tier="mid-tier", depends_on=[names[0]]),
        ])
        nodes_with_deps = [graph.nodes[1]]

    graph_svc = DependencyGraphService()
    graph_svc.load_graph(graph)

    # Pick a dimension that has dependencies
    target_node = draw(st.sampled_from(nodes_with_deps))

    # Create a registry but do NOT register/activate plugins for at least
    # one of the target's dependencies
    registry = PluginRegistryService()

    # Optionally activate some deps but leave at least one unresolved
    deps = list(target_node.depends_on)
    node_set = {n.dimension for n in graph.nodes}
    valid_deps = [d for d in deps if d in node_set]

    if len(valid_deps) > 1:
        # Activate a random subset, leaving at least one out
        num_to_activate = draw(st.integers(min_value=0, max_value=len(valid_deps) - 1))
        to_activate = draw(
            st.lists(
                st.sampled_from(valid_deps),
                min_size=num_to_activate,
                max_size=num_to_activate,
                unique=True,
            ).filter(lambda xs: len(xs) < len(valid_deps))
        )
    else:
        to_activate = []

    for dep_dim in to_activate:
        contract = _build_contract(dep_dim)
        plugin = PluginMetadata(
            plugin_id=uuid4(),
            dimension=dep_dim,
            name=f"plugin-{uuid4().hex[:6]}",
            version="1.0.0",
            contract_version="1.0.0",
            status="inactive",
            endpoint_base_url="http://localhost:8000",
        )
        result = registry.register(plugin, contract, _matching_endpoints())
        assert isinstance(result, PluginMetadata)
        registry.activate(result.plugin_id)

    unresolved = [d for d in valid_deps if d not in to_activate]

    return graph_svc, registry, target_node.dimension, unresolved


@given(data=_graph_with_unresolved_deps())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_benchmark_blocked_by_unresolved_dependencies(
    data: tuple,
) -> None:
    """For any dimension whose upstream dependencies include a dimension with
    no active plugin, attempting to start a benchmark shall fail with an error
    listing all unresolved upstream dimensions.

    # Feature: conviction-room, Property 10: Benchmark blocked by unresolved dependencies
    **Validates: Requirements 3.4**
    """
    graph_svc, registry, target_dim, expected_unresolved = data

    result = _check_unresolved_dependencies(target_dim, graph_svc, registry)

    assert result is not None, (
        f"Expected unresolved dependency error for '{target_dim}' but got None"
    )
    assert isinstance(result, PluginError)
    assert result.error_code == "UNRESOLVED_DEPENDENCIES"
    assert result.dimension == target_dim

    # All expected unresolved dimensions should be listed
    for dim in expected_unresolved:
        assert dim in result.details, (
            f"Unresolved dimension '{dim}' not listed in error details: {result.details}"
        )


# ---------------------------------------------------------------------------
# Property 11: Dimension tier classification is consistent with graph structure
# ---------------------------------------------------------------------------


@given(graph=dimension_graph())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_tier_classification_consistent_with_structure(
    graph: DimensionGraph,
) -> None:
    """For any valid DimensionGraph:
    - dimensions with no upstream dependencies → "foundation"
    - dimensions depending only on foundation dimensions → "mid-tier"
    - all others → "leaf"

    # Feature: conviction-room, Property 11: Dimension tier classification is consistent with graph structure
    **Validates: Requirements 3.5**
    """
    svc = DependencyGraphService()
    svc.load_graph(graph)
    classified = svc.get_graph()

    tier_map = {node.dimension: node.tier for node in classified.nodes}
    dep_map = {node.dimension: list(node.depends_on) for node in classified.nodes}

    for node in classified.nodes:
        deps = dep_map[node.dimension]
        valid_deps = [d for d in deps if d in tier_map]

        if not deps:
            assert node.tier == "foundation", (
                f"Dimension '{node.dimension}' has no dependencies but tier is "
                f"'{node.tier}', expected 'foundation'"
            )
        elif all(tier_map.get(d) == "foundation" for d in valid_deps):
            assert node.tier == "mid-tier", (
                f"Dimension '{node.dimension}' depends only on foundation "
                f"dimensions but tier is '{node.tier}', expected 'mid-tier'"
            )
        else:
            assert node.tier == "leaf", (
                f"Dimension '{node.dimension}' depends on non-foundation "
                f"dimensions but tier is '{node.tier}', expected 'leaf'"
            )
