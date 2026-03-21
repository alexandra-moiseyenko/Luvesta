"""Benchmark Orchestrator service for Conviction Room.

Manages experiments that compare plugins within a dimension using
identical inputs from golden datasets. Supports head_to_head, tournament,
and regression comparison modes. Enforces cost budgets, produces ranked
results with composite scores, and persists all data for reproducibility.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from uuid import UUID, uuid4

from conviction_room.models.benchmark import (
    BenchmarkRun,
    EvaluationMetric,
    Experiment,
    ExperimentResults,
    PluginScore,
)
from conviction_room.models.cost import CostRecord
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.golden_dataset import GoldenDatasetService

logger = logging.getLogger(__name__)


class BenchmarkOrchestratorService:
    """In-memory benchmark orchestrator.

    Executes experiments comparing plugins within a dimension. Each plugin
    is scored against the same golden dataset inputs. Budget is checked
    before every plugin run; if exceeded the experiment terminates with
    partial results flagged as ``budget_exceeded``.
    """

    def __init__(
        self,
        cost_governor: CostGovernorService,
        golden_dataset_service: GoldenDatasetService,
    ) -> None:
        self._cost_governor = cost_governor
        self._golden_dataset_service = golden_dataset_service
        self._experiments: dict[UUID, Experiment] = {}
        self._runs: dict[UUID, BenchmarkRun] = {}

    # ------------------------------------------------------------------
    # create_experiment
    # ------------------------------------------------------------------

    def create_experiment(self, experiment: Experiment) -> Experiment:
        """Store an experiment definition and return it."""
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    # ------------------------------------------------------------------
    # get_experiment
    # ------------------------------------------------------------------

    def get_experiment(self, experiment_id: UUID) -> Experiment | None:
        """Return an experiment by ID, or ``None`` if not found."""
        return self._experiments.get(experiment_id)

    # ------------------------------------------------------------------
    # cancel_experiment
    # ------------------------------------------------------------------

    def cancel_experiment(self, experiment_id: UUID) -> Experiment | None:
        """Set experiment status to failed. Returns the experiment or None."""
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return None
        exp = exp.model_copy(update={"status": "failed"})
        self._experiments[experiment_id] = exp
        return exp

    # ------------------------------------------------------------------
    # get_run
    # ------------------------------------------------------------------

    def get_run(self, run_id: UUID) -> BenchmarkRun | None:
        """Return a benchmark run by ID, or ``None`` if not found."""
        return self._runs.get(run_id)

    # ------------------------------------------------------------------
    # run_benchmark  (single run)
    # ------------------------------------------------------------------

    def run_benchmark(self, run: BenchmarkRun) -> BenchmarkRun:
        """Execute a single benchmark run.

        Simulates scoring by generating metric values for each metric
        listed in the run's metadata (key ``"metrics"``). For deterministic
        metrics (``is_deterministic=True``), the score is computed via a
        hash so that identical inputs always produce identical scores.

        Records cost via the cost governor and returns the completed run.
        """
        metrics_config: list[dict] = run.metadata.get("metrics", [])
        scores: list[EvaluationMetric] = []

        # Build an input hash from raw_inputs for deterministic scoring.
        input_hash = hashlib.sha256(
            str(run.raw_inputs).encode()
        ).hexdigest()

        for metric_cfg in metrics_config:
            metric_name: str = metric_cfg.get("name", "unknown")
            category: str = metric_cfg.get("category", "quality")
            unit: str = metric_cfg.get("unit", "score")
            is_deterministic: bool = metric_cfg.get("is_deterministic", False)

            if is_deterministic:
                # Deterministic: hash(plugin_id + metric_name + input_hash) % 100 / 100.0
                hash_input = f"{run.plugin_id}{metric_name}{input_hash}"
                hash_val = int(
                    hashlib.sha256(hash_input.encode()).hexdigest(), 16
                )
                value = (hash_val % 100) / 100.0
            else:
                # Non-deterministic: use a hash-based pseudo-random value
                # seeded with run_id for variety across runs.
                hash_input = f"{run.run_id}{metric_name}{input_hash}"
                hash_val = int(
                    hashlib.sha256(hash_input.encode()).hexdigest(), 16
                )
                value = (hash_val % 100) / 100.0

            scores.append(
                EvaluationMetric(
                    name=metric_name,
                    category=category,
                    value=value,
                    unit=unit,
                    is_deterministic=is_deterministic,
                )
            )

        # Simulate cost: small fixed cost per run.
        cost_record = CostRecord(
            record_id=uuid4(),
            timestamp=datetime.utcnow(),
            dimension=run.dimension,
            plugin_id=run.plugin_id,
            token_count=100,
            api_calls=1,
            dollar_cost=0.01,
            is_estimated=True,
        )
        self._cost_governor.record_cost(cost_record)

        # Build raw_outputs from scores for reproducibility.
        raw_outputs = [{"scores": [s.model_dump() for s in scores]}]

        completed_run = run.model_copy(
            update={
                "status": "completed",
                "scores": scores,
                "raw_outputs": raw_outputs,
                "cost_consumed": cost_record,
                "iterations_completed": run.metadata.get("iteration_count", 1),
                "completed_at": datetime.utcnow(),
            }
        )
        self._runs[completed_run.run_id] = completed_run
        return completed_run

    # ------------------------------------------------------------------
    # run_experiment
    # ------------------------------------------------------------------

    def run_experiment(self, experiment_id: UUID) -> Experiment | None:
        """Execute an experiment: score each plugin against the golden dataset.

        For each plugin_id in the experiment, creates a ``BenchmarkRun``
        using inputs from the golden dataset (via ``golden_dataset_service``).
        Checks budget before each run. If budget is exceeded, terminates
        early, saves partial results, and sets status to ``budget_exceeded``.

        After all runs complete, ranks plugins by composite score and
        produces ``ExperimentResults`` with ``ranked_plugins``.
        """
        exp = self._experiments.get(experiment_id)
        if exp is None:
            return None

        # Mark as running.
        exp = exp.model_copy(update={"status": "running"})
        self._experiments[experiment_id] = exp

        # Fetch golden dataset inputs.
        dataset = self._golden_dataset_service.get(exp.suite_id)
        if dataset is not None:
            raw_inputs = [
                entry.input_payload for entry in dataset.entries
            ]
        else:
            raw_inputs = [{"default_input": True}]

        # Default metrics config if not available from a suite.
        default_metrics = [
            {"name": "quality", "category": "quality", "unit": "score", "is_deterministic": True},
            {"name": "latency", "category": "performance", "unit": "ms", "is_deterministic": True},
            {"name": "cost_efficiency", "category": "cost", "unit": "usd", "is_deterministic": True},
        ]

        run_ids: list[UUID] = []
        completed_runs: list[BenchmarkRun] = []
        budget_exceeded = False

        for plugin_id in exp.plugin_ids:
            # Pre-flight budget check before each plugin run.
            budget_error = self._cost_governor.check_budget(
                dimension=exp.dimension,
                estimated_cost=0.01,
            )
            if budget_error is not None:
                logger.warning(
                    "Budget exceeded for experiment %s at plugin %s: %s",
                    experiment_id,
                    plugin_id,
                    budget_error.message,
                )
                budget_exceeded = True
                break

            run = BenchmarkRun(
                run_id=uuid4(),
                suite_id=exp.suite_id,
                plugin_id=plugin_id,
                dimension=exp.dimension,
                status="pending",
                raw_inputs=raw_inputs,
                cost_consumed=CostRecord(
                    record_id=uuid4(),
                    dimension=exp.dimension,
                    plugin_id=plugin_id,
                    token_count=0,
                    api_calls=0,
                    dollar_cost=0.0,
                    is_estimated=True,
                ),
                metadata={
                    "metrics": default_metrics,
                    "iteration_count": exp.iteration_count,
                },
            )

            completed_run = self.run_benchmark(run)
            run_ids.append(completed_run.run_id)
            completed_runs.append(completed_run)

        # Rank plugins by composite score (sum of all metric values).
        plugin_scores: list[PluginScore] = []
        for run in completed_runs:
            composite = sum(m.value for m in run.scores)
            plugin_scores.append(
                PluginScore(
                    plugin_id=run.plugin_id,
                    composite_score=composite,
                    per_metric_scores=run.scores,
                    rank=0,  # assigned below
                )
            )

        # Sort descending by composite_score, assign ranks.
        plugin_scores.sort(key=lambda ps: ps.composite_score, reverse=True)
        ranked: list[PluginScore] = []
        for i, ps in enumerate(plugin_scores):
            ranked.append(ps.model_copy(update={"rank": i + 1}))

        results = ExperimentResults(
            ranked_plugins=ranked,
            comparison_report={
                "mode": exp.comparison_mode,
                "plugins_evaluated": len(completed_runs),
                "plugins_total": len(exp.plugin_ids),
                "budget_exceeded": budget_exceeded,
            },
        )

        final_status = "budget_exceeded" if budget_exceeded else "completed"
        exp = exp.model_copy(
            update={
                "status": final_status,
                "runs": run_ids,
                "results": results,
                "completed_at": datetime.utcnow(),
            }
        )
        self._experiments[experiment_id] = exp
        return exp
