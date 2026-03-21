# Feature: conviction-room, Property 12: Experiment uses identical inputs across plugins
# Feature: conviction-room, Property 13: Benchmark suite covers all metric categories
# Feature: conviction-room, Property 14: Experiment results contain complete ranked scores
# Feature: conviction-room, Property 15: Budget-exceeded benchmark terminates with partial results
# Feature: conviction-room, Property 16: Benchmark run results are fully persisted
# Feature: conviction-room, Property 17: Deterministic metrics are reproducible
"""
Property tests for Benchmark Orchestrator invariants.

Property 12 — When an experiment runs multiple plugins, each plugin's
              BenchmarkRun must receive the same raw_inputs list.
Property 13 — Every BenchmarkRun's scores list must contain at least one
              metric from each category: quality, performance, cost.
Property 14 — After run_experiment completes, results.ranked_plugins must
              have one PluginScore per plugin that was actually run, ranks
              are 1..N with no gaps, and composite_score equals sum of
              per_metric_scores values.
Property 15 — When cost governor rejects a plugin mid-experiment, the
              experiment status is "budget_exceeded", partial results are
              saved, and the number of completed runs is less than total
              plugin count.
Property 16 — After run_benchmark, the run is retrievable via get_run and
              contains non-empty scores, raw_inputs, raw_outputs, and
              cost_consumed.
Property 17 — Running the same plugin with the same inputs and deterministic
              metrics produces identical scores across two runs.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 11.2**
"""

from __future__ import annotations

from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st

from conviction_room.models.benchmark import (
    BenchmarkRun,
    Experiment,
    ExperimentResults,
)
from conviction_room.models.cost import CostBudget, CostRecord
from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.golden_dataset import GoldenDatasetService
from tests.conftest import safe_text, safe_dicts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_services(
    budget_ceiling: float = 1e6,
    golden_entries: list[GoldenDatasetEntry] | None = None,
    suite_id: UUID | None = None,
    dimension: str = "test_dim",
) -> tuple[BenchmarkOrchestratorService, CostGovernorService, GoldenDatasetService, UUID]:
    """Create fresh services with an optional golden dataset pre-loaded.

    Returns (benchmark_svc, cost_svc, golden_svc, suite_id).
    """
    cost_svc = CostGovernorService()
    golden_svc = GoldenDatasetService()

    sid = suite_id or uuid4()

    if golden_entries is not None and len(golden_entries) > 0:
        ds = GoldenDataset(
            dataset_id=sid,
            dimension=dimension,
            version=1,
            entries=golden_entries,
        )
        golden_svc.create(ds)

    benchmark_svc = BenchmarkOrchestratorService(cost_svc, golden_svc)

    # Set a generous budget so tests don't fail on budget by default.
    cost_svc.set_budget(CostBudget(
        scope="global_period",
        dimension=None,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=budget_ceiling,
    ))

    return benchmark_svc, cost_svc, golden_svc, sid


def _make_experiment(
    plugin_ids: list[UUID],
    suite_id: UUID,
    dimension: str = "test_dim",
    budget_ceiling: float = 1e6,
) -> Experiment:
    """Build an Experiment model ready for create + run."""
    return Experiment(
        experiment_id=uuid4(),
        dimension=dimension,
        plugin_ids=plugin_ids,
        suite_id=suite_id,
        comparison_mode="head_to_head",
        iteration_count=1,
        cost_budget=CostBudget(
            scope="benchmark_run",
            dimension=dimension,
            period=None,
            max_tokens=10_000_000,
            max_api_calls=100_000,
            max_dollar_cost=budget_ceiling,
        ),
        status="pending",
    )


# ---------------------------------------------------------------------------
# Property 12: Experiment uses identical inputs across plugins
# ---------------------------------------------------------------------------


@given(
    num_plugins=st.integers(min_value=2, max_value=5),
    num_entries=st.integers(min_value=1, max_value=5),
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_experiment_uses_identical_inputs_across_plugins(
    num_plugins: int,
    num_entries: int,
    dimension: str,
) -> None:
    """When an experiment runs multiple plugins, each plugin's BenchmarkRun
    must receive the same raw_inputs list.

    # Feature: conviction-room, Property 12: Experiment uses identical inputs across plugins
    **Validates: Requirements 4.1, 4.2**
    """
    plugin_ids = [uuid4() for _ in range(num_plugins)]
    entries = [
        GoldenDatasetEntry(
            input_payload={"key": f"value_{i}"},
            scenario_description=f"scenario_{i}",
            tags=["empty_input", "max_size", "malformed_input", "known_failure_mode"],
        )
        for i in range(num_entries)
    ]

    suite_id = uuid4()
    benchmark_svc, _, _, _ = _make_services(
        golden_entries=entries,
        suite_id=suite_id,
        dimension=dimension,
    )

    exp = _make_experiment(plugin_ids, suite_id, dimension)
    benchmark_svc.create_experiment(exp)
    result = benchmark_svc.run_experiment(exp.experiment_id)

    assert result is not None
    assert result.status == "completed"
    assert len(result.runs) == num_plugins, (
        f"Expected {num_plugins} runs, got {len(result.runs)}"
    )

    # Collect raw_inputs from each run.
    all_raw_inputs = []
    for run_id in result.runs:
        run = benchmark_svc.get_run(run_id)
        assert run is not None
        all_raw_inputs.append(run.raw_inputs)

    # All plugins must have received the same inputs.
    for i in range(1, len(all_raw_inputs)):
        assert all_raw_inputs[i] == all_raw_inputs[0], (
            f"Plugin {i} received different inputs than plugin 0"
        )


# ---------------------------------------------------------------------------
# Property 13: Benchmark suite covers all metric categories
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    num_entries=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_benchmark_suite_covers_all_metric_categories(
    dimension: str,
    num_entries: int,
) -> None:
    """Every BenchmarkRun's scores list must contain at least one metric from
    each category: quality, performance, cost.

    # Feature: conviction-room, Property 13: Benchmark suite covers all metric categories
    **Validates: Requirements 4.3**
    """
    plugin_id = uuid4()
    entries = [
        GoldenDatasetEntry(
            input_payload={"key": f"v_{i}"},
            scenario_description=f"s_{i}",
            tags=["empty_input", "max_size", "malformed_input", "known_failure_mode"],
        )
        for i in range(num_entries)
    ]

    suite_id = uuid4()
    benchmark_svc, _, _, _ = _make_services(
        golden_entries=entries,
        suite_id=suite_id,
        dimension=dimension,
    )

    exp = _make_experiment([plugin_id], suite_id, dimension)
    benchmark_svc.create_experiment(exp)
    result = benchmark_svc.run_experiment(exp.experiment_id)

    assert result is not None
    for run_id in result.runs:
        run = benchmark_svc.get_run(run_id)
        assert run is not None

        categories_present = {m.category for m in run.scores}
        assert "quality" in categories_present, "Missing quality metric"
        assert "performance" in categories_present, "Missing performance metric"
        assert "cost" in categories_present, "Missing cost metric"


# ---------------------------------------------------------------------------
# Property 14: Experiment results contain complete ranked scores
# ---------------------------------------------------------------------------


@given(
    num_plugins=st.integers(min_value=1, max_value=5),
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_experiment_results_contain_complete_ranked_scores(
    num_plugins: int,
    dimension: str,
) -> None:
    """After run_experiment completes, results.ranked_plugins must have one
    PluginScore per plugin that was actually run, ranks are 1..N with no
    gaps, and composite_score equals sum of per_metric_scores values.

    # Feature: conviction-room, Property 14: Experiment results contain complete ranked scores
    **Validates: Requirements 4.4, 11.2**
    """
    plugin_ids = [uuid4() for _ in range(num_plugins)]
    entries = [
        GoldenDatasetEntry(
            input_payload={"data": "test"},
            scenario_description="basic",
            tags=["empty_input", "max_size", "malformed_input", "known_failure_mode"],
        )
    ]

    suite_id = uuid4()
    benchmark_svc, _, _, _ = _make_services(
        golden_entries=entries,
        suite_id=suite_id,
        dimension=dimension,
    )

    exp = _make_experiment(plugin_ids, suite_id, dimension)
    benchmark_svc.create_experiment(exp)
    result = benchmark_svc.run_experiment(exp.experiment_id)

    assert result is not None
    assert result.status == "completed"
    assert result.results is not None

    ranked = result.results.ranked_plugins

    # One PluginScore per plugin.
    assert len(ranked) == num_plugins, (
        f"Expected {num_plugins} ranked plugins, got {len(ranked)}"
    )

    # Ranks are 1..N with no gaps.
    ranks = sorted(ps.rank for ps in ranked)
    assert ranks == list(range(1, num_plugins + 1)), (
        f"Ranks should be 1..{num_plugins}, got {ranks}"
    )

    # composite_score equals sum of per_metric_scores values.
    for ps in ranked:
        expected_composite = sum(m.value for m in ps.per_metric_scores)
        assert abs(ps.composite_score - expected_composite) < 1e-9, (
            f"composite_score {ps.composite_score} != sum of per_metric_scores "
            f"{expected_composite} for plugin {ps.plugin_id}"
        )

    # Plugin IDs in results match the experiment's plugin_ids.
    result_plugin_ids = {ps.plugin_id for ps in ranked}
    assert result_plugin_ids == set(plugin_ids), (
        f"Result plugin IDs {result_plugin_ids} != experiment plugin IDs {set(plugin_ids)}"
    )


# ---------------------------------------------------------------------------
# Property 15: Budget-exceeded benchmark terminates with partial results
# ---------------------------------------------------------------------------


@given(
    num_plugins=st.integers(min_value=2, max_value=5),
    dimension=safe_text,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_budget_exceeded_terminates_with_partial_results(
    num_plugins: int,
    dimension: str,
) -> None:
    """When cost governor rejects a plugin mid-experiment, the experiment
    status is "budget_exceeded", partial results are saved, and the number
    of completed runs is less than total plugin count.

    # Feature: conviction-room, Property 15: Budget-exceeded benchmark terminates with partial results
    **Validates: Requirements 4.6**
    """
    plugin_ids = [uuid4() for _ in range(num_plugins)]
    entries = [
        GoldenDatasetEntry(
            input_payload={"data": "test"},
            scenario_description="basic",
            tags=["empty_input", "max_size", "malformed_input", "known_failure_mode"],
        )
    ]

    suite_id = uuid4()
    # Set a very low budget: enough for 1 run (0.01 cost) but not all.
    # Each run costs 0.01, so ceiling of 0.015 allows exactly 1 run.
    budget_ceiling = 0.015
    benchmark_svc, cost_svc, _, _ = _make_services(
        budget_ceiling=budget_ceiling,
        golden_entries=entries,
        suite_id=suite_id,
        dimension=dimension,
    )

    exp = _make_experiment(plugin_ids, suite_id, dimension, budget_ceiling=budget_ceiling)
    benchmark_svc.create_experiment(exp)
    result = benchmark_svc.run_experiment(exp.experiment_id)

    assert result is not None
    assert result.status == "budget_exceeded", (
        f"Expected 'budget_exceeded' status, got '{result.status}'"
    )

    # Partial results: fewer runs than total plugins.
    assert len(result.runs) < num_plugins, (
        f"Expected fewer runs ({len(result.runs)}) than plugins ({num_plugins})"
    )

    # Partial results are saved.
    assert result.results is not None, "Partial results must be saved"
    assert len(result.results.ranked_plugins) == len(result.runs), (
        "ranked_plugins count must match completed runs"
    )


# ---------------------------------------------------------------------------
# Property 16: Benchmark run results are fully persisted
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    num_entries=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_benchmark_run_results_fully_persisted(
    dimension: str,
    num_entries: int,
) -> None:
    """After run_benchmark, the run is retrievable via get_run and contains
    non-empty scores, raw_inputs, raw_outputs, and cost_consumed.

    # Feature: conviction-room, Property 16: Benchmark run results are fully persisted
    **Validates: Requirements 4.7**
    """
    plugin_id = uuid4()
    raw_inputs = [{"key": f"input_{i}"} for i in range(num_entries)]

    benchmark_svc, _, _, _ = _make_services(dimension=dimension)

    run = BenchmarkRun(
        run_id=uuid4(),
        suite_id=uuid4(),
        plugin_id=plugin_id,
        dimension=dimension,
        status="pending",
        raw_inputs=raw_inputs,
        cost_consumed=CostRecord(
            dimension=dimension,
            plugin_id=plugin_id,
            token_count=0,
            api_calls=0,
            dollar_cost=0.0,
            is_estimated=True,
        ),
        metadata={
            "metrics": [
                {"name": "quality", "category": "quality", "unit": "score", "is_deterministic": True},
                {"name": "latency", "category": "performance", "unit": "ms", "is_deterministic": True},
                {"name": "cost_eff", "category": "cost", "unit": "usd", "is_deterministic": True},
            ],
            "iteration_count": 1,
        },
    )

    completed = benchmark_svc.run_benchmark(run)

    # Retrievable via get_run.
    retrieved = benchmark_svc.get_run(completed.run_id)
    assert retrieved is not None, "Run must be retrievable via get_run"

    # Non-empty scores.
    assert len(retrieved.scores) > 0, "scores must be non-empty"

    # Non-empty raw_inputs.
    assert len(retrieved.raw_inputs) > 0, "raw_inputs must be non-empty"

    # Non-empty raw_outputs.
    assert len(retrieved.raw_outputs) > 0, "raw_outputs must be non-empty"

    # cost_consumed is present with recorded cost.
    assert retrieved.cost_consumed is not None, "cost_consumed must be present"
    assert retrieved.cost_consumed.dollar_cost >= 0, "cost must be non-negative"


# ---------------------------------------------------------------------------
# Property 17: Deterministic metrics are reproducible
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    num_entries=st.integers(min_value=1, max_value=3),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_deterministic_metrics_are_reproducible(
    dimension: str,
    num_entries: int,
) -> None:
    """Running the same plugin with the same inputs and deterministic metrics
    produces identical scores across two runs.

    # Feature: conviction-room, Property 17: Deterministic metrics are reproducible
    **Validates: Requirements 4.8**
    """
    plugin_id = uuid4()
    raw_inputs = [{"key": f"input_{i}"} for i in range(num_entries)]

    metrics_config = [
        {"name": "accuracy", "category": "quality", "unit": "score", "is_deterministic": True},
        {"name": "latency_p95", "category": "performance", "unit": "ms", "is_deterministic": True},
        {"name": "cost_per_run", "category": "cost", "unit": "usd", "is_deterministic": True},
    ]

    benchmark_svc, _, _, _ = _make_services(dimension=dimension)

    def _make_run() -> BenchmarkRun:
        return BenchmarkRun(
            run_id=uuid4(),  # different run_id each time
            suite_id=uuid4(),
            plugin_id=plugin_id,  # same plugin
            dimension=dimension,
            status="pending",
            raw_inputs=raw_inputs,  # same inputs
            cost_consumed=CostRecord(
                dimension=dimension,
                plugin_id=plugin_id,
                token_count=0,
                api_calls=0,
                dollar_cost=0.0,
                is_estimated=True,
            ),
            metadata={
                "metrics": metrics_config,  # same deterministic metrics
                "iteration_count": 1,
            },
        )

    run1 = benchmark_svc.run_benchmark(_make_run())
    run2 = benchmark_svc.run_benchmark(_make_run())

    # Filter to deterministic metrics only.
    det_scores_1 = {m.name: m.value for m in run1.scores if m.is_deterministic}
    det_scores_2 = {m.name: m.value for m in run2.scores if m.is_deterministic}

    assert det_scores_1 == det_scores_2, (
        f"Deterministic scores differ between runs:\n"
        f"  Run 1: {det_scores_1}\n"
        f"  Run 2: {det_scores_2}"
    )
