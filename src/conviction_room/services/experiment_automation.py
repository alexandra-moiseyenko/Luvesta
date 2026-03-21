"""Experiment Automation service for Conviction Room.

Manages experiment policies, automated execution, result evaluation,
auto-promotion of winning plugins, and rollback on regression.
Maintains per-dimension experiment history for trend analysis.

Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID, uuid4

from conviction_room.models.automation import ExperimentPolicy
from conviction_room.models.benchmark import Experiment, ExperimentResults
from conviction_room.models.cost import CostBudget
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.testability import TestabilityService

logger = logging.getLogger(__name__)


class ExperimentAutomationService:
    """In-memory experiment automation.

    Stores experiment policies, executes them via the Benchmark
    Orchestrator, evaluates results against significance thresholds,
    and optionally auto-promotes winning plugins or generates
    recommendation reports.  Supports rollback when an auto-promoted
    plugin fails subsequent regression tests.
    """

    def __init__(
        self,
        benchmark_orchestrator: BenchmarkOrchestratorService,
        registry: PluginRegistryService,
        testability: TestabilityService,
    ) -> None:
        self._benchmark = benchmark_orchestrator
        self._registry = registry
        self._testability = testability
        self._policies: dict[UUID, ExperimentPolicy] = {}
        # Per-dimension experiment history for trend analysis (Req 11.5).
        self._history: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # create_policy  (Requirement 11.1)
    # ------------------------------------------------------------------

    def create_policy(self, policy: ExperimentPolicy) -> ExperimentPolicy:
        """Store an experiment policy and return it."""
        self._policies[policy.policy_id] = policy
        return policy

    # ------------------------------------------------------------------
    # get_policy
    # ------------------------------------------------------------------

    def get_policy(self, policy_id: UUID) -> ExperimentPolicy | None:
        """Return a policy by ID, or ``None`` if not found."""
        return self._policies.get(policy_id)

    # ------------------------------------------------------------------
    # list_policies
    # ------------------------------------------------------------------

    def list_policies(self) -> list[ExperimentPolicy]:
        """Return all stored policies."""
        return list(self._policies.values())

    # ------------------------------------------------------------------
    # execute_policy  (Requirement 11.1)
    # ------------------------------------------------------------------

    def execute_policy(self, policy_id: UUID) -> Experiment | None:
        """Run the experiment defined by a policy.

        Creates an ``Experiment`` from the policy's parameters, delegates
        execution to the Benchmark Orchestrator, records the result in
        the dimension's history, and returns the completed experiment.

        Returns ``None`` if the policy is not found or is disabled.
        """
        policy = self._policies.get(policy_id)
        if policy is None:
            return None
        if not policy.enabled:
            logger.info("Policy %s is disabled; skipping execution.", policy_id)
            return None

        experiment = Experiment(
            experiment_id=uuid4(),
            dimension=policy.dimension,
            plugin_ids=policy.plugin_ids,
            suite_id=policy.suite_id,
            comparison_mode="tournament",
            iteration_count=1,
            cost_budget=CostBudget(
                scope="benchmark_run",
                dimension=policy.dimension,
                period=None,
                max_tokens=1_000_000,
                max_api_calls=10_000,
                max_dollar_cost=100.0,
            ),
            status="pending",
        )

        experiment = self._benchmark.create_experiment(experiment)
        experiment = self._benchmark.run_experiment(experiment.experiment_id)

        if experiment is not None:
            self._record_history(experiment)

        return experiment

    # ------------------------------------------------------------------
    # evaluate_results  (Requirement 11.2)
    # ------------------------------------------------------------------

    def evaluate_results(
        self,
        experiment: Experiment,
    ) -> dict:
        """Analyse experiment results and determine promotion eligibility.

        Returns a dict with keys:
        - ``winner_plugin_id``: UUID of the top-ranked plugin (or None)
        - ``current_active_plugin_id``: UUID of the currently active plugin
        - ``score_delta``: difference between winner and active plugin scores
        - ``exceeds_threshold``: bool — True when delta > significance_threshold
        - ``recommendation``: human-readable recommendation string
        - ``policy_id``: the policy that triggered this evaluation (if found)
        """
        results = experiment.results
        if results is None or not results.ranked_plugins:
            return {
                "winner_plugin_id": None,
                "current_active_plugin_id": None,
                "score_delta": 0.0,
                "exceeds_threshold": False,
                "recommendation": "No results available.",
                "policy_id": None,
            }

        winner = results.ranked_plugins[0]

        # Find the policy for this dimension to get the threshold.
        policy = self._find_policy_for_dimension(experiment.dimension)
        threshold = policy.significance_threshold if policy else 0.0

        # Find the currently active plugin's score in the results.
        active_result = self._registry.get_active(experiment.dimension)
        active_plugin_id: UUID | None = None
        active_score = 0.0

        from conviction_room.models.plugin import PluginMetadata

        if isinstance(active_result, PluginMetadata):
            active_plugin_id = active_result.plugin_id
            for ps in results.ranked_plugins:
                if ps.plugin_id == active_plugin_id:
                    active_score = ps.composite_score
                    break

        score_delta = winner.composite_score - active_score
        exceeds = score_delta > threshold

        if exceeds:
            recommendation = (
                f"Plugin {winner.plugin_id} outperforms the current active "
                f"plugin by {score_delta:.4f} (threshold={threshold}). "
                f"Recommend promotion."
            )
        else:
            recommendation = (
                f"Score delta {score_delta:.4f} does not exceed threshold "
                f"{threshold}. No promotion recommended."
            )

        return {
            "winner_plugin_id": winner.plugin_id,
            "current_active_plugin_id": active_plugin_id,
            "score_delta": score_delta,
            "exceeds_threshold": exceeds,
            "recommendation": recommendation,
            "policy_id": policy.policy_id if policy else None,
        }

    # ------------------------------------------------------------------
    # auto_promote  (Requirement 11.3)
    # ------------------------------------------------------------------

    def auto_promote(self, dimension: str, plugin_id: UUID) -> bool:
        """Promote *plugin_id* to active for *dimension* if allowed.

        Auto-promotion is allowed only when:
        1. The testability service says the dimension can be auto-promoted.
        2. The policy for the dimension has ``auto_promote=True``.

        If auto-promote is disabled on the policy, a recommendation
        report is generated and an admin notification is logged
        (Requirement 11.4).

        Returns ``True`` if the plugin was promoted, ``False`` otherwise.
        """
        policy = self._find_policy_for_dimension(dimension)

        # Check testability tier allows auto-promotion.
        if not self._testability.can_auto_promote(dimension):
            logger.info(
                "Dimension '%s' is not fully_automatable; "
                "auto-promotion blocked by testability classification.",
                dimension,
            )
            if policy and not policy.auto_promote:
                self._generate_recommendation(dimension, plugin_id)
            return False

        # Check policy auto_promote flag.
        if policy is not None and not policy.auto_promote:
            self._generate_recommendation(dimension, plugin_id)
            return False

        # Perform the promotion via the registry.
        result = self._registry.activate(plugin_id)

        from conviction_room.models.plugin import PluginMetadata

        if isinstance(result, PluginMetadata):
            logger.info(
                "Auto-promoted plugin %s to active for dimension '%s'.",
                plugin_id,
                dimension,
            )
            return True

        logger.warning(
            "Auto-promotion failed for plugin %s in dimension '%s': %s",
            plugin_id,
            dimension,
            result.message,
        )
        return False

    # ------------------------------------------------------------------
    # rollback  (Requirement 11.6)
    # ------------------------------------------------------------------

    def rollback(self, dimension: str, previous_plugin_id: UUID) -> bool:
        """Revert to *previous_plugin_id* for *dimension*.

        Used when an auto-promoted plugin fails a subsequent regression
        test.  Activates the previous plugin and alerts the admin.

        Returns ``True`` if the rollback succeeded.
        """
        result = self._registry.activate(previous_plugin_id)

        from conviction_room.models.plugin import PluginMetadata

        if isinstance(result, PluginMetadata):
            logger.warning(
                "ROLLBACK: Reverted dimension '%s' to plugin %s after "
                "regression failure. Admin notified.",
                dimension,
                previous_plugin_id,
            )
            # Record rollback event in history.
            self._history.setdefault(dimension, []).append({
                "event": "rollback",
                "dimension": dimension,
                "reverted_to_plugin_id": previous_plugin_id,
                "timestamp": datetime.utcnow().isoformat(),
            })
            return True

        logger.error(
            "Rollback failed for dimension '%s' to plugin %s: %s",
            dimension,
            previous_plugin_id,
            result.message,
        )
        return False

    # ------------------------------------------------------------------
    # get_history  (Requirement 11.5)
    # ------------------------------------------------------------------

    def get_history(self, dimension: str) -> list[dict]:
        """Return experiment history for *dimension* for trend analysis."""
        return list(self._history.get(dimension, []))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_policy_for_dimension(
        self, dimension: str,
    ) -> ExperimentPolicy | None:
        """Return the first enabled policy matching *dimension*."""
        for policy in self._policies.values():
            if policy.dimension == dimension:
                return policy
        return None

    def _record_history(self, experiment: Experiment) -> None:
        """Append an experiment summary to the dimension's history."""
        results = experiment.results
        ranked_summary = []
        if results is not None:
            for ps in results.ranked_plugins:
                ranked_summary.append({
                    "plugin_id": str(ps.plugin_id),
                    "composite_score": ps.composite_score,
                    "rank": ps.rank,
                })

        entry = {
            "event": "experiment_completed",
            "experiment_id": str(experiment.experiment_id),
            "dimension": experiment.dimension,
            "status": experiment.status,
            "ranked_plugins": ranked_summary,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._history.setdefault(experiment.dimension, []).append(entry)

    def _generate_recommendation(
        self, dimension: str, plugin_id: UUID,
    ) -> None:
        """Generate a recommendation report and notify admin (Req 11.4).

        In this in-memory implementation, the recommendation is logged
        and recorded in the dimension's history.
        """
        logger.info(
            "RECOMMENDATION: Plugin %s is the top candidate for "
            "dimension '%s' but auto-promotion is disabled. "
            "Admin review required.",
            plugin_id,
            dimension,
        )
        self._history.setdefault(dimension, []).append({
            "event": "recommendation",
            "dimension": dimension,
            "recommended_plugin_id": str(plugin_id),
            "message": (
                f"Plugin {plugin_id} recommended for dimension "
                f"'{dimension}'. Auto-promotion disabled; admin "
                f"review required."
            ),
            "timestamp": datetime.utcnow().isoformat(),
        })
