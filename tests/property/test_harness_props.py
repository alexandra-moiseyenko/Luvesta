# Feature: conviction-room, Property 31: Contract validation triggers benchmark queue
# Feature: conviction-room, Property 32: Test reports contain all required fields
# Feature: conviction-room, Property 33: Regression degradation blocks auto-promotion
"""
Property tests for Test Harness automation.

Property 31 — After validate_contract passes (no violations), the harness's
              _benchmark_queue has an entry for that plugin/dimension. After
              validate_contract fails, the queue is unchanged.
Property 32 — Every TestReport returned by validate_contract, run_benchmark,
              or run_regression has non-None report_id, test_mode, plugin_id,
              dimension, and passed fields. Reports are retrievable via
              get_report.
Property 33 — When run_regression detects degradation exceeding threshold,
              the testability service's classification for that dimension is
              changed to block auto-promotion (can_auto_promote returns False).

**Validates: Requirements 9.2, 9.3, 9.4, 9.5**
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
from conviction_room.models.benchmark import EvaluationMetric
from conviction_room.models.cost import CostBudget, CostRecord
from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.models.plugin import PluginMetadata
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.golden_dataset import GoldenDatasetService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.test_harness import TestHarnessService
from conviction_room.services.testability import TestabilityService
from tests.conftest import safe_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_services(
    budget_ceiling: float = 1e6,
) -> tuple[
    TestHarnessService,
    PluginRegistryService,
    CostGovernorService,
    BenchmarkOrchestratorService,
    TestabilityService,
]:
    """Create fresh services wired together for test harness tests."""
    registry = PluginRegistryService()
    cost_gov = CostGovernorService()
    golden_svc = GoldenDatasetService()
    benchmark_svc = BenchmarkOrchestratorService(cost_gov, golden_svc)
    testability = TestabilityService()

    harness = TestHarnessService(
        registry=registry,
        cost_governor=cost_gov,
        benchmark_orchestrator=benchmark_svc,
        testability=testability,
    )

    # Set a generous global budget so tests don't fail on budget.
    cost_gov.set_budget(CostBudget(
        scope="global_period",
        dimension=None,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=budget_ceiling,
    ))

    return harness, registry, cost_gov, benchmark_svc, testability


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


def _make_plugin(dimension: str, version: str = "1.0.0") -> PluginMetadata:
    """Create a PluginMetadata matching the contract from _make_contract."""
    return PluginMetadata(
        dimension=dimension,
        name=f"test-plugin-{dimension}",
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


def _invalid_endpoints() -> list[dict]:
    """Endpoints that are missing the required 'run' endpoint."""
    return [
        {"name": "health", "method": "GET"},
    ]


# ---------------------------------------------------------------------------
# Property 31: Contract validation triggers benchmark queue
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_contract_validation_triggers_benchmark_queue(
    dimension: str,
) -> None:
    """After validate_contract passes (no violations), the harness's
    _benchmark_queue has an entry for that plugin/dimension. After
    validate_contract fails, the queue is unchanged.

    # Feature: conviction-room, Property 31: Contract validation triggers benchmark queue
    **Validates: Requirements 9.2, 9.3**
    """
    harness, registry, _, _, _ = _make_services()

    contract = _make_contract(dimension)
    plugin = _make_plugin(dimension)

    # Register the plugin in the registry so validate_contract can find it.
    registered = registry.register(plugin, contract, _valid_endpoints())
    assert isinstance(registered, PluginMetadata)
    plugin_id = registered.plugin_id

    queue_before = len(harness._benchmark_queue)

    # --- Passing validation: should add to queue ---
    report_pass = harness.validate_contract(
        plugin_id=plugin_id,
        dimension=dimension,
        contract=contract,
        plugin_endpoints=_valid_endpoints(),
    )
    assert report_pass.passed is True
    assert len(harness._benchmark_queue) == queue_before + 1
    queued_entry = harness._benchmark_queue[-1]
    assert queued_entry["plugin_id"] == plugin_id
    assert queued_entry["dimension"] == dimension

    queue_after_pass = len(harness._benchmark_queue)

    # --- Failing validation: queue should be unchanged ---
    report_fail = harness.validate_contract(
        plugin_id=plugin_id,
        dimension=dimension,
        contract=contract,
        plugin_endpoints=_invalid_endpoints(),
    )
    assert report_fail.passed is False
    assert len(harness._benchmark_queue) == queue_after_pass


# ---------------------------------------------------------------------------
# Property 32: Test reports contain all required fields
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    prior_val=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
    current_val=st.floats(min_value=0.5, max_value=1.0, allow_nan=False),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_reports_contain_all_required_fields(
    dimension: str,
    prior_val: float,
    current_val: float,
) -> None:
    """Every TestReport returned by validate_contract, run_benchmark, or
    run_regression has non-None report_id, test_mode, plugin_id, dimension,
    and passed fields. Reports are retrievable via get_report.

    # Feature: conviction-room, Property 32: Test reports contain all required fields
    **Validates: Requirements 9.4**
    """
    harness, registry, _, _, _ = _make_services()

    contract = _make_contract(dimension)
    plugin = _make_plugin(dimension)
    registered = registry.register(plugin, contract, _valid_endpoints())
    assert isinstance(registered, PluginMetadata)
    plugin_id = registered.plugin_id

    reports = []

    # 1. Contract validation report
    report_cv = harness.validate_contract(
        plugin_id=plugin_id,
        dimension=dimension,
        contract=contract,
        plugin_endpoints=_valid_endpoints(),
    )
    reports.append(report_cv)

    # 2. Benchmark report
    suite_id = uuid4()
    report_bm = harness.run_benchmark(
        plugin_id=plugin_id,
        dimension=dimension,
        suite_id=suite_id,
    )
    reports.append(report_bm)

    # 3. Regression report
    prior_scores = [
        EvaluationMetric(
            name="quality", category="quality", value=prior_val,
            unit="score", is_deterministic=True,
        ),
    ]
    current_scores = [
        EvaluationMetric(
            name="quality", category="quality", value=current_val,
            unit="score", is_deterministic=True,
        ),
    ]
    report_reg = harness.run_regression(
        plugin_id=plugin_id,
        dimension=dimension,
        prior_scores=prior_scores,
        current_scores=current_scores,
    )
    reports.append(report_reg)

    # Verify all reports have required fields and are retrievable.
    for report in reports:
        assert report.report_id is not None
        assert report.test_mode is not None
        assert report.plugin_id is not None
        assert report.dimension is not None
        assert report.passed is not None

        # Retrievable via get_report.
        retrieved = harness.get_report(report.report_id)
        assert retrieved is not None
        assert retrieved.report_id == report.report_id


# ---------------------------------------------------------------------------
# Property 33: Regression degradation blocks auto-promotion
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    prior_val=st.floats(min_value=0.6, max_value=1.0, allow_nan=False),
    degradation_frac=st.floats(min_value=0.15, max_value=0.5, allow_nan=False),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_regression_degradation_blocks_auto_promotion(
    dimension: str,
    prior_val: float,
    degradation_frac: float,
) -> None:
    """When run_regression detects degradation exceeding threshold, the
    testability service's classification for that dimension is changed to
    block auto-promotion (can_auto_promote returns False).

    # Feature: conviction-room, Property 33: Regression degradation blocks auto-promotion
    **Validates: Requirements 9.5**
    """
    harness, registry, _, _, testability = _make_services()

    plugin_id = uuid4()

    # Classify the dimension as fully_automatable first.
    testability.classify_dimension(
        dimension=dimension,
        tier="fully_automatable",
        automatable_metrics=["quality"],
        human_review_metrics=[],
    )
    assert testability.can_auto_promote(dimension) is True

    # Create scores where current is degraded beyond the 0.1 threshold.
    current_val = prior_val * (1.0 - degradation_frac)

    prior_scores = [
        EvaluationMetric(
            name="quality", category="quality", value=prior_val,
            unit="score", is_deterministic=True,
        ),
    ]
    current_scores = [
        EvaluationMetric(
            name="quality", category="quality", value=current_val,
            unit="score", is_deterministic=True,
        ),
    ]

    report = harness.run_regression(
        plugin_id=plugin_id,
        dimension=dimension,
        prior_scores=prior_scores,
        current_scores=current_scores,
        threshold=0.1,
    )

    # The report should indicate failure (degradation detected).
    assert report.passed is False

    # Auto-promotion should now be blocked.
    assert testability.can_auto_promote(dimension) is False
