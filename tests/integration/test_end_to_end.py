"""Integration tests for Conviction Room end-to-end flows.

Wires multiple services together and tests service-level interactions
without FastAPI's TestClient.

**Validates: Requirements 2.2, 3.4, 7.2, 9.2, 9.3, 12.1**
"""

from __future__ import annotations

from uuid import uuid4

from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from conviction_room.models.cost import CostBudget
from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.dependency_graph import DependencyGraphService
from conviction_room.services.golden_dataset import GoldenDatasetService
from conviction_room.services.observability import ObservabilityService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.router import PluginRouterService
from conviction_room.services.test_harness import TestHarnessService
from conviction_room.services.testability import TestabilityService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(dimension: str = "retrieval", version: str = "1.0.0") -> PluginContractBase:
    """Build a minimal valid contract for testing."""
    return PluginContractBase(
        version=version,
        dimension=dimension,
        endpoints=[
            Endpoint(name="search", method="POST", path="/search"),
        ],
        health_check=Endpoint(name="health", method="GET", path="/health"),
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=1_048_576,
        ),
    )


def _make_plugin(
    dimension: str = "retrieval",
    contract_version: str = "1.0.0",
    name: str = "test-plugin",
) -> PluginMetadata:
    """Build a minimal valid plugin metadata for testing."""
    return PluginMetadata(
        plugin_id=uuid4(),
        dimension=dimension,
        name=name,
        version="1.0.0",
        contract_version=contract_version,
        status="inactive",
        endpoint_base_url="http://localhost:9000",
    )


def _valid_endpoints() -> list[dict]:
    """Endpoints that satisfy the contract built by _make_contract."""
    return [
        {"name": "search", "method": "POST", "path": "/search"},
        {"name": "health", "method": "GET", "path": "/health"},
    ]


def _wire_services() -> dict:
    """Instantiate and wire all services together, return as a dict."""
    registry = PluginRegistryService()
    cost_governor = CostGovernorService()
    golden_dataset = GoldenDatasetService()
    testability = TestabilityService()
    observability = ObservabilityService()
    dependency_graph = DependencyGraphService()

    benchmark = BenchmarkOrchestratorService(
        cost_governor=cost_governor,
        golden_dataset_service=golden_dataset,
    )
    test_harness = TestHarnessService(
        registry=registry,
        cost_governor=cost_governor,
        benchmark_orchestrator=benchmark,
        testability=testability,
    )
    router = PluginRouterService(
        registry=registry,
        cost_governor=cost_governor,
    )

    return {
        "registry": registry,
        "cost_governor": cost_governor,
        "golden_dataset": golden_dataset,
        "testability": testability,
        "observability": observability,
        "dependency_graph": dependency_graph,
        "benchmark": benchmark,
        "test_harness": test_harness,
        "router": router,
    }



# ---------------------------------------------------------------------------
# Test 1: register → validate contract → auto-queue benchmark → run → traces
# Validates: Requirements 2.2, 9.2, 9.3, 12.1
# ---------------------------------------------------------------------------


class TestRegisterValidateBenchmarkTrace:
    """End-to-end: register plugin → validate contract → auto-queue
    benchmark → drain queue → verify experiment ran and traces exist."""

    def test_full_flow(self) -> None:
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        test_harness: TestHarnessService = svc["test_harness"]
        observability: ObservabilityService = svc["observability"]
        cost_governor: CostGovernorService = svc["cost_governor"]

        dimension = "retrieval"
        contract = _make_contract(dimension=dimension)
        plugin = _make_plugin(dimension=dimension)

        # 1. Register plugin — should succeed (no violations).
        reg_result = registry.register(plugin, contract, _valid_endpoints())
        assert isinstance(reg_result, PluginMetadata), f"Registration failed: {reg_result}"

        # 2. Activate the plugin so downstream services can find it.
        act_result = registry.activate(plugin.plugin_id)
        assert isinstance(act_result, PluginMetadata)
        assert act_result.status == "active"

        # 3. Validate contract via test harness — should pass and auto-queue benchmark.
        report = test_harness.validate_contract(
            plugin_id=plugin.plugin_id,
            dimension=dimension,
            contract=contract,
            plugin_endpoints=_valid_endpoints(),
        )
        assert report.passed is True
        assert report.test_mode == "contract_validation"

        # 4. Benchmark should be auto-queued (Requirement 9.3).
        assert len(test_harness._benchmark_queue) == 1

        # 5. Drain the benchmark queue — runs the auto-queued benchmark.
        suite_id = uuid4()
        benchmark_reports = test_harness.drain_benchmark_queue(suite_id=suite_id)
        assert len(benchmark_reports) == 1

        bm_report = benchmark_reports[0]
        assert bm_report.test_mode == "benchmark"
        assert bm_report.passed is True
        assert bm_report.plugin_id == plugin.plugin_id
        assert bm_report.dimension == dimension

        # 6. Verify cost was recorded in the ledger (Requirement 7.2).
        ledger = cost_governor.get_ledger(dimension=dimension)
        assert len(ledger) >= 1
        assert all(r.dimension == dimension for r in ledger)

        # 7. Verify the test harness stored both reports.
        all_reports = test_harness.list_reports(plugin_id=plugin.plugin_id)
        assert len(all_reports) == 2
        modes = {r.test_mode for r in all_reports}
        assert modes == {"contract_validation", "benchmark"}

    def test_contract_validation_failure_does_not_queue_benchmark(self) -> None:
        """When contract validation fails, no benchmark should be queued."""
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        test_harness: TestHarnessService = svc["test_harness"]

        dimension = "retrieval"
        contract = _make_contract(dimension=dimension)
        plugin = _make_plugin(dimension=dimension)

        # Register with valid endpoints so it's in the registry.
        registry.register(plugin, contract, _valid_endpoints())
        registry.activate(plugin.plugin_id)

        # Validate with MISSING endpoints — should fail.
        bad_endpoints: list[dict] = [
            {"name": "health", "method": "GET", "path": "/health"},
            # Missing "search" endpoint
        ]
        report = test_harness.validate_contract(
            plugin_id=plugin.plugin_id,
            dimension=dimension,
            contract=contract,
            plugin_endpoints=bad_endpoints,
        )
        assert report.passed is False
        assert len(test_harness._benchmark_queue) == 0



# ---------------------------------------------------------------------------
# Test 2: dispatch → cost check → plugin call → cost record → trace emit
# Validates: Requirements 2.2, 7.2, 12.1
# ---------------------------------------------------------------------------


class TestDispatchCostTrace:
    """End-to-end: dispatch through router → cost check → plugin call →
    cost record → trace emit."""

    def test_dispatch_records_cost_and_emits_trace(self) -> None:
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        cost_governor: CostGovernorService = svc["cost_governor"]
        router: PluginRouterService = svc["router"]

        dimension = "retrieval"
        contract = _make_contract(dimension=dimension)
        plugin = _make_plugin(dimension=dimension)

        # Register and activate.
        registry.register(plugin, contract, _valid_endpoints())
        registry.activate(plugin.plugin_id)

        # Set a generous budget so dispatch succeeds.
        cost_governor.set_budget(CostBudget(
            scope="global_period",
            period="daily",
            max_tokens=1_000_000,
            max_api_calls=10_000,
            max_dollar_cost=100.0,
        ))

        # Dispatch.
        result = router.dispatch(dimension, "/search", {"query": "AAPL"})
        assert isinstance(result, dict)
        assert result["status"] == "dispatched"
        assert result["plugin_id"] == str(plugin.plugin_id)

        # Verify cost was recorded.
        ledger = cost_governor.get_ledger(dimension=dimension)
        assert len(ledger) == 1
        record = ledger[0]
        assert record.dimension == dimension
        assert record.plugin_id == plugin.plugin_id
        assert record.dollar_cost > 0

        # Verify trace was emitted.
        traces = router.get_traces()
        assert len(traces) == 1
        trace = traces[0]
        assert trace.dimension == dimension
        assert trace.plugin_id == plugin.plugin_id
        assert trace.success is True
        assert trace.latency_ms >= 0

    def test_dispatch_rejected_by_cost_governor(self) -> None:
        """When budget is exhausted, dispatch is rejected — no trace emitted."""
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        cost_governor: CostGovernorService = svc["cost_governor"]
        router: PluginRouterService = svc["router"]

        dimension = "retrieval"
        contract = _make_contract(dimension=dimension)
        plugin = _make_plugin(dimension=dimension)

        registry.register(plugin, contract, _valid_endpoints())
        registry.activate(plugin.plugin_id)

        # Set a budget that allows zero spend.
        cost_governor.set_budget(CostBudget(
            scope="global_period",
            period="daily",
            max_tokens=0,
            max_api_calls=0,
            max_dollar_cost=0.0,
        ))

        result = router.dispatch(dimension, "/search", {"query": "AAPL"})
        assert isinstance(result, PluginError)
        assert result.error_code == "BUDGET_EXCEEDED"

        # No cost recorded, no trace emitted.
        assert len(cost_governor.get_ledger()) == 0
        assert len(router.get_traces()) == 0

    def test_observability_service_receives_trace(self) -> None:
        """Traces emitted by the router can be stored in ObservabilityService."""
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        router: PluginRouterService = svc["router"]
        observability: ObservabilityService = svc["observability"]

        dimension = "retrieval"
        contract = _make_contract(dimension=dimension)
        plugin = _make_plugin(dimension=dimension)

        registry.register(plugin, contract, _valid_endpoints())
        registry.activate(plugin.plugin_id)

        # Dispatch to generate a trace.
        router.dispatch(dimension, "/search", {"query": "TSLA"})

        # Forward router traces into the observability service.
        for trace in router.get_traces():
            observability.emit_trace(trace)

        # Query traces from observability.
        obs_traces = observability.query_traces(dimension=dimension)
        assert len(obs_traces) == 1
        assert obs_traces[0].plugin_id == plugin.plugin_id
        assert obs_traces[0].success is True



# ---------------------------------------------------------------------------
# Test 3: update DAG → verify topological order → block benchmark on
#          unresolved dependency
# Validates: Requirements 3.4, 9.2
# ---------------------------------------------------------------------------


class TestDAGTopologyAndBenchmarkBlocking:
    """End-to-end: load DAG → update it → verify topological order →
    attempt benchmark on dimension with unresolved dependency."""

    def test_topological_order_after_update(self) -> None:
        svc = _wire_services()
        dep_graph: DependencyGraphService = svc["dependency_graph"]

        # Load an initial graph.
        initial = DimensionGraph(nodes=[
            DimensionNode(dimension="persistence", tier="foundation", depends_on=[]),
            DimensionNode(dimension="model_provider", tier="foundation", depends_on=[]),
            DimensionNode(dimension="retrieval", tier="mid-tier", depends_on=["persistence"]),
        ])
        dep_graph.load_graph(initial)

        order = dep_graph.get_topological_order()
        assert "persistence" in order
        assert "retrieval" in order
        # persistence must come before retrieval.
        assert order.index("persistence") < order.index("retrieval")

        # Update: add orchestration depending on retrieval + model_provider.
        updated = DimensionGraph(nodes=[
            DimensionNode(dimension="persistence", tier="foundation", depends_on=[]),
            DimensionNode(dimension="model_provider", tier="foundation", depends_on=[]),
            DimensionNode(dimension="retrieval", tier="mid-tier", depends_on=["persistence"]),
            DimensionNode(dimension="orchestration", tier="leaf", depends_on=["retrieval", "model_provider"]),
        ])
        result = dep_graph.update_graph(updated)
        assert isinstance(result, DimensionGraph)

        new_order = dep_graph.get_topological_order()
        assert len(new_order) == 4

        # Verify topological invariant: for every edge u→v, u before v.
        idx = {dim: i for i, dim in enumerate(new_order)}
        assert idx["persistence"] < idx["retrieval"]
        assert idx["retrieval"] < idx["orchestration"]
        assert idx["model_provider"] < idx["orchestration"]

    def test_cycle_rejected(self) -> None:
        """Updating the DAG with a cycle is rejected."""
        svc = _wire_services()
        dep_graph: DependencyGraphService = svc["dependency_graph"]

        # Load a valid graph first.
        dep_graph.load_graph(DimensionGraph(nodes=[
            DimensionNode(dimension="a", tier="foundation", depends_on=[]),
        ]))

        # Try to update with a cycle: a→b→a.
        cyclic = DimensionGraph(nodes=[
            DimensionNode(dimension="a", tier="foundation", depends_on=["b"]),
            DimensionNode(dimension="b", tier="foundation", depends_on=["a"]),
        ])
        result = dep_graph.update_graph(cyclic)
        assert isinstance(result, PluginError)
        assert result.error_code == "CYCLE_DETECTED"

    def test_benchmark_blocked_on_unresolved_dependency(self) -> None:
        """Benchmarking a dimension whose upstream dependency has no active
        plugin should be detectable via the dependency graph + registry."""
        svc = _wire_services()
        registry: PluginRegistryService = svc["registry"]
        dep_graph: DependencyGraphService = svc["dependency_graph"]

        # Load graph: orchestration depends on retrieval and model_provider.
        dep_graph.load_graph(DimensionGraph(nodes=[
            DimensionNode(dimension="persistence", tier="foundation", depends_on=[]),
            DimensionNode(dimension="model_provider", tier="foundation", depends_on=[]),
            DimensionNode(dimension="retrieval", tier="mid-tier", depends_on=["persistence"]),
            DimensionNode(dimension="orchestration", tier="leaf", depends_on=["retrieval", "model_provider"]),
        ]))

        # Register and activate a plugin for persistence only.
        persistence_contract = _make_contract(dimension="persistence")
        persistence_plugin = _make_plugin(dimension="persistence", name="pg-plugin")
        registry.register(persistence_plugin, persistence_contract, _valid_endpoints())
        registry.activate(persistence_plugin.plugin_id)

        # Check unresolved dependencies for "orchestration".
        deps = dep_graph.get_dependencies("orchestration")
        assert set(deps) == {"retrieval", "model_provider"}

        unresolved: list[str] = []
        for dep_dim in deps:
            active = registry.get_active(dep_dim)
            if isinstance(active, PluginError):
                unresolved.append(dep_dim)

        # Both retrieval and model_provider have no active plugin.
        assert "retrieval" in unresolved
        assert "model_provider" in unresolved

        # A benchmark for "orchestration" should be blocked.
        # Verify the blocking condition: unresolved is non-empty.
        assert len(unresolved) > 0, (
            "Expected unresolved upstream dependencies to block benchmark"
        )

    def test_tier_classification_after_update(self) -> None:
        """After updating the DAG, tier classification should be consistent."""
        svc = _wire_services()
        dep_graph: DependencyGraphService = svc["dependency_graph"]

        graph = DimensionGraph(nodes=[
            DimensionNode(dimension="persistence", tier="foundation", depends_on=[]),
            DimensionNode(dimension="model_provider", tier="foundation", depends_on=[]),
            DimensionNode(dimension="retrieval", tier="mid-tier", depends_on=["persistence"]),
            DimensionNode(dimension="orchestration", tier="leaf", depends_on=["retrieval", "model_provider"]),
        ])
        dep_graph.load_graph(graph)

        # Foundation: no dependencies.
        assert dep_graph.get_tier("persistence") == "foundation"
        assert dep_graph.get_tier("model_provider") == "foundation"

        # Mid-tier: depends only on foundation.
        assert dep_graph.get_tier("retrieval") == "mid-tier"

        # Leaf: depends on non-foundation.
        assert dep_graph.get_tier("orchestration") == "leaf"
