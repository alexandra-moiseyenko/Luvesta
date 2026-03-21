"""Test Harness FastAPI routes.

Exposes endpoints for contract validation, benchmark execution,
regression testing, and test report retrieval.  Thin route handlers
that delegate to TestHarnessService.

Requirements: 9.1, 9.4
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from conviction_room.contracts.base import PluginContractBase
from conviction_room.models.benchmark import EvaluationMetric
from conviction_room.models.test_report import TestReport
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.golden_dataset import GoldenDatasetService
from conviction_room.services.registry import PluginRegistryService
from conviction_room.services.test_harness import TestHarnessService
from conviction_room.services.testability import TestabilityService

router = APIRouter(prefix="/test-harness", tags=["test-harness"])

# Module-level service instances
_registry = PluginRegistryService()
_cost_governor = CostGovernorService()
_golden_dataset_service = GoldenDatasetService()
_benchmark_service = BenchmarkOrchestratorService(
    cost_governor=_cost_governor,
    golden_dataset_service=_golden_dataset_service,
)
_testability = TestabilityService()
_harness = TestHarnessService(
    registry=_registry,
    cost_governor=_cost_governor,
    benchmark_orchestrator=_benchmark_service,
    testability=_testability,
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ValidateContractRequest(BaseModel):
    """Request body for POST /test-harness/validate."""

    plugin_id: UUID
    dimension: str
    contract: PluginContractBase
    plugin_endpoints: list[dict]


class RunBenchmarkRequest(BaseModel):
    """Request body for POST /test-harness/benchmark."""

    plugin_id: UUID
    dimension: str
    suite_id: UUID


class RunRegressionRequest(BaseModel):
    """Request body for POST /test-harness/regression."""

    plugin_id: UUID
    dimension: str
    prior_scores: list[EvaluationMetric]
    current_scores: list[EvaluationMetric]
    threshold: float = 0.1


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/validate", status_code=201)
def validate_contract(body: ValidateContractRequest) -> TestReport:
    """Run contract validation for a plugin.

    Automatically queues a benchmark if validation passes (Req 9.3).
    """
    return _harness.validate_contract(
        plugin_id=body.plugin_id,
        dimension=body.dimension,
        contract=body.contract,
        plugin_endpoints=body.plugin_endpoints,
    )


@router.post("/benchmark", status_code=201)
def run_benchmark(body: RunBenchmarkRequest) -> TestReport:
    """Run a benchmark suite against a plugin."""
    return _harness.run_benchmark(
        plugin_id=body.plugin_id,
        dimension=body.dimension,
        suite_id=body.suite_id,
    )


@router.post("/regression", status_code=201)
def run_regression(body: RunRegressionRequest) -> TestReport:
    """Run regression comparison of prior vs current scores."""
    return _harness.run_regression(
        plugin_id=body.plugin_id,
        dimension=body.dimension,
        prior_scores=body.prior_scores,
        current_scores=body.current_scores,
        threshold=body.threshold,
    )


@router.get("/reports")
def list_reports(
    plugin_id: UUID | None = Query(default=None),
    dimension: str | None = Query(default=None),
) -> list[TestReport]:
    """List test reports with optional filters."""
    return _harness.list_reports(plugin_id=plugin_id, dimension=dimension)


@router.get("/reports/{report_id}")
def get_report(report_id: UUID) -> TestReport:
    """Get a single test report by ID."""
    report = _harness.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
