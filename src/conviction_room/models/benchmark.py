"""Benchmark and experiment data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from conviction_room.models.cost import CostBudget, CostRecord


class EvaluationMetric(BaseModel):
    """A single evaluation metric result."""

    name: str
    category: Literal["quality", "performance", "cost"]
    value: float
    unit: str
    is_deterministic: bool


class BenchmarkSuite(BaseModel):
    """Definition of a benchmark suite for a dimension."""

    suite_id: UUID = Field(default_factory=uuid4)
    dimension: str
    name: str
    description: str
    golden_dataset_id: UUID
    metrics: list[str] = Field(default_factory=list)
    iteration_count: int


class BenchmarkRun(BaseModel):
    """A single benchmark run against a plugin."""

    run_id: UUID = Field(default_factory=uuid4)
    suite_id: UUID
    plugin_id: UUID
    dimension: str
    status: Literal["pending", "running", "completed", "failed", "budget_exceeded"]
    iterations_completed: int = 0
    scores: list[EvaluationMetric] = Field(default_factory=list)
    raw_inputs: list[dict] = Field(default_factory=list)
    raw_outputs: list[dict] = Field(default_factory=list)
    cost_consumed: CostRecord
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PluginScore(BaseModel):
    """Score for a single plugin in an experiment."""

    plugin_id: UUID
    composite_score: float
    per_metric_scores: list[EvaluationMetric] = Field(default_factory=list)
    rank: int


class ExperimentResults(BaseModel):
    """Results of a completed experiment."""

    ranked_plugins: list[PluginScore] = Field(default_factory=list)
    comparison_report: dict[str, Any] = Field(default_factory=dict)
    confidence_intervals: dict[str, tuple[float, float]] | None = None


class Experiment(BaseModel):
    """An experiment comparing plugins within a dimension."""

    experiment_id: UUID = Field(default_factory=uuid4)
    dimension: str
    plugin_ids: list[UUID]
    suite_id: UUID
    comparison_mode: Literal["head_to_head", "tournament", "regression"]
    iteration_count: int
    cost_budget: CostBudget
    status: Literal["pending", "running", "completed", "failed", "budget_exceeded"]
    runs: list[UUID] = Field(default_factory=list)
    results: ExperimentResults | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
