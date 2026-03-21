# Feature: conviction-room, Property 37: Trace events emitted for every invocation
# Feature: conviction-room, Property 38: Benchmark traces correlate to parent experiment
# Feature: conviction-room, Property 39: Trace query returns correct filtered results
# Feature: conviction-room, Property 40: Aggregate metrics are consistent with individual traces
"""
Property tests for Observability / Trace Emitter.

Property 37 — For any TraceEvent emitted via emit_trace, it shall be
              retrievable via get_trace and appear in query_traces results.
Property 38 — For any trace with experiment_id set, querying traces and
              filtering should return traces that share the same experiment_id.
Property 39 — For any set of traces and any filter combination (dimension,
              plugin_id, success), query_traces returns exactly the matching
              traces.
Property 40 — For any set of traces for a plugin, the computed
              AggregateMetrics shall have: total_invocations == count of
              traces, success_rate == successes/total, mean_latency == avg
              of latencies, mean_cost == avg of costs.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st

from conviction_room.models.trace import TraceEvent
from conviction_room.services.observability import ObservabilityService
from tests.conftest import trace_event_st, safe_text, pos_floats, safe_ints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> ObservabilityService:
    """Return a new ObservabilityService with no state."""
    return ObservabilityService()


def _make_recent_trace(**overrides) -> TraceEvent:
    """Create a TraceEvent with a recent timestamp (utcnow) so it falls
    within the default 24h aggregation window."""
    defaults = dict(
        trace_id=uuid4(),
        timestamp=datetime.utcnow(),
        dimension="test_dim",
        plugin_id=uuid4(),
        input_hash="inhash",
        output_hash="outhash",
        latency_ms=10.0,
        token_usage=100,
        cost_usd=0.01,
        success=True,
        error_context=None,
        experiment_id=None,
        benchmark_run_id=None,
    )
    defaults.update(overrides)
    return TraceEvent(**defaults)



# ---------------------------------------------------------------------------
# Strategy: trace events with recent timestamps for aggregation tests
# ---------------------------------------------------------------------------

@st.composite
def recent_trace_event(draw: st.DrawFn) -> TraceEvent:
    """Generate a TraceEvent with timestamp set to utcnow() so it falls
    within the default 24h aggregation window."""
    te = draw(trace_event_st)
    return te.model_copy(update={"timestamp": datetime.utcnow()})


# ---------------------------------------------------------------------------
# Property 37: Trace events emitted for every invocation
# ---------------------------------------------------------------------------


@given(trace=trace_event_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_emitted_trace_retrievable_by_id(trace: TraceEvent) -> None:
    """For any TraceEvent emitted via emit_trace, it shall be retrievable
    via get_trace by its trace_id.

    # Feature: conviction-room, Property 37: Trace events emitted for every invocation
    **Validates: Requirements 12.1**
    """
    svc = _fresh_service()
    svc.emit_trace(trace)

    retrieved = svc.get_trace(trace.trace_id)
    assert retrieved is not None, "Emitted trace must be retrievable by ID"
    assert retrieved.trace_id == trace.trace_id
    assert retrieved.dimension == trace.dimension
    assert retrieved.plugin_id == trace.plugin_id


@given(trace=trace_event_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_emitted_trace_appears_in_query(trace: TraceEvent) -> None:
    """For any TraceEvent emitted via emit_trace, it shall appear in
    query_traces results when queried by its dimension.

    # Feature: conviction-room, Property 37: Trace events emitted for every invocation
    **Validates: Requirements 12.1, 12.3**
    """
    svc = _fresh_service()
    svc.emit_trace(trace)

    results = svc.query_traces(dimension=trace.dimension)
    trace_ids = [t.trace_id for t in results]
    assert trace.trace_id in trace_ids, (
        "Emitted trace must appear in query_traces results"
    )


# ---------------------------------------------------------------------------
# Property 38: Benchmark traces correlate to parent experiment
# ---------------------------------------------------------------------------


@given(
    experiment_id=st.uuids(),
    num_traces=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_benchmark_traces_correlate_to_experiment(
    experiment_id: UUID,
    num_traces: int,
) -> None:
    """For any trace with experiment_id set, querying traces and filtering
    should return traces that share the same experiment_id.

    # Feature: conviction-room, Property 38: Benchmark traces correlate to parent experiment
    **Validates: Requirements 12.2**
    """
    svc = _fresh_service()
    dimension = "bench_dim"
    plugin_id = uuid4()

    # Emit traces belonging to the experiment
    for _ in range(num_traces):
        svc.emit_trace(_make_recent_trace(
            dimension=dimension,
            plugin_id=plugin_id,
            experiment_id=experiment_id,
        ))

    # Emit a trace with a different experiment_id
    other_exp_id = uuid4()
    svc.emit_trace(_make_recent_trace(
        dimension=dimension,
        plugin_id=plugin_id,
        experiment_id=other_exp_id,
    ))

    # Emit a trace with no experiment_id
    svc.emit_trace(_make_recent_trace(
        dimension=dimension,
        plugin_id=plugin_id,
        experiment_id=None,
    ))

    # Query all traces for the dimension and filter by experiment_id
    all_traces = svc.query_traces(dimension=dimension)
    matching = [t for t in all_traces if t.experiment_id == experiment_id]

    assert len(matching) == num_traces, (
        f"Expected {num_traces} traces for experiment {experiment_id}, "
        f"got {len(matching)}"
    )
    for t in matching:
        assert t.experiment_id == experiment_id


# ---------------------------------------------------------------------------
# Property 39: Trace query returns correct filtered results
# ---------------------------------------------------------------------------


@st.composite
def _filter_scenario(draw: st.DrawFn):
    """Generate a set of traces and a filter combination, then return
    (service, filters, expected_count)."""
    dimensions = draw(st.lists(safe_text, min_size=2, max_size=3, unique=True))
    plugin_ids = [uuid4() for _ in range(draw(st.integers(min_value=2, max_value=3)))]

    svc = _fresh_service()
    traces: list[TraceEvent] = []

    num_traces = draw(st.integers(min_value=3, max_value=15))
    for _ in range(num_traces):
        dim = draw(st.sampled_from(dimensions))
        pid = draw(st.sampled_from(plugin_ids))
        success = draw(st.booleans())
        t = _make_recent_trace(
            dimension=dim,
            plugin_id=pid,
            success=success,
        )
        svc.emit_trace(t)
        traces.append(t)

    # Pick a random filter combination
    filter_dim = draw(st.none() | st.sampled_from(dimensions))
    filter_pid = draw(st.none() | st.sampled_from(plugin_ids))
    filter_success = draw(st.none() | st.booleans())

    # Compute expected results
    expected = traces[:]
    if filter_dim is not None:
        expected = [t for t in expected if t.dimension == filter_dim]
    if filter_pid is not None:
        expected = [t for t in expected if t.plugin_id == filter_pid]
    if filter_success is not None:
        expected = [t for t in expected if t.success == filter_success]

    return svc, filter_dim, filter_pid, filter_success, expected


@given(scenario=_filter_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_query_traces_returns_correct_filtered_results(scenario) -> None:
    """For any set of traces and any filter combination (dimension, plugin_id,
    success), query_traces returns exactly the matching traces.

    # Feature: conviction-room, Property 39: Trace query returns correct filtered results
    **Validates: Requirements 12.3**
    """
    svc, filter_dim, filter_pid, filter_success, expected = scenario

    results = svc.query_traces(
        dimension=filter_dim,
        plugin_id=filter_pid,
        success=filter_success,
    )

    expected_ids = sorted(str(t.trace_id) for t in expected)
    result_ids = sorted(str(t.trace_id) for t in results)

    assert result_ids == expected_ids, (
        f"Filter(dim={filter_dim}, pid={filter_pid}, success={filter_success}): "
        f"expected {len(expected)} traces, got {len(results)}"
    )


# ---------------------------------------------------------------------------
# Property 40: Aggregate metrics are consistent with individual traces
# ---------------------------------------------------------------------------


@st.composite
def _aggregate_scenario(draw: st.DrawFn):
    """Generate a set of recent traces for a single plugin and return
    (service, plugin_id, traces) for aggregate verification."""
    plugin_id = uuid4()
    dimension = draw(safe_text)
    num_traces = draw(st.integers(min_value=1, max_value=20))

    svc = _fresh_service()
    traces: list[TraceEvent] = []

    for _ in range(num_traces):
        latency = draw(st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))
        cost = draw(st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False))
        success = draw(st.booleans())
        t = _make_recent_trace(
            plugin_id=plugin_id,
            dimension=dimension,
            latency_ms=latency,
            cost_usd=cost,
            success=success,
        )
        svc.emit_trace(t)
        traces.append(t)

    return svc, plugin_id, traces


@given(scenario=_aggregate_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_aggregate_metrics_consistent_with_traces(scenario) -> None:
    """For any set of traces for a plugin, the computed AggregateMetrics
    shall have: total_invocations == count of traces, success_rate ==
    successes/total, mean_latency == avg of latencies, mean_cost == avg
    of costs.

    # Feature: conviction-room, Property 40: Aggregate metrics are consistent with individual traces
    **Validates: Requirements 12.4, 12.5**
    """
    svc, plugin_id, traces = scenario

    metrics = svc.get_plugin_metrics(plugin_id, time_window="24h")

    total = len(traces)
    successes = sum(1 for t in traces if t.success)
    expected_success_rate = successes / total
    expected_mean_latency = sum(t.latency_ms for t in traces) / total
    expected_mean_cost = sum(t.cost_usd for t in traces) / total

    assert metrics.total_invocations == total, (
        f"total_invocations: expected {total}, got {metrics.total_invocations}"
    )

    assert math.isclose(metrics.success_rate, expected_success_rate, rel_tol=1e-9, abs_tol=1e-9), (
        f"success_rate: expected {expected_success_rate}, got {metrics.success_rate}"
    )

    assert math.isclose(metrics.mean_latency_ms, expected_mean_latency, rel_tol=1e-6, abs_tol=1e-9), (
        f"mean_latency_ms: expected {expected_mean_latency}, got {metrics.mean_latency_ms}"
    )

    assert math.isclose(metrics.mean_cost_usd, expected_mean_cost, rel_tol=1e-6, abs_tol=1e-9), (
        f"mean_cost_usd: expected {expected_mean_cost}, got {metrics.mean_cost_usd}"
    )
