# Feature: conviction-room, Property 21: Every dimension has a testability classification
# Feature: conviction-room, Property 22: Fully-automatable dimensions run without human intervention
# Feature: conviction-room, Property 23: Semi-automatable dimensions queue human review
# Feature: conviction-room, Property 24: Human-required dimensions block auto-promotion
"""
Property tests for Testability Classification service.

Property 21 — After classify_dimension is called, get_classification returns
              a non-None result and list_classifications includes it.
Property 22 — For fully_automatable tier, can_auto_promote returns True and
              needs_human_review returns an empty list.
Property 23 — For semi_automatable tier, can_auto_promote returns False and
              needs_human_review returns exactly the human_review_metrics.
Property 24 — For human_required tier, can_auto_promote returns False and
              needs_human_review returns ALL metrics (automatable + human_review).

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from conviction_room.services.testability import TestabilityService
from tests.conftest import safe_text


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_tier_st = st.sampled_from(["fully_automatable", "semi_automatable", "human_required"])

# Generate non-empty, unique metric lists whose union is also non-empty.
_metric_list = st.lists(
    st.text(min_size=1, max_size=30, alphabet=st.characters(categories=("L", "N"))),
    min_size=1,
    max_size=5,
    unique=True,
)


# ---------------------------------------------------------------------------
# Property 21: Every dimension has a testability classification
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    tier=_tier_st,
    automatable=_metric_list,
    human_review=_metric_list,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_every_dimension_has_testability_classification(
    dimension: str,
    tier: str,
    automatable: list[str],
    human_review: list[str],
) -> None:
    """After classify_dimension is called, get_classification returns a
    non-None result and list_classifications includes it.

    # Feature: conviction-room, Property 21: Every dimension has a testability classification
    **Validates: Requirements 6.1, 6.4**
    """
    svc = TestabilityService()

    classification = svc.classify_dimension(
        dimension=dimension,
        tier=tier,
        automatable_metrics=automatable,
        human_review_metrics=human_review,
    )

    # get_classification returns a non-None result.
    retrieved = svc.get_classification(dimension)
    assert retrieved is not None, "get_classification must return non-None after classify_dimension"
    assert retrieved.dimension == dimension
    assert retrieved.tier == tier
    assert retrieved.automatable_metrics == automatable
    assert retrieved.human_review_metrics == human_review

    # list_classifications includes the classification.
    all_classifications = svc.list_classifications()
    assert any(
        c.dimension == dimension for c in all_classifications
    ), "list_classifications must include the classified dimension"

    # The union of automatable + human_review covers all metrics.
    all_metrics = set(retrieved.automatable_metrics) | set(retrieved.human_review_metrics)
    assert len(all_metrics) > 0, "Union of metrics must be non-empty"


# ---------------------------------------------------------------------------
# Property 22: Fully-automatable dimensions run without human intervention
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    automatable=_metric_list,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_fully_automatable_no_human_intervention(
    dimension: str,
    automatable: list[str],
) -> None:
    """For fully_automatable tier, can_auto_promote returns True and
    needs_human_review returns an empty list.

    # Feature: conviction-room, Property 22: Fully-automatable dimensions run without human intervention
    **Validates: Requirements 6.2**
    """
    svc = TestabilityService()

    svc.classify_dimension(
        dimension=dimension,
        tier="fully_automatable",
        automatable_metrics=automatable,
        human_review_metrics=[],
    )

    assert svc.can_auto_promote(dimension) is True, (
        "fully_automatable dimensions must allow auto-promotion"
    )
    assert svc.needs_human_review(dimension) == [], (
        "fully_automatable dimensions must not need human review"
    )


# ---------------------------------------------------------------------------
# Property 23: Semi-automatable dimensions queue human review
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    automatable=_metric_list,
    human_review=_metric_list,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_semi_automatable_queues_human_review(
    dimension: str,
    automatable: list[str],
    human_review: list[str],
) -> None:
    """For semi_automatable tier, can_auto_promote returns False and
    needs_human_review returns exactly the human_review_metrics.

    # Feature: conviction-room, Property 23: Semi-automatable dimensions queue human review
    **Validates: Requirements 6.3**
    """
    svc = TestabilityService()

    svc.classify_dimension(
        dimension=dimension,
        tier="semi_automatable",
        automatable_metrics=automatable,
        human_review_metrics=human_review,
    )

    assert svc.can_auto_promote(dimension) is False, (
        "semi_automatable dimensions must not allow auto-promotion"
    )

    review_metrics = svc.needs_human_review(dimension)
    assert review_metrics == human_review, (
        f"semi_automatable needs_human_review should return exactly "
        f"human_review_metrics {human_review}, got {review_metrics}"
    )


# ---------------------------------------------------------------------------
# Property 24: Human-required dimensions block auto-promotion
# ---------------------------------------------------------------------------


@given(
    dimension=safe_text,
    automatable=_metric_list,
    human_review=_metric_list,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_human_required_blocks_auto_promotion(
    dimension: str,
    automatable: list[str],
    human_review: list[str],
) -> None:
    """For human_required tier, can_auto_promote returns False and
    needs_human_review returns ALL metrics (automatable + human_review).

    # Feature: conviction-room, Property 24: Human-required dimensions block auto-promotion
    **Validates: Requirements 6.5**
    """
    svc = TestabilityService()

    svc.classify_dimension(
        dimension=dimension,
        tier="human_required",
        automatable_metrics=automatable,
        human_review_metrics=human_review,
    )

    assert svc.can_auto_promote(dimension) is False, (
        "human_required dimensions must not allow auto-promotion"
    )

    review_metrics = svc.needs_human_review(dimension)
    expected = automatable + human_review
    assert review_metrics == expected, (
        f"human_required needs_human_review should return ALL metrics "
        f"{expected}, got {review_metrics}"
    )
