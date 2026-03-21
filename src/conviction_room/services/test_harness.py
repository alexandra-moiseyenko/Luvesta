"""Test Harness service for Conviction Room.

Orchestrates automated plugin testing: contract validation, benchmark
execution, and regression comparison.  Produces machine-readable JSON
test reports and respects Cost Governor budgets.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import UUID, uuid4

from conviction_room.contracts.base import PluginContractBase
from conviction_room.contracts.validator import validate_plugin_against_contract
from conviction_room.models.benchmark import BenchmarkRun, EvaluationMetric
from conviction_room.models.cost import CostRecord
from conviction_room.models.plugin import PluginError
from conviction_room.models.test_report import RegressionResult, TestReport
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.testability import TestabilityService

logger = logging.getLogger(__name__)


class TestHarnessService:
    """In-memory test harness.

    Coordinates contract validation → benchmark execution → regression
    comparison for plugins.  Stores test reports in-memory and delegates
    to the Cost Governor for budget enforcement and the Benchmark
    Orchestrator for benchmark runs.
    """

    def __init__(
        self,
        registry: PluginRegistryService,
        cost_governor: CostGovernorService,
        benchmark_orchestrator: BenchmarkOrchestratorService,
        testability: TestabilityService,
    ) -> None:
        self._registry = registry
        self._cost_governor = cost_governor
        self._benchmark = benchmark_orchestrator
        self._testability = testability
        self._reports: dict[UUID, TestReport] = {}
        # Queued benchmark tasks from auto-queue after contract validation.
        self._benchmark_queue: list[dict] = []

    # ------------------------------------------------------------------
    # validate_contract  (Requirement 9.1, 9.2, 9.3)
    # ------------------------------------------------------------------

    def validate_contract(
        self,
        plugin_id: UUID,
        dimension: str,
        contract: PluginContractBase,
        plugin_endpoints: list[dict],
        *,
        estimated_cost: float = 0.001,
    ) -> TestReport:
        """Validate a plugin against its dimension contract.

        If validation passes, automatically queues a benchmark run
        (Requirement 9.3).

        Returns a ``TestReport`` with ``test_mode="contract_validation"``.
        """
        # Budget check (Requirement 9.6).
        budget_err = self._cost_governor.check_budget(
            dimension=dimension,
            estimated_cost=estimated_cost,
        )
        if budget_err is not None:
            report = TestReport(
                report_id=uuid4(),
                test_mode="contract_validation",
                plugin_id=plugin_id,
                dimension=dimension,
                passed=False,
                violations=[],
                failure_details=[f"Budget exceeded: {budget_err.message}"],
            )
            self._reports[report.report_id] = report
            return report

        # Look up plugin metadata.
        plugin = self._registry.get(plugin_id)
        if plugin is None:
            report = TestReport(
                report_id=uuid4(),
                test_mode="contract_validation",
                plugin_id=plugin_id,
                dimension=dimension,
                passed=False,
                violations=[],
                failure_details=[f"Plugin {plugin_id} not found in registry"],
            )
            self._reports[report.report_id] = report
            return report

        # Run contract validation.
        violations = validate_plugin_against_contract(
            plugin, contract, plugin_endpoints,
        )

        passed = len(violations) == 0
        report = TestReport(
            report_id=uuid4(),
            test_mode="contract_validation",
            plugin_id=plugin_id,
            dimension=dimension,
            passed=passed,
            violations=violations,
            failure_details=violations if not passed else [],
        )
        self._reports[report.report_id] = report

        # Auto-queue benchmark if validation passes (Requirement 9.3).
        if passed:
            self._benchmark_queue.append({
                "plugin_id": plugin_id,
                "dimension": dimension,
            })
            logger.info(
                "Contract validation passed for plugin %s; "
                "benchmark auto-queued for dimension '%s'",
                plugin_id,
                dimension,
            )

        return report

    # ------------------------------------------------------------------
    # run_benchmark  (Requirement 9.1)
    # ------------------------------------------------------------------

    def run_benchmark(
        self,
        plugin_id: UUID,
        dimension: str,
        suite_id: UUID,
        *,
        metrics: list[dict] | None = None,
        raw_inputs: list[dict] | None = None,
        estimated_cost: float = 0.01,
    ) -> TestReport:
        """Run a benchmark suite against a plugin via the Benchmark Orchestrator.

        Returns a ``TestReport`` with ``test_mode="benchmark"`` and
        ``per_metric_scores`` populated from the benchmark run.
        """
        # Budget check (Requirement 9.6).
        budget_err = self._cost_governor.check_budget(
            dimension=dimension,
            estimated_cost=estimated_cost,
        )
        if budget_err is not None:
            report = TestReport(
                report_id=uuid4(),
                test_mode="benchmark",
                plugin_id=plugin_id,
                dimension=dimension,
                passed=False,
                failure_details=[f"Budget exceeded: {budget_err.message}"],
            )
            self._reports[report.report_id] = report
            return report

        if metrics is None:
            metrics = [
                {"name": "quality", "category": "quality", "unit": "score", "is_deterministic": True},
                {"name": "latency", "category": "performance", "unit": "ms", "is_deterministic": True},
                {"name": "cost_efficiency", "category": "cost", "unit": "usd", "is_deterministic": True},
            ]

        if raw_inputs is None:
            raw_inputs = [{"default_input": True}]

        run = BenchmarkRun(
            run_id=uuid4(),
            suite_id=suite_id,
            plugin_id=plugin_id,
            dimension=dimension,
            status="pending",
            raw_inputs=raw_inputs,
            cost_consumed=CostRecord(
                record_id=uuid4(),
                dimension=dimension,
                plugin_id=plugin_id,
                token_count=0,
                api_calls=0,
                dollar_cost=0.0,
                is_estimated=True,
            ),
            metadata={
                "metrics": metrics,
                "iteration_count": 1,
            },
        )

        completed_run = self._benchmark.run_benchmark(run)

        passed = completed_run.status == "completed"
        report = TestReport(
            report_id=uuid4(),
            test_mode="benchmark",
            plugin_id=plugin_id,
            dimension=dimension,
            passed=passed,
            per_metric_scores=completed_run.scores,
            failure_details=(
                [f"Benchmark run status: {completed_run.status}"]
                if not passed
                else []
            ),
        )
        self._reports[report.report_id] = report
        return report

    # ------------------------------------------------------------------
    # run_regression  (Requirement 9.1, 9.5)
    # ------------------------------------------------------------------

    def run_regression(
        self,
        plugin_id: UUID,
        dimension: str,
        prior_scores: list[EvaluationMetric],
        current_scores: list[EvaluationMetric],
        threshold: float = 0.1,
    ) -> TestReport:
        """Compare prior vs current scores and flag degradation.

        For each metric present in both lists, computes the delta.  If
        any metric degrades by more than *threshold* (as a fraction of
        the prior score), the plugin is flagged and auto-promotion is
        blocked via the testability service (Requirement 9.5).

        Returns a ``TestReport`` with ``test_mode="regression"``.
        """
        prior_map = {m.name: m for m in prior_scores}
        current_map = {m.name: m for m in current_scores}

        results: list[RegressionResult] = []
        degradations: list[str] = []

        for metric_name, prior_metric in prior_map.items():
            current_metric = current_map.get(metric_name)
            if current_metric is None:
                continue

            delta = current_metric.value - prior_metric.value
            # Degradation: current is worse (lower) than prior by more
            # than threshold fraction of the prior value.
            if prior_metric.value != 0:
                relative_change = abs(delta) / abs(prior_metric.value)
            else:
                relative_change = abs(delta)

            exceeds = delta < 0 and relative_change > threshold

            results.append(
                RegressionResult(
                    metric_name=metric_name,
                    prior_score=prior_metric.value,
                    current_score=current_metric.value,
                    delta=delta,
                    exceeds_threshold=exceeds,
                )
            )

            if exceeds:
                degradations.append(
                    f"Metric '{metric_name}' degraded: "
                    f"{prior_metric.value:.4f} → {current_metric.value:.4f} "
                    f"(delta={delta:.4f}, threshold={threshold})"
                )

        passed = len(degradations) == 0

        # Block auto-promotion if degradation exceeds threshold (Req 9.5).
        if not passed:
            # Reclassify dimension to block auto-promotion.
            existing = self._testability.get_classification(dimension)
            if existing is not None and existing.tier == "fully_automatable":
                self._testability.classify_dimension(
                    dimension=dimension,
                    tier="semi_automatable",
                    automatable_metrics=existing.automatable_metrics,
                    human_review_metrics=existing.human_review_metrics
                    if existing.human_review_metrics
                    else ["regression_review"],
                )
                logger.warning(
                    "Regression degradation detected for plugin %s in "
                    "dimension '%s'; auto-promotion blocked.",
                    plugin_id,
                    dimension,
                )

        report = TestReport(
            report_id=uuid4(),
            test_mode="regression",
            plugin_id=plugin_id,
            dimension=dimension,
            passed=passed,
            per_metric_scores=current_scores,
            violations=[],
            failure_details=degradations,
        )
        self._reports[report.report_id] = report
        return report

    # ------------------------------------------------------------------
    # get_report
    # ------------------------------------------------------------------

    def get_report(self, report_id: UUID) -> TestReport | None:
        """Return a test report by ID, or ``None`` if not found."""
        return self._reports.get(report_id)

    # ------------------------------------------------------------------
    # list_reports
    # ------------------------------------------------------------------

    def list_reports(
        self,
        plugin_id: UUID | None = None,
        dimension: str | None = None,
    ) -> list[TestReport]:
        """List test reports with optional filters."""
        results: list[TestReport] = []
        for report in self._reports.values():
            if plugin_id is not None and report.plugin_id != plugin_id:
                continue
            if dimension is not None and report.dimension != dimension:
                continue
            results.append(report)
        return results

    # ------------------------------------------------------------------
    # run_parallel  (Requirement 9.7)
    # ------------------------------------------------------------------

    def run_parallel(
        self,
        tasks: list[dict],
        max_workers: int = 4,
    ) -> list[TestReport]:
        """Execute independent plugin tests in parallel.

        Each task dict should have keys: ``"mode"`` (one of
        ``"contract_validation"``, ``"benchmark"``, ``"regression"``),
        plus the arguments required by the corresponding method.

        Returns a list of ``TestReport`` objects.
        """
        reports: list[TestReport] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            for task in tasks:
                mode = task.get("mode")
                if mode == "contract_validation":
                    futures.append(
                        executor.submit(
                            self.validate_contract,
                            plugin_id=task["plugin_id"],
                            dimension=task["dimension"],
                            contract=task["contract"],
                            plugin_endpoints=task["plugin_endpoints"],
                        )
                    )
                elif mode == "benchmark":
                    futures.append(
                        executor.submit(
                            self.run_benchmark,
                            plugin_id=task["plugin_id"],
                            dimension=task["dimension"],
                            suite_id=task["suite_id"],
                        )
                    )
                elif mode == "regression":
                    futures.append(
                        executor.submit(
                            self.run_regression,
                            plugin_id=task["plugin_id"],
                            dimension=task["dimension"],
                            prior_scores=task["prior_scores"],
                            current_scores=task["current_scores"],
                            threshold=task.get("threshold", 0.1),
                        )
                    )

            for future in as_completed(futures):
                reports.append(future.result())

        return reports

    # ------------------------------------------------------------------
    # drain_benchmark_queue  (helper for auto-queued benchmarks)
    # ------------------------------------------------------------------

    def drain_benchmark_queue(
        self,
        suite_id: UUID,
    ) -> list[TestReport]:
        """Run all auto-queued benchmarks and return their reports."""
        reports: list[TestReport] = []
        while self._benchmark_queue:
            item = self._benchmark_queue.pop(0)
            report = self.run_benchmark(
                plugin_id=item["plugin_id"],
                dimension=item["dimension"],
                suite_id=suite_id,
            )
            reports.append(report)
        return reports
