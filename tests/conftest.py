"""Shared fixtures and Hypothesis strategies for Conviction Room tests."""

from __future__ import annotations

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

safe_text = st.text(
    min_size=1, max_size=50,
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
)
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
# 1. plugin_metadata() — valid PluginMetadata with random dimensions/versions/statuses
# ---------------------------------------------------------------------------

@st.composite
def plugin_metadata(draw: st.DrawFn) -> PluginMetadata:
    """Generate a valid PluginMetadata instance."""
    return draw(st.builds(
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
    ))


# ---------------------------------------------------------------------------
# 2. plugin_contract() — valid contract definitions (dict-based, since
#    PluginContractBase hasn't been implemented yet)
# ---------------------------------------------------------------------------

@st.composite
def plugin_contract(draw: st.DrawFn) -> dict:
    """Generate a dict representing a plugin contract definition.

    Uses a dict strategy because PluginContractBase is not yet implemented.
    The shape mirrors the planned contract schema from the design doc.
    """
    dimension = draw(safe_text)
    version = draw(st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True))
    num_endpoints = draw(st.integers(min_value=1, max_value=5))
    endpoints = []
    for _ in range(num_endpoints):
        endpoints.append({
            "name": draw(safe_text),
            "method": draw(st.sampled_from(["GET", "POST", "PUT", "DELETE"])),
            "path": "/" + draw(st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L",)))),
            "request_schema": draw(safe_dicts),
            "response_schema": draw(safe_dicts),
        })
    return {
        "dimension": dimension,
        "version": version,
        "endpoints": endpoints,
        "health_check": "/health",
        "lifecycle_hooks": {
            "init": draw(st.booleans()),
            "warmup": draw(st.booleans()),
            "shutdown": draw(st.booleans()),
        },
        "constraints": {
            "max_response_time_ms": draw(st.integers(min_value=100, max_value=30_000)),
            "max_payload_bytes": draw(st.integers(min_value=1024, max_value=10_485_760)),
        },
    }


# ---------------------------------------------------------------------------
# 3. dimension_graph() — random valid DAGs (no cycles) over dimension sets
# ---------------------------------------------------------------------------

@st.composite
def dimension_graph(draw: st.DrawFn) -> DimensionGraph:
    """Generate a random valid DAG over a set of dimension names.

    Strategy: generate a list of unique dimension names, impose a random
    ordering, then only allow edges from earlier to later in that ordering
    — guaranteeing acyclicity.
    """
    num_nodes = draw(st.integers(min_value=1, max_value=8))
    names = draw(
        st.lists(
            st.text(min_size=1, max_size=15, alphabet=st.characters(categories=("L",))),
            min_size=num_nodes,
            max_size=num_nodes,
            unique=True,
        )
    )
    # Build edges: node i can only depend on nodes j where j < i
    nodes: list[DimensionNode] = []
    for i, name in enumerate(names):
        if i == 0:
            depends_on: list[str] = []
        else:
            depends_on = draw(
                st.lists(
                    st.sampled_from(names[:i]),
                    max_size=min(i, 3),
                    unique=True,
                )
            )
        # Classify tier based on position in the ordering
        if len(depends_on) == 0:
            tier = "foundation"
        elif all(
            any(n.dimension == dep and n.tier == "foundation" for n in nodes)
            for dep in depends_on
        ):
            tier = "mid-tier"
        else:
            tier = "leaf"
        nodes.append(DimensionNode(dimension=name, tier=tier, depends_on=depends_on))
    return DimensionGraph(nodes=nodes)


# ---------------------------------------------------------------------------
# 4. golden_dataset_entry() — entries with random payloads, including edge cases
# ---------------------------------------------------------------------------

@st.composite
def golden_dataset_entry(draw: st.DrawFn) -> GoldenDatasetEntry:
    """Generate a GoldenDatasetEntry with random payloads.

    Includes edge-case tags drawn from the required set.
    """
    edge_case_tags = ["empty_input", "max_size", "malformed_input", "known_failure_mode"]
    tags = draw(st.lists(
        st.sampled_from(edge_case_tags) | safe_text,
        max_size=5,
        unique=True,
    ))
    return draw(st.builds(
        GoldenDatasetEntry,
        entry_id=st.uuids(),
        input_payload=safe_dicts,
        expected_output=st.none() | safe_dicts,
        quality_bounds=st.none() | safe_dicts,
        scenario_description=safe_text,
        tags=st.just(tags),
    ))


# ---------------------------------------------------------------------------
# 5. cost_budget() — budgets at various scopes with random ceilings
# ---------------------------------------------------------------------------

@st.composite
def cost_budget(draw: st.DrawFn) -> CostBudget:
    """Generate a CostBudget at a random scope with random ceilings."""
    scope = draw(st.sampled_from(["benchmark_run", "dimension_period", "global_period"]))
    dimension = draw(safe_text) if scope == "dimension_period" else draw(st.none() | safe_text)
    period = draw(st.sampled_from(["daily", "weekly"])) if scope != "benchmark_run" else draw(st.none() | st.sampled_from(["daily", "weekly"]))
    return CostBudget(
        scope=scope,
        dimension=dimension,
        period=period,
        max_tokens=draw(st.integers(min_value=0, max_value=10_000_000)),
        max_api_calls=draw(st.integers(min_value=0, max_value=100_000)),
        max_dollar_cost=draw(pos_floats),
    )


# ---------------------------------------------------------------------------
# 6. evidence_item() — valid EvidenceItems as dicts matching the hackathon spec
#    schema: source, content, metadata, tags
# ---------------------------------------------------------------------------

@st.composite
def evidence_item(draw: st.DrawFn) -> dict:
    """Generate a dict matching the EvidenceItem schema from the hackathon spec.

    Fields: source, content, metadata, tags.
    """
    return {
        "source": draw(safe_text),
        "content": draw(st.text(min_size=0, max_size=200, alphabet=st.characters(categories=("L", "N", "P", "Z")))),
        "metadata": draw(safe_dicts),
        "tags": draw(st.lists(safe_text, max_size=5)),
    }


# ---------------------------------------------------------------------------
# 7. trace_event() — trace events with random metrics
# ---------------------------------------------------------------------------

@st.composite
def trace_event(draw: st.DrawFn) -> TraceEvent:
    """Generate a valid TraceEvent with random metrics."""
    return draw(st.builds(
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
    ))


# ---------------------------------------------------------------------------
# 8. experiment() — experiment definitions with random plugin sets and configs
# ---------------------------------------------------------------------------

@st.composite
def experiment(draw: st.DrawFn) -> Experiment:
    """Generate a valid Experiment definition with random plugin sets."""
    budget = draw(cost_budget())
    return draw(st.builds(
        Experiment,
        experiment_id=st.uuids(),
        dimension=safe_text,
        plugin_ids=st.lists(st.uuids(), min_size=1, max_size=5),
        suite_id=st.uuids(),
        comparison_mode=st.sampled_from(["head_to_head", "tournament", "regression"]),
        iteration_count=st.integers(min_value=1, max_value=1000),
        cost_budget=st.just(budget),
        status=st.sampled_from(["pending", "running", "completed", "failed", "budget_exceeded"]),
        runs=st.lists(st.uuids(), max_size=5),
        results=st.none(),
        created_at=st.datetimes(),
        completed_at=st.none() | st.datetimes(),
    ))


# ---------------------------------------------------------------------------
# Additional model strategies (used by test_roundtrip and other property tests)
# ---------------------------------------------------------------------------

plugin_metadata_st = plugin_metadata()

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

dimension_graph_st = dimension_graph()

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

cost_budget_st = cost_budget()

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

experiment_st = experiment()

golden_dataset_entry_st = golden_dataset_entry()

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

trace_event_st = trace_event()

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
# Combined strategy for all domain objects
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
