"""Unit tests for Plugin Router dispatch flow.

Tests cover: successful dispatch, no active plugin error, budget exceeded
rejection, cost recording after dispatch, and trace emission after dispatch.

**Validates: Requirements 2.2, 2.3, 2.6, 7.2, 12.1**
"""

from __future__ import annotations

from uuid import uuid4

from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from conviction_room.models.cost import CostBudget
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.router import PluginRouterService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(dimension: str = "test-dim", version: str = "1.0.0") -> PluginContractBase:
    return PluginContractBase(
        version=version,
        dimension=dimension,
        endpoints=[
            Endpoint(name="run", method="POST", path="/run"),
        ],
        health_check=Endpoint(name="health", method="GET", path="/health"),
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=1_048_576,
        ),
    )


def _make_plugin(dimension: str = "test-dim", contract_version: str = "1.0.0") -> PluginMetadata:
    return PluginMetadata(
        plugin_id=uuid4(),
        dimension=dimension,
        name="test-plugin",
        version="1.0.0",
        contract_version=contract_version,
        status="inactive",
        endpoint_base_url="http://localhost:8000",
    )


def _valid_endpoints() -> list[dict]:
    return [
        {"name": "run", "method": "POST", "path": "/run"},
        {"name": "health", "method": "GET", "path": "/health"},
    ]


def _setup_router_with_active_plugin(
    dimension: str = "test-dim",
) -> tuple[PluginRouterService, PluginRegistryService, CostGovernorService, PluginMetadata]:
    """Register and activate a plugin, return (router, registry, cost_gov, plugin)."""
    registry = PluginRegistryService()
    cost_gov = CostGovernorService()
    router = PluginRouterService(registry=registry, cost_governor=cost_gov)

    contract = _make_contract(dimension=dimension)
    plugin = _make_plugin(dimension=dimension)
    registry.register(plugin, contract, _valid_endpoints())
    registry.activate(plugin.plugin_id)

    return router, registry, cost_gov, plugin


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSuccessfulDispatch:
    """Successful dispatch: register, activate, dispatch, verify response."""

    def test_dispatch_returns_expected_fields(self) -> None:
        router, _, _, plugin = _setup_router_with_active_plugin()

        result = router.dispatch("test-dim", "/run", {"query": "test"})

        assert isinstance(result, dict)
        assert result["plugin_id"] == str(plugin.plugin_id)
        assert result["dimension"] == "test-dim"
        assert result["endpoint"] == "/run"
        assert result["status"] == "dispatched"


class TestNoActivePluginError:
    """Dispatch to a dimension with no active plugin → PluginError."""

    def test_dispatch_no_active_plugin_returns_error(self) -> None:
        registry = PluginRegistryService()
        cost_gov = CostGovernorService()
        router = PluginRouterService(registry=registry, cost_governor=cost_gov)

        result = router.dispatch("empty-dimension", "/run", {})

        assert isinstance(result, PluginError)
        assert result.error_code == "PLUGIN_NOT_FOUND"

    def test_dispatch_inactive_plugin_returns_error(self) -> None:
        """Plugin registered but not activated → still returns error."""
        registry = PluginRegistryService()
        cost_gov = CostGovernorService()
        router = PluginRouterService(registry=registry, cost_governor=cost_gov)

        contract = _make_contract()
        plugin = _make_plugin()
        registry.register(plugin, contract, _valid_endpoints())
        # Do NOT activate

        result = router.dispatch("test-dim", "/run", {})

        assert isinstance(result, PluginError)
        assert result.error_code == "PLUGIN_NOT_FOUND"


class TestBudgetExceededRejection:
    """Set a tight budget, exhaust it, then dispatch → BUDGET_EXCEEDED."""

    def test_dispatch_rejected_when_budget_exceeded(self) -> None:
        router, _, cost_gov, plugin = _setup_router_with_active_plugin()

        # Set a very tight budget that will be exceeded after a few dispatches
        budget = CostBudget(
            scope="global_period",
            dimension=None,
            period="daily",
            max_tokens=100,
            max_api_calls=100,
            max_dollar_cost=0.002,
        )
        cost_gov.set_budget(budget)

        # First dispatch should succeed (costs 0.001)
        result1 = router.dispatch("test-dim", "/run", {"q": "first"})
        assert isinstance(result1, dict)
        assert result1["status"] == "dispatched"

        # Second dispatch should succeed (cumulative 0.002)
        result2 = router.dispatch("test-dim", "/run", {"q": "second"})
        assert isinstance(result2, dict)

        # Third dispatch should be rejected (would push to 0.003 > 0.002)
        result3 = router.dispatch("test-dim", "/run", {"q": "third"})
        assert isinstance(result3, PluginError)
        assert result3.error_code == "BUDGET_EXCEEDED"


class TestCostRecording:
    """After a successful dispatch, verify a cost record in the ledger."""

    def test_cost_record_added_after_dispatch(self) -> None:
        router, _, cost_gov, plugin = _setup_router_with_active_plugin()

        # Ledger should be empty before dispatch
        assert len(cost_gov.get_ledger()) == 0

        router.dispatch("test-dim", "/run", {"query": "test"})

        ledger = cost_gov.get_ledger()
        assert len(ledger) == 1

        record = ledger[0]
        assert record.dimension == "test-dim"
        assert record.plugin_id == plugin.plugin_id
        assert record.dollar_cost > 0
        assert record.api_calls == 1

    def test_multiple_dispatches_accumulate_cost(self) -> None:
        router, _, cost_gov, _ = _setup_router_with_active_plugin()

        router.dispatch("test-dim", "/run", {"q": "1"})
        router.dispatch("test-dim", "/run", {"q": "2"})
        router.dispatch("test-dim", "/run", {"q": "3"})

        ledger = cost_gov.get_ledger()
        assert len(ledger) == 3


class TestTraceEmission:
    """After a successful dispatch, verify a TraceEvent was emitted."""

    def test_trace_emitted_after_dispatch(self) -> None:
        router, _, _, plugin = _setup_router_with_active_plugin()

        # No traces before dispatch
        assert len(router.get_traces()) == 0

        router.dispatch("test-dim", "/run", {"query": "test"})

        traces = router.get_traces()
        assert len(traces) == 1

        trace = traces[0]
        assert trace.dimension == "test-dim"
        assert trace.plugin_id == plugin.plugin_id
        assert trace.success is True
        assert trace.latency_ms >= 0
        assert trace.cost_usd > 0

    def test_no_trace_on_budget_rejection(self) -> None:
        """When budget is exceeded, no trace should be emitted."""
        router, _, cost_gov, _ = _setup_router_with_active_plugin()

        # Budget allows exactly one dispatch (0.001) but not two
        budget = CostBudget(
            scope="global_period",
            dimension=None,
            period="daily",
            max_tokens=100,
            max_api_calls=100,
            max_dollar_cost=0.0015,
        )
        cost_gov.set_budget(budget)

        # First dispatch succeeds and emits a trace
        result1 = router.dispatch("test-dim", "/run", {"q": "1"})
        assert isinstance(result1, dict)
        assert len(router.get_traces()) == 1

        # Second dispatch rejected — no new trace
        result2 = router.dispatch("test-dim", "/run", {"q": "2"})
        assert isinstance(result2, PluginError)
        assert len(router.get_traces()) == 1
