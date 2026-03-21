"""Benchmark Orchestrator FastAPI routes.

Exposes endpoints for creating/managing experiments and benchmark runs.
Follows the thin-handler pattern — all business logic lives in the
service layer.

Requirements: 4.1, 4.4, 4.5
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from conviction_room.models.benchmark import BenchmarkRun, Experiment
from conviction_room.models.cost import CostBudget, CostRecord
from conviction_room.services.benchmark import BenchmarkOrchestratorService
from conviction_room.services.cost_governor import CostGovernorService
from conviction_room.services.golden_dataset import GoldenDatasetService

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

# Module-level service instances
_cost_governor = CostGovernorService()
_golden_dataset_service = GoldenDatasetService()
_benchmark_service = BenchmarkOrchestratorService(
    cost_governor=_cost_governor,
    golden_dataset_service=_golden_dataset_service,
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateExperimentRequest(BaseModel):
    """Request body for POST /benchmarks/experiments."""

    dimension: str
    plugin_ids: list[UUID]
    suite_id: UUID
    comparison_mode: str = "head_to_head"
    iteration_count: int = 10
    cost_budget: CostBudget


class StartRunRequest(BaseModel):
    """Request body for POST /benchmarks/runs."""

    suite_id: UUID
    plugin_id: UUID
    dimension: str
    raw_inputs: list[dict] = []
    metadata: dict = {}


# ---------------------------------------------------------------------------
# Experiment routes
# ---------------------------------------------------------------------------


@router.post("/experiments", status_code=201)
def create_experiment(body: CreateExperimentRequest) -> Experiment:
    """Create and start an experiment comparing plugins."""
    experiment = Experiment(
        dimension=body.dimension,
        plugin_ids=body.plugin_ids,
        suite_id=body.suite_id,
        comparison_mode=body.comparison_mode,
        iteration_count=body.iteration_count,
        cost_budget=body.cost_budget,
        status="pending",
    )
    created = _benchmark_service.create_experiment(experiment)
    result = _benchmark_service.run_experiment(created.experiment_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to run experiment")
    return result


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: UUID) -> Experiment:
    """Get experiment status and results."""
    exp = _benchmark_service.get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.get("/experiments")
def list_experiments(
    dimension: str | None = Query(default=None),
) -> list[Experiment]:
    """List experiments, optionally filtered by dimension."""
    all_experiments = list(_benchmark_service._experiments.values())
    if dimension is not None:
        return [e for e in all_experiments if e.dimension == dimension]
    return all_experiments


@router.post("/experiments/{exp_id}/cancel")
def cancel_experiment(exp_id: UUID) -> Experiment:
    """Cancel a running experiment."""
    exp = _benchmark_service.cancel_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


# ---------------------------------------------------------------------------
# Run routes
# ---------------------------------------------------------------------------


@router.post("/runs", status_code=201)
def start_run(body: StartRunRequest) -> BenchmarkRun:
    """Start a single benchmark run."""
    run = BenchmarkRun(
        suite_id=body.suite_id,
        plugin_id=body.plugin_id,
        dimension=body.dimension,
        status="pending",
        raw_inputs=body.raw_inputs,
        cost_consumed=CostRecord(
            dimension=body.dimension,
            plugin_id=body.plugin_id,
            token_count=0,
            api_calls=0,
            dollar_cost=0.0,
            is_estimated=True,
        ),
        metadata=body.metadata,
    )
    return _benchmark_service.run_benchmark(run)


@router.get("/runs/{run_id}")
def get_run(run_id: UUID) -> BenchmarkRun:
    """Get benchmark run results."""
    run = _benchmark_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
