# Feature: conviction-room, Property 25: Cost tracking records all required fields
# Feature: conviction-room, Property 26: Cost budget enforcement rejects over-budget invocations
# Feature: conviction-room, Property 27: Cost 80% warning threshold
# Feature: conviction-room, Property 28: Cost summary is internally consistent
"""
Property tests for Cost Governor invariants.

Property 25 — For any plugin invocation, the CostGovernor shall create a cost
              ledger entry containing: timestamp, dimension, plugin_id,
              token_count, api_calls, and dollar_cost.  If the plugin did not
              report token usage (token_count=0), the entry shall have
              is_estimated=True and a warning shall be logged.
Property 26 — For any plugin invocation where the estimated cost would cause
              cumulative spend to exceed the active CostBudget, the invocation
              shall be rejected with a budget-exceeded error.
Property 27 — For any CostBudget where cumulative spend crosses 80% of the
              ceiling, the CostGovernor shall emit a warning event.
Property 28 — For any cost query response, current_spend + remaining_budget
              shall equal the total budget ceiling, and the per-dimension and
              per-plugin breakdowns shall sum to current_spend.

**Validates: Requirements 7.1, 7.2, 7.4, 7.5, 7.6, 7.7**
"""

from __future__ import annotations

import logging
import math
from uuid import uuid4

from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st

from conviction_room.models.cost import CostBudget, CostRecord
from conviction_room.models.plugin import PluginError
from conviction_room.services.cost_governor import CostGovernorService
from tests.conftest import cost_budget_st, cost_record_st, safe_text, pos_floats, safe_ints


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_service() -> CostGovernorService:
    """Return a new CostGovernorService with no state."""
    return CostGovernorService()


# ---------------------------------------------------------------------------
# Property 25: Cost tracking records all required fields
# ---------------------------------------------------------------------------


@given(record=cost_record_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_cost_record_has_all_required_fields(record: CostRecord) -> None:
    """For any plugin invocation, the CostGovernor shall create a cost ledger
    entry containing: timestamp, dimension, plugin_id, token_count, api_calls,
    and dollar_cost.

    # Feature: conviction-room, Property 25: Cost tracking records all required fields
    **Validates: Requirements 7.1, 7.7**
    """
    svc = _fresh_service()
    stored = svc.record_cost(record)

    # All required fields must be present and non-None
    assert stored.timestamp is not None, "timestamp must be present"
    assert stored.dimension is not None, "dimension must be present"
    assert stored.plugin_id is not None, "plugin_id must be present"
    assert stored.token_count is not None, "token_count must be present"
    assert stored.api_calls is not None, "api_calls must be present"
    assert stored.dollar_cost is not None, "dollar_cost must be present"

    # The entry must appear in the ledger
    ledger = svc.get_ledger()
    assert len(ledger) == 1
    assert ledger[0].record_id == stored.record_id



@given(
    dimension=safe_text,
    plugin_id=st.uuids(),
    api_calls=safe_ints,
    dollar_cost=pos_floats,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_zero_token_count_sets_is_estimated(
    dimension: str,
    plugin_id,
    api_calls: int,
    dollar_cost: float,
) -> None:
    """If the plugin did not report token usage (token_count=0), the entry
    shall have is_estimated=True and a warning shall be logged.

    # Feature: conviction-room, Property 25: Cost tracking records all required fields
    **Validates: Requirements 7.6**
    """
    assume(dollar_cost > 0)  # need positive cost so estimation produces tokens

    svc = _fresh_service()
    record = CostRecord(
        dimension=dimension,
        plugin_id=plugin_id,
        token_count=0,
        api_calls=api_calls,
        dollar_cost=dollar_cost,
        is_estimated=False,
    )

    with _capture_warnings() as warnings_list:
        stored = svc.record_cost(record)

    assert stored.is_estimated is True, (
        "Record with token_count=0 must have is_estimated=True"
    )
    assert stored.token_count > 0, (
        "Estimated token count should be positive"
    )
    # A warning should have been logged
    assert any("estimated" in w.lower() or "token" in w.lower() for w in warnings_list), (
        f"Expected a warning about estimated tokens, got: {warnings_list}"
    )


class _capture_warnings:
    """Context manager that captures WARNING-level log messages from the
    cost_governor logger."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._handler: logging.Handler | None = None

    def __enter__(self) -> list[str]:
        logger = logging.getLogger("conviction_room.services.cost_governor")
        handler = logging.Handler()
        handler.emit = lambda record: self.messages.append(record.getMessage())  # type: ignore[assignment]
        handler.setLevel(logging.WARNING)
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        self._handler = handler
        return self.messages

    def __exit__(self, *_: object) -> None:
        if self._handler:
            logger = logging.getLogger("conviction_room.services.cost_governor")
            logger.removeHandler(self._handler)


# ---------------------------------------------------------------------------
# Property 26: Cost budget enforcement rejects over-budget invocations
# ---------------------------------------------------------------------------


@st.composite
def _over_budget_scenario(draw: st.DrawFn):
    """Generate a scenario where a new invocation would exceed the budget.

    Returns (service, dimension, estimated_cost) where the service already
    has a budget set and enough prior spend that estimated_cost pushes it
    over the ceiling.
    """
    dimension = draw(safe_text)
    ceiling = draw(st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    # Prior spend is between 50% and 99% of ceiling
    prior_spend = draw(st.floats(
        min_value=ceiling * 0.5,
        max_value=ceiling * 0.99,
        allow_nan=False,
        allow_infinity=False,
    ))
    # Estimated cost pushes total over ceiling
    remaining = ceiling - prior_spend
    estimated_cost = draw(st.floats(
        min_value=remaining + 0.01,
        max_value=remaining + ceiling,
        allow_nan=False,
        allow_infinity=False,
    ))

    svc = _fresh_service()
    budget = CostBudget(
        scope="dimension_period",
        dimension=dimension,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=ceiling,
    )
    svc.set_budget(budget)

    # Record prior spend as a single ledger entry
    svc.record_cost(CostRecord(
        dimension=dimension,
        plugin_id=uuid4(),
        token_count=100,
        api_calls=1,
        dollar_cost=prior_spend,
        is_estimated=False,
    ))

    return svc, dimension, estimated_cost


@given(scenario=_over_budget_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_over_budget_invocation_rejected(scenario) -> None:
    """For any plugin invocation where the estimated cost would cause
    cumulative spend to exceed the active CostBudget, the invocation shall
    be rejected with a budget-exceeded error.

    # Feature: conviction-room, Property 26: Cost budget enforcement rejects over-budget invocations
    **Validates: Requirements 7.2**
    """
    svc, dimension, estimated_cost = scenario

    result = svc.check_budget(dimension, estimated_cost)

    assert isinstance(result, PluginError), (
        f"Expected PluginError for over-budget invocation, got {result}"
    )
    assert result.error_code == "BUDGET_EXCEEDED"


@st.composite
def _under_budget_scenario(draw: st.DrawFn):
    """Generate a scenario where a new invocation stays within budget.

    Returns (service, dimension, estimated_cost).
    """
    dimension = draw(safe_text)
    ceiling = draw(st.floats(min_value=10.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    # Prior spend is between 0% and 40% of ceiling
    prior_spend = draw(st.floats(
        min_value=0.0,
        max_value=ceiling * 0.4,
        allow_nan=False,
        allow_infinity=False,
    ))
    # Estimated cost keeps total well under ceiling
    remaining = ceiling - prior_spend
    estimated_cost = draw(st.floats(
        min_value=0.001,
        max_value=remaining * 0.5,
        allow_nan=False,
        allow_infinity=False,
    ))

    svc = _fresh_service()
    budget = CostBudget(
        scope="dimension_period",
        dimension=dimension,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=ceiling,
    )
    svc.set_budget(budget)

    if prior_spend > 0:
        svc.record_cost(CostRecord(
            dimension=dimension,
            plugin_id=uuid4(),
            token_count=100,
            api_calls=1,
            dollar_cost=prior_spend,
            is_estimated=False,
        ))

    return svc, dimension, estimated_cost


@given(scenario=_under_budget_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_under_budget_invocation_approved(scenario) -> None:
    """For any plugin invocation where the estimated cost stays within the
    active CostBudget, the invocation shall be approved (no error).

    # Feature: conviction-room, Property 26: Cost budget enforcement rejects over-budget invocations
    **Validates: Requirements 7.2**
    """
    svc, dimension, estimated_cost = scenario

    result = svc.check_budget(dimension, estimated_cost)

    assert result is None, (
        f"Expected approval (None) for under-budget invocation, got {result}"
    )


# ---------------------------------------------------------------------------
# Property 27: Cost 80% warning threshold
# ---------------------------------------------------------------------------


@st.composite
def _warning_threshold_scenario(draw: st.DrawFn):
    """Generate a scenario where cumulative spend crosses 80% of the ceiling.

    Returns (service, dimension, budget_ceiling).
    """
    dimension = draw(safe_text)
    ceiling = draw(st.floats(min_value=10.0, max_value=1e6, allow_nan=False, allow_infinity=False))
    threshold = ceiling * 0.8

    # First spend: below 80%
    first_spend = draw(st.floats(
        min_value=0.0,
        max_value=threshold * 0.9,
        allow_nan=False,
        allow_infinity=False,
    ))
    # Second spend: pushes total past 80%
    needed = threshold - first_spend
    second_spend = draw(st.floats(
        min_value=max(needed + 0.01, 0.01),
        max_value=max(needed + ceiling * 0.1, 0.02),
        allow_nan=False,
        allow_infinity=False,
    ))

    svc = _fresh_service()
    budget = CostBudget(
        scope="global_period",
        dimension=None,
        period="daily",
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=ceiling,
    )
    svc.set_budget(budget)

    return svc, dimension, first_spend, second_spend, ceiling


@given(scenario=_warning_threshold_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_80_percent_warning_emitted(scenario) -> None:
    """For any CostBudget where cumulative spend crosses 80% of the ceiling,
    the CostGovernor shall emit a warning event.

    # Feature: conviction-room, Property 27: Cost 80% warning threshold
    **Validates: Requirements 7.4**
    """
    svc, dimension, first_spend, second_spend, ceiling = scenario

    # Record first spend (below 80%)
    svc.record_cost(CostRecord(
        dimension=dimension,
        plugin_id=uuid4(),
        token_count=100,
        api_calls=1,
        dollar_cost=first_spend,
        is_estimated=False,
    ))

    warnings_before = len(svc.warning_events)

    # Record second spend (crosses 80%)
    svc.record_cost(CostRecord(
        dimension=dimension,
        plugin_id=uuid4(),
        token_count=100,
        api_calls=1,
        dollar_cost=second_spend,
        is_estimated=False,
    ))

    total_spend = first_spend + second_spend
    threshold = ceiling * 0.8

    if total_spend >= threshold:
        assert len(svc.warning_events) > warnings_before, (
            f"Expected warning event when spend ${total_spend:.4f} crosses "
            f"80% threshold ${threshold:.4f} of ceiling ${ceiling:.4f}"
        )
        latest_warning = svc.warning_events[-1]
        assert latest_warning["type"] == "BUDGET_WARNING_80_PERCENT"
        assert latest_warning["threshold_pct"] == 0.8


# ---------------------------------------------------------------------------
# Property 28: Cost summary is internally consistent
# ---------------------------------------------------------------------------


@st.composite
def _summary_scenario(draw: st.DrawFn):
    """Generate a service with a budget and several ledger entries, then
    return (service, scope, dimension, period) for summary query."""
    scope = draw(st.sampled_from(["global_period", "dimension_period"]))
    dimension = draw(safe_text) if scope == "dimension_period" else None
    period = draw(st.sampled_from(["daily", "weekly"]))
    ceiling = draw(st.floats(min_value=100.0, max_value=1e6, allow_nan=False, allow_infinity=False))

    svc = _fresh_service()
    budget = CostBudget(
        scope=scope,
        dimension=dimension,
        period=period,
        max_tokens=10_000_000,
        max_api_calls=100_000,
        max_dollar_cost=ceiling,
    )
    svc.set_budget(budget)

    # Record several cost entries
    num_entries = draw(st.integers(min_value=1, max_value=10))
    target_dim = dimension if dimension else draw(safe_text)
    for _ in range(num_entries):
        cost = draw(st.floats(min_value=0.01, max_value=ceiling / (num_entries * 2), allow_nan=False, allow_infinity=False))
        svc.record_cost(CostRecord(
            dimension=target_dim,
            plugin_id=draw(st.uuids()),
            token_count=draw(safe_ints.filter(lambda x: x > 0)),
            api_calls=draw(safe_ints),
            dollar_cost=cost,
            is_estimated=False,
        ))

    return svc, scope, dimension, period, ceiling


@given(scenario=_summary_scenario())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_cost_summary_internally_consistent(scenario) -> None:
    """For any cost query response, current_spend + remaining_budget shall
    equal the total budget ceiling, and the per-dimension and per-plugin
    breakdowns shall sum to current_spend.

    # Feature: conviction-room, Property 28: Cost summary is internally consistent
    **Validates: Requirements 7.5**
    """
    svc, scope, dimension, period, ceiling = scenario

    result = svc.get_summary(scope, dimension, period)

    assert not isinstance(result, PluginError), (
        f"Expected CostSummary but got error: {result}"
    )

    # Invariant 1: current_spend + remaining_budget == ceiling
    total = result.current_spend + result.remaining_budget
    assert math.isclose(total, ceiling, rel_tol=1e-9, abs_tol=1e-9), (
        f"current_spend ({result.current_spend}) + remaining_budget "
        f"({result.remaining_budget}) = {total} != ceiling ({ceiling})"
    )

    # Invariant 2: sum of per-dimension breakdown == current_spend
    dim_sum = sum(result.breakdown_by_dimension.values())
    assert math.isclose(dim_sum, result.current_spend, rel_tol=1e-6, abs_tol=1e-9), (
        f"breakdown_by_dimension sum ({dim_sum}) != current_spend ({result.current_spend})"
    )

    # Invariant 3: sum of per-plugin breakdown == current_spend
    plugin_sum = sum(result.breakdown_by_plugin.values())
    assert math.isclose(plugin_sum, result.current_spend, rel_tol=1e-6, abs_tol=1e-9), (
        f"breakdown_by_plugin sum ({plugin_sum}) != current_spend ({result.current_spend})"
    )
