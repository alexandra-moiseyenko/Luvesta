"""Testability Classification service for Conviction Room.

Classifies each dimension into one of three AI-testability tiers and tracks
which metrics are automatable vs. requiring human review.

- fully_automatable: experiments complete end-to-end without human intervention
- semi_automatable: automated portion runs, then human-review tasks are queued
  for non-automatable metrics
- human_required: auto-promotion is blocked regardless of benchmark scores

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

from conviction_room.models.testability import TestabilityClassification


class TestabilityService:
    """In-memory testability classification store.

    Stores one ``TestabilityClassification`` per dimension and exposes
    helpers that other services (Benchmark Orchestrator, Experiment
    Automation) use to decide promotion and review behaviour.
    """

    def __init__(self) -> None:
        self._store: dict[str, TestabilityClassification] = {}

    # ------------------------------------------------------------------
    # classify_dimension
    # ------------------------------------------------------------------

    def classify_dimension(
        self,
        dimension: str,
        tier: str,
        automatable_metrics: list[str],
        human_review_metrics: list[str],
    ) -> TestabilityClassification:
        """Create or update the testability classification for *dimension*.

        Validates:
        - *tier* is one of the three allowed values.
        - The union of *automatable_metrics* and *human_review_metrics*
          covers all metrics for the dimension (i.e. both lists together
          must be non-empty and have no unexpected gaps — the caller is
          responsible for providing the full metric set).

        Returns the persisted ``TestabilityClassification``.

        Raises ``ValueError`` on invalid input.
        """
        valid_tiers = {"fully_automatable", "semi_automatable", "human_required"}
        if tier not in valid_tiers:
            raise ValueError(
                f"Invalid tier '{tier}'. Must be one of {sorted(valid_tiers)}."
            )

        all_metrics = set(automatable_metrics) | set(human_review_metrics)
        if not all_metrics:
            raise ValueError(
                "The union of automatable_metrics and human_review_metrics "
                "must cover at least one metric."
            )

        classification = TestabilityClassification(
            dimension=dimension,
            tier=tier,
            automatable_metrics=list(automatable_metrics),
            human_review_metrics=list(human_review_metrics),
        )
        self._store[dimension] = classification
        return classification

    # ------------------------------------------------------------------
    # get_classification
    # ------------------------------------------------------------------

    def get_classification(self, dimension: str) -> TestabilityClassification | None:
        """Return the classification for *dimension*, or ``None``."""
        return self._store.get(dimension)

    # ------------------------------------------------------------------
    # list_classifications
    # ------------------------------------------------------------------

    def list_classifications(self) -> list[TestabilityClassification]:
        """Return all stored classifications."""
        return list(self._store.values())

    # ------------------------------------------------------------------
    # can_auto_promote  (Requirement 6.2 / 6.5)
    # ------------------------------------------------------------------

    def can_auto_promote(self, dimension: str) -> bool:
        """Return ``True`` only when *dimension* is fully_automatable.

        Semi-automatable and human-required dimensions must not be
        auto-promoted based on benchmark scores alone.
        """
        classification = self._store.get(dimension)
        if classification is None:
            return False
        return classification.tier == "fully_automatable"

    # ------------------------------------------------------------------
    # needs_human_review  (Requirement 6.3 / 6.4)
    # ------------------------------------------------------------------

    def needs_human_review(self, dimension: str) -> list[str]:
        """Return the list of metrics that require human review.

        - fully_automatable → empty list
        - semi_automatable  → human_review_metrics
        - human_required    → all metrics (automatable + human_review)
        - unknown dimension → empty list
        """
        classification = self._store.get(dimension)
        if classification is None:
            return []

        if classification.tier == "fully_automatable":
            return []
        if classification.tier == "semi_automatable":
            return list(classification.human_review_metrics)
        # human_required — everything needs human review
        return list(classification.automatable_metrics) + list(
            classification.human_review_metrics
        )
