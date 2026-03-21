# Feature: conviction-room, Property 1: Domain object JSON round-trip
"""
Property test: for any valid domain object, serializing to JSON via
.model_dump_json() and deserializing via .model_validate_json() produces
an equivalent object.

**Validates: Requirements 1.7, 5.4, 8.7, 9.8**
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.models.automation import ExperimentPolicy
from conviction_room.models.benchmark import (
    BenchmarkRun,
    BenchmarkSuite,
    EvaluationMetric,
    Experiment,
    ExperimentResults,
    PluginScore,
)
from conviction_room.models.cost import CostBudget, CostRecord, CostSummary
from conviction_room.models.golden import GoldenDataset, GoldenDatasetEntry
from conviction_room.models.graph import DimensionGraph, DimensionNode
from conviction_room.models.plugin import PluginError, PluginMetadata
from conviction_room.models.test_report import RegressionResult, TestReport
from conviction_room.models.testability import TestabilityClassification
from conviction_room.models.trace import AggregateMetrics, TraceEvent

# ---------------------------------------------------------------------------
# Reusable atomic strategies
# ---------------------------------------------------------------------------

safe_text = st.text(min_size=1, max_size=50, alphabet=st.characters(categories=("L", "N", "P", "Z")))
safe_floats = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e12, max_value=1e12)
pos_floats = st.floats(allow_nan=False, allow_infinity=False, min_value=0.0, max_value=1e12)
safe_ints = st.integers(min_value=0, max_value=10_000)
safe_dicts = st.dictionaries(
    st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
    st.text(min_size=0, max_size=20),
    max_size=5,
)
safe_str_float_dicts = st.dictionaries(
    st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
    pos_floats,
    max_size=5,
)

# ---------------------------------------------------------------------------
# Model strategies
# ---------------------------------------------------------------------------

plugin_metadata_st = st.builds(
    PluginMetadata,
    plugin_id=st.uuids(),
    dimension=safe_text,
    name=safe_text,
    version=safe_text,
    contract_version=safe_text,
    status=st.sampled_from(["active", "inactive", "deprecated"]),
    endpoint_base_url=safe_text,
    config=safe_dicts,
    health_status=st.sampled_from(["healthy", "degraded", "unhealthy", "unknown"]),
    last_health_check=st.none() | st.datetimes(),
    latest_benchmark_score=st.none() | safe_floats,
    registered_at=st.datetimes(),
    validated_at=st.none() | st.datetimes(),
    contract_violations=st.lists(safe_text, max_size=5),
)

plugin_error_st = st.builds(
    PluginError,
    error_code=safe_text,
    message=safe_text,
    dimension=st.none() | safe_text,
    plugin_id=st.none() | st.uuids(),
    details=st.lists(safe_text, max_size=5),
    timestamp=st.datetimes(),
    trace_id=st.none() | st.uuids(),
)

dimension_node_st = st.builds(
    DimensionNode,
    dimension=safe_text,
    tier=st.sampled_from(["foundation", "mid-tier", "leaf"]),
    depends_on=st.lists(safe_text, max_size=5),
)

dimension_graph_st = st.builds(
    DimensionGraph,
    nodes=st.lists(dimension_node_st, max_size=5),
)

evaluation_metric_st = st.builds(
    EvaluationMetric,
    name=safe_text,
    category=st.sampled_from(["quality", "performance", "cost"]),
    value=safe_floats,
    unit=safe_text,
    is_deterministic=st.booleans(),
)

benchmark_suite_st = st.builds(
    BenchmarkSuite,
    suite_id=st.uuids(),
    dimension=safe_text,
    name=safe_text,
    description=safe_text,
    golden_dataset_id=st.uuids(),
    metrics=st.lists(safe_text, max_size=5),
    iteration_count=st.integers(min_value=1, max_value=1000),
)

cost_budget_st = st.builds(
    CostBudget,
    scope=st.sampled_from(["benchmark_run", "dimension_period", "global_period"]),
    dimension=st.none() | safe_text,
    period=st.none() | st.sampled_from(["daily", "weekly"]),
    max_tokens=st.integers(min_value=0, max_value=10_000_000),
    max_api_calls=st.integers(min_value=0, max_value=100_000),
    max_dollar_cost=pos_floats,
)

cost_record_st = st.builds(
    CostRecord,
    record_id=st.uuids(),
    timestamp=st.datetimes(),
    dimension=safe_text,
    plugin_id=st.uuids(),
    token_count=safe_ints,
    api_calls=safe_ints,
    dollar_cost=pos_floats,
    is_estimated=st.booleans(),
)

cost_summary_st = st.builds(
    CostSummary,
    scope=safe_text,
    current_spend=pos_floats,
    remaining_budget=pos_floats,
    projected_spend=pos_floats,
    breakdown_by_dimension=safe_str_float_dicts,
    breakdown_by_plugin=safe_str_float_dicts,
)

benchmark_run_st = st.builds(
    BenchmarkRun,
    run_id=st.uuids(),
    suite_id=st.uuids(),
    plugin_id=st.uuids(),
    dimension=safe_text,
    status=st.sampled_from(["pending", "running", "completed", "failed", "budget_exceeded"]),
    iterations_completed=safe_ints,
    scores=st.lists(evaluation_metric_st, max_size=3),
    raw_inputs=st.just([]),
    raw_outputs=st.just([]),
    cost_consumed=cost_record_st,
    started_at=st.datetimes(),
    completed_at=st.none() | st.datetimes(),
    metadata=safe_dicts,
)

plugin_score_st = st.builds(
    PluginScore,
    plugin_id=st.uuids(),
    composite_score=safe_floats,
    per_metric_scores=st.lists(evaluation_metric_st, max_size=3),
    rank=st.integers(min_value=1, max_value=100),
)

experiment_results_st = st.builds(
    ExperimentResults,
    ranked_plugins=st.lists(plugin_score_st, max_size=2),
    comparison_report=safe_dicts,
    confidence_intervals=st.none(),
)

experiment_st = st.builds(
    Experiment,
    experiment_id=st.uuids(),
    dimension=safe_text,
    plugin_ids=st.lists(st.uuids(), min_size=1, max_size=3),
    suite_id=st.uuids(),
    comparison_mode=st.sampled_from(["head_to_head", "tournament", "regression"]),
    iteration_count=st.integers(min_value=1, max_value=1000),
    cost_budget=cost_budget_st,
    status=st.sampled_from(["pending", "running", "completed", "failed", "budget_exceeded"]),
    runs=st.lists(st.uuids(), max_size=3),
    results=st.none() | experiment_results_st,
    created_at=st.datetimes(),
    completed_at=st.none() | st.datetimes(),
)

golden_dataset_entry_st = st.builds(
    GoldenDatasetEntry,
    entry_id=st.uuids(),
    input_payload=safe_dicts,
    expected_output=st.none() | safe_dicts,
    quality_bounds=st.none() | safe_dicts,
    scenario_description=safe_text,
    tags=st.lists(safe_text, max_size=5),
)

golden_dataset_st = st.builds(
    GoldenDataset,
    dataset_id=st.uuids(),
    dimension=safe_text,
    version=st.integers(min_value=1, max_value=1000),
    entries=st.lists(golden_dataset_entry_st, max_size=3),
    created_at=st.datetimes(),
    prior_version_id=st.none() | st.uuids(),
)

test_report_st = st.builds(
    TestReport,
    report_id=st.uuids(),
    test_mode=st.sampled_from(["contract_validation", "benchmark", "regression"]),
    plugin_id=st.uuids(),
    dimension=safe_text,
    passed=st.booleans(),
    per_metric_scores=st.none() | st.lists(evaluation_metric_st, max_size=3),
    violations=st.lists(safe_text, max_size=5),
    failure_details=st.lists(safe_text, max_size=5),
    created_at=st.datetimes(),
)

regression_result_st = st.builds(
    RegressionResult,
    metric_name=safe_text,
    prior_score=safe_floats,
    current_score=safe_floats,
    delta=safe_floats,
    exceeds_threshold=st.booleans(),
)

trace_event_st = st.builds(
    TraceEvent,
    trace_id=st.uuids(),
    timestamp=st.datetimes(),
    dimension=safe_text,
    plugin_id=st.uuids(),
    input_hash=safe_text,
    output_hash=safe_text,
    latency_ms=pos_floats,
    token_usage=safe_ints,
    cost_usd=pos_floats,
    success=st.booleans(),
    error_context=st.none() | safe_dicts,
    experiment_id=st.none() | st.uuids(),
    benchmark_run_id=st.none() | st.uuids(),
)

aggregate_metrics_st = st.builds(
    AggregateMetrics,
    plugin_id=st.uuids(),
    dimension=safe_text,
    time_window=safe_text,
    success_rate=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    mean_latency_ms=pos_floats,
    p95_latency_ms=pos_floats,
    mean_cost_usd=pos_floats,
    total_invocations=safe_ints,
)

testability_classification_st = st.builds(
    TestabilityClassification,
    dimension=safe_text,
    tier=st.sampled_from(["fully_automatable", "semi_automatable", "human_required"]),
    automatable_metrics=st.lists(safe_text, max_size=5),
    human_review_metrics=st.lists(safe_text, max_size=5),
)

experiment_policy_st = st.builds(
    ExperimentPolicy,
    policy_id=st.uuids(),
    dimension=safe_text,
    plugin_ids=st.lists(st.uuids(), min_size=1, max_size=5),
    suite_id=st.uuids(),
    schedule=safe_text,
    auto_promote=st.booleans(),
    significance_threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    enabled=st.booleans(),
)


# ---------------------------------------------------------------------------
# Combined strategy using st.one_of for all domain objects
# ---------------------------------------------------------------------------

all_domain_objects_st = st.one_of(
    plugin_metadata_st,
    plugin_error_st,
    dimension_node_st,
    dimension_graph_st,
    evaluation_metric_st,
    benchmark_suite_st,
    benchmark_run_st,
    experiment_st,
    experiment_results_st,
    plugin_score_st,
    cost_budget_st,
    cost_record_st,
    cost_summary_st,
    golden_dataset_entry_st,
    golden_dataset_st,
    test_report_st,
    regression_result_st,
    trace_event_st,
    aggregate_metrics_st,
    testability_classification_st,
    experiment_policy_st,
)


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(obj=all_domain_objects_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_domain_object_json_roundtrip(obj: Any) -> None:
    """For any valid domain object, serializing to JSON and deserializing back
    produces an equivalent object.

    # Feature: conviction-room, Property 1: Domain object JSON round-trip
    **Validates: Requirements 1.7, 5.4, 8.7, 9.8**
    """
    json_str = obj.model_dump_json()
    restored = type(obj).model_validate_json(json_str)
    assert restored == obj, (
        f"Round-trip failed for {type(obj).__name__}: {obj!r} != {restored!r}"
    )
