"""Unit tests for DependencyGraphService.

Covers: load/get graph, topological order, dependency queries,
tier classification, cycle detection, and update_graph.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import pytest

from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError
from conviction_room.services.dependency_graph import DependencyGraphService


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_graph(nodes: list[DimensionNode]) -> DimensionGraph:
    return DimensionGraph(nodes=nodes)


def _linear_graph() -> DimensionGraph:
    """A -> B -> C (linear chain)."""
    return _make_graph([
        DimensionNode(dimension="A", tier="foundation", depends_on=[]),
        DimensionNode(dimension="B", tier="mid-tier", depends_on=["A"]),
        DimensionNode(dimension="C", tier="leaf", depends_on=["B"]),
    ])


def _diamond_graph() -> DimensionGraph:
    """A -> B, A -> C, B -> D, C -> D (diamond)."""
    return _make_graph([
        DimensionNode(dimension="A", tier="foundation", depends_on=[]),
        DimensionNode(dimension="B", tier="mid-tier", depends_on=["A"]),
        DimensionNode(dimension="C", tier="mid-tier", depends_on=["A"]),
        DimensionNode(dimension="D", tier="leaf", depends_on=["B", "C"]),
    ])


# ------------------------------------------------------------------
# load_graph / get_graph
# ------------------------------------------------------------------


class TestLoadAndGetGraph:
    def test_load_valid_graph(self) -> None:
        svc = DependencyGraphService()
        graph = _linear_graph()
        svc.load_graph(graph)
        result = svc.get_graph()
        assert len(result.nodes) == 3

    def test_load_empty_graph(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(DimensionGraph(nodes=[]))
        assert svc.get_graph().nodes == []

    def test_load_graph_with_cycle_raises(self) -> None:
        svc = DependencyGraphService()
        cyclic = _make_graph([
            DimensionNode(dimension="A", tier="foundation", depends_on=["B"]),
            DimensionNode(dimension="B", tier="foundation", depends_on=["A"]),
        ])
        with pytest.raises(ValueError, match="Cycle detected"):
            svc.load_graph(cyclic)

    def test_load_replaces_previous_graph(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert len(svc.get_graph().nodes) == 3
        svc.load_graph(_diamond_graph())
        assert len(svc.get_graph().nodes) == 4


# ------------------------------------------------------------------
# get_topological_order
# ------------------------------------------------------------------


class TestTopologicalOrder:
    def test_linear_order(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        order = svc.get_topological_order()
        assert order.index("A") < order.index("B") < order.index("C")

    def test_diamond_order(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_diamond_graph())
        order = svc.get_topological_order()
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_empty_graph_order(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(DimensionGraph(nodes=[]))
        assert svc.get_topological_order() == []

    def test_all_foundations_order(self) -> None:
        svc = DependencyGraphService()
        graph = _make_graph([
            DimensionNode(dimension="X", tier="foundation", depends_on=[]),
            DimensionNode(dimension="Y", tier="foundation", depends_on=[]),
        ])
        svc.load_graph(graph)
        order = svc.get_topological_order()
        assert set(order) == {"X", "Y"}


# ------------------------------------------------------------------
# get_dependencies
# ------------------------------------------------------------------


class TestGetDependencies:
    def test_foundation_has_no_deps(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_dependencies("A") == []

    def test_mid_tier_deps(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_dependencies("B") == ["A"]

    def test_leaf_deps(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_diamond_graph())
        assert set(svc.get_dependencies("D")) == {"B", "C"}

    def test_unknown_dimension_returns_empty(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_dependencies("UNKNOWN") == []


# ------------------------------------------------------------------
# get_tier
# ------------------------------------------------------------------


class TestGetTier:
    def test_foundation_tier(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_tier("A") == "foundation"

    def test_mid_tier(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_tier("B") == "mid-tier"

    def test_leaf_tier(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        assert svc.get_tier("C") == "leaf"

    def test_diamond_leaf(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_diamond_graph())
        # D depends on B and C (both mid-tier), so D is leaf
        assert svc.get_tier("D") == "leaf"

    def test_unknown_dimension_raises(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        with pytest.raises(KeyError, match="not found"):
            svc.get_tier("UNKNOWN")


# ------------------------------------------------------------------
# update_graph
# ------------------------------------------------------------------


class TestUpdateGraph:
    def test_update_valid_graph(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        result = svc.update_graph(_diamond_graph())
        assert isinstance(result, DimensionGraph)
        assert len(result.nodes) == 4

    def test_update_with_cycle_returns_error(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        cyclic = _make_graph([
            DimensionNode(dimension="X", tier="foundation", depends_on=["Z"]),
            DimensionNode(dimension="Y", tier="foundation", depends_on=["X"]),
            DimensionNode(dimension="Z", tier="foundation", depends_on=["Y"]),
        ])
        result = svc.update_graph(cyclic)
        assert isinstance(result, PluginError)
        assert result.error_code == "CYCLE_DETECTED"
        assert len(result.details) > 0

    def test_update_with_cycle_preserves_old_graph(self) -> None:
        svc = DependencyGraphService()
        svc.load_graph(_linear_graph())
        cyclic = _make_graph([
            DimensionNode(dimension="X", tier="foundation", depends_on=["Y"]),
            DimensionNode(dimension="Y", tier="foundation", depends_on=["X"]),
        ])
        svc.update_graph(cyclic)
        # Old graph should still be intact
        assert len(svc.get_graph().nodes) == 3


# ------------------------------------------------------------------
# Tier reclassification on load
# ------------------------------------------------------------------


class TestTierReclassification:
    def test_tiers_are_recomputed_on_load(self) -> None:
        """Even if input tiers are wrong, load_graph recomputes them."""
        svc = DependencyGraphService()
        graph = _make_graph([
            DimensionNode(dimension="A", tier="leaf", depends_on=[]),  # wrong tier
            DimensionNode(dimension="B", tier="foundation", depends_on=["A"]),  # wrong
        ])
        svc.load_graph(graph)
        assert svc.get_tier("A") == "foundation"
        assert svc.get_tier("B") == "mid-tier"
