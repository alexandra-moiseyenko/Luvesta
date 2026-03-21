# Feature: conviction-room, Property 34: Auto-promotion on significant score improvement
# Feature: conviction-room, Property 35: Disabled auto-promotion generates recommendation
# Feature: conviction-room, Property 36: Auto-promotion rollback on regression
"""
Property tests for Experiment Automation.

Property 34 — When an experiment's winning plugin exceeds the significance
              threshold AND the dimension is fully_automatable AND the policy
              has auto_promote=True, calling auto_promote activates the winning
              plugin in the registry.
Property 35 — When the policy has auto_promote=False, auto_promote returns
              False and a recommendation event is recorded in the dimension's
              history.
Property 36 — After auto_promote succeeds, calling rollback with the previous
              plugin_id reverts the active plugin and records a rollback event
              in history.

**Validates: Requirements 11.3, 11.4, 11.6**
"""

from __future__ import annotations

from uuid import uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.contracts.base import (
    ContractConstraints,
    Endpoint,
    PluginContractBase,
)
from conviction_room.models.cost import CostBudget
from conviction_room.models.plugin import PluginMetadata
from conviction_room.models.automation import ExperimentPolicy
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.experiment_automation import ExperimentAutomationService
from conviction_room.services.golden_dataset import GoldenDatasetService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.testability import TestabilityService
from tests.conftest import safe_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_services() -> tuple[
    ExperimentAutomationService,
    PluginRegistryService,
    TestabilityService,
    BenchmarkOrchestratorService,
    CostGovernorService,
]:
    """Create fresh services wired together for experiment automation tests."""
    registry = PluginRegistryService()
    cost_gov = CostGovernorService()
    golden_svc = GoldenDatasetService()
    benchmark_svc = BenchmarkOrchestratorService(cost_gov, golden_svc)
    testability = TestabilityService()

    automation = ExperimentAutomationService(
        benchmark_orchestrator=benchmark_svc,
        registry=registry,
        testability=testability,
    )

    # Set a generous global budget so tests don't fail on budget.
    cost_gov.set_budget(CostBudget(
        scope="global_period",
        dimension=None,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=1e6,
    ))

    return automation, registry, testability, benchmark_svc, cost_gov


def _make_contract(dimension: str, version: str = "1.0.0") -> PluginContractBase:
    """Create a minimal valid contract for the given dimension."""
    return PluginContractBase(
        version=version,
        dimension=dimension,
        endpoints=[
            Endpoint(name="run", method="POST", path="/run"),
        ],
        constraints=ContractConstraints(
            max_response_time_ms=5000,
            max_payload_bytes=1_000_000,
        ),
    )


def _make_plugin(dimension: str, name: str = "plugin", version: str = "1.0.0") -> PluginMetadata:
    """Create a PluginMetadata matching the contract from _make_contract."""
    return PluginMetadata(
        dimension=dimension,
        name=f"{name}-{dimension}",
        version="0.1.0",
        contract_version=version,
        status="inactive",
        endpoint_base_url="http://localhost:8000",
    )


def _valid_endpoints() -> list[dict]:
    """Endpoints that satisfy the contract from _make_contract."""
    return [
        {"name": "run", "method": "POST"},
        {"name": "health", "method": "GET"},
    ]


# ---------------------------------------------------------------------------
# Property 34: Auto-promotion on significant score improvement
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    significance_threshold=st.floats(
        min_value=0.01, max_value=0.5, allow_nan=False,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_auto_promotion_on_significant_score_improvement(
    dimension: str,
    significance_threshold: float,
) -> None:
    """When an experiment's winning plugin exceeds the significance threshold
    AND the dimension is fully_automatable AND the policy has auto_promote=True,
    calling auto_promote activates the winning plugin in the registry.

    # Feature: conviction-room, Property 34: Auto-promotion on significant score improvement
    **Validates: Requirements 11.3**
    """
    automation, registry, testability, _, _ = _make_services()

    contract = _make_contract(dimension)

    # Register two plugins for the dimension.
    plugin_a = _make_plugin(dimension, name="plugin-a")
    plugin_b = _make_plugin(dimension, name="plugin-b")

    reg_a = registry.register(plugin_a, contract, _valid_endpoints())
    reg_b = registry.register(plugin_b, contract, _valid_endpoints())
    assert isinstance(reg_a, PluginMetadata)
    assert isinstance(reg_b, PluginMetadata)

    # Activate plugin_a as the current active plugin.
    registry.activate(reg_a.plugin_id)

    # Classify the dimension as fully_automatable.
    testability.classify_dimension(
        dimension=dimension,
        tier="fully_automatable",
        automatable_metrics=["quality", "latency"],
        human_review_metrics=[],
    )
    assert testability.can_auto_promote(dimension) is True

    # Create a policy with auto_promote=True.
    policy = ExperimentPolicy(
        dimension=dimension,
        plugin_ids=[reg_a.plugin_id, reg_b.plugin_id],
        suite_id=uuid4(),
        schedule="0 0 * * *",
        auto_promote=True,
        significance_threshold=significance_threshold,
        enabled=True,
    )
    automation.create_policy(policy)

    # Call auto_promote with plugin_b as the winning plugin.
    result = automation.auto_promote(dimension, reg_b.plugin_id)

    # auto_promote should succeed.
    assert result is True

    # The active plugin for the dimension should now be plugin_b.
    active = registry.get_active(dimension)
    assert isinstance(active, PluginMetadata)
    assert active.plugin_id == reg_b.plugin_id
    assert active.status == "active"


# ---------------------------------------------------------------------------
# Property 35: Disabled auto-promotion generates recommendation
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_disabled_auto_promotion_generates_recommendation(
    dimension: str,
) -> None:
    """When the policy has auto_promote=False, auto_promote returns False and
    a recommendation event is recorded in the dimension's history.

    # Feature: conviction-room, Property 35: Disabled auto-promotion generates recommendation
    **Validates: Requirements 11.4**
    """
    automation, registry, testability, _, _ = _make_services()

    contract = _make_contract(dimension)

    # Register two plugins.
    plugin_a = _make_plugin(dimension, name="plugin-a")
    plugin_b = _make_plugin(dimension, name="plugin-b")

    reg_a = registry.register(plugin_a, contract, _valid_endpoints())
    reg_b = registry.register(plugin_b, contract, _valid_endpoints())
    assert isinstance(reg_a, PluginMetadata)
    assert isinstance(reg_b, PluginMetadata)

    # Activate plugin_a.
    registry.activate(reg_a.plugin_id)

    # Classify the dimension as fully_automatable.
    testability.classify_dimension(
        dimension=dimension,
        tier="fully_automatable",
        automatable_metrics=["quality"],
        human_review_metrics=[],
    )

    # Create a policy with auto_promote=False.
    policy = ExperimentPolicy(
        dimension=dimension,
        plugin_ids=[reg_a.plugin_id, reg_b.plugin_id],
        suite_id=uuid4(),
        schedule="0 0 * * *",
        auto_promote=False,
        significance_threshold=0.05,
        enabled=True,
    )
    automation.create_policy(policy)

    # History should be empty before the call.
    history_before = automation.get_history(dimension)

    # Call auto_promote — should return False because policy disables it.
    result = automation.auto_promote(dimension, reg_b.plugin_id)
    assert result is False

    # The active plugin should still be plugin_a (unchanged).
    active = registry.get_active(dimension)
    assert isinstance(active, PluginMetadata)
    assert active.plugin_id == reg_a.plugin_id

    # A recommendation event should be recorded in history.
    history_after = automation.get_history(dimension)
    assert len(history_after) > len(history_before)

    recommendation_events = [
        e for e in history_after if e.get("event") == "recommendation"
    ]
    assert len(recommendation_events) >= 1

    latest_rec = recommendation_events[-1]
    assert latest_rec["dimension"] == dimension
    assert str(reg_b.plugin_id) in latest_rec.get("recommended_plugin_id", "")


# ---------------------------------------------------------------------------
# Property 36: Auto-promotion rollback on regression
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_auto_promotion_rollback_on_regression(
    dimension: str,
) -> None:
    """After auto_promote succeeds, calling rollback with the previous
    plugin_id reverts the active plugin and records a rollback event in
    history.

    # Feature: conviction-room, Property 36: Auto-promotion rollback on regression
    **Validates: Requirements 11.6**
    """
    automation, registry, testability, _, _ = _make_services()

    contract = _make_contract(dimension)

    # Register two plugins.
    plugin_a = _make_plugin(dimension, name="plugin-a")
    plugin_b = _make_plugin(dimension, name="plugin-b")

    reg_a = registry.register(plugin_a, contract, _valid_endpoints())
    reg_b = registry.register(plugin_b, contract, _valid_endpoints())
    assert isinstance(reg_a, PluginMetadata)
    assert isinstance(reg_b, PluginMetadata)

    # Activate plugin_a as the initial active plugin.
    registry.activate(reg_a.plugin_id)

    # Classify the dimension as fully_automatable.
    testability.classify_dimension(
        dimension=dimension,
        tier="fully_automatable",
        automatable_metrics=["quality"],
        human_review_metrics=[],
    )

    # Create a policy with auto_promote=True.
    policy = ExperimentPolicy(
        dimension=dimension,
        plugin_ids=[reg_a.plugin_id, reg_b.plugin_id],
        suite_id=uuid4(),
        schedule="0 0 * * *",
        auto_promote=True,
        significance_threshold=0.05,
        enabled=True,
    )
    automation.create_policy(policy)

    # Auto-promote plugin_b.
    promote_result = automation.auto_promote(dimension, reg_b.plugin_id)
    assert promote_result is True

    # Verify plugin_b is now active.
    active_after_promote = registry.get_active(dimension)
    assert isinstance(active_after_promote, PluginMetadata)
    assert active_after_promote.plugin_id == reg_b.plugin_id

    # Now rollback to plugin_a (simulating regression failure).
    rollback_result = automation.rollback(dimension, reg_a.plugin_id)
    assert rollback_result is True

    # The active plugin should be reverted to plugin_a.
    active_after_rollback = registry.get_active(dimension)
    assert isinstance(active_after_rollback, PluginMetadata)
    assert active_after_rollback.plugin_id == reg_a.plugin_id

    # A rollback event should be recorded in history.
    history = automation.get_history(dimension)
    rollback_events = [e for e in history if e.get("event") == "rollback"]
    assert len(rollback_events) >= 1

    latest_rollback = rollback_events[-1]
    assert latest_rollback["dimension"] == dimension
    assert latest_rollback["reverted_to_plugin_id"] == reg_a.plugin_id
