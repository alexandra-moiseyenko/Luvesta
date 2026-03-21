"""Test report and regression result models."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from conviction_room.models.benchmark import EvaluationMetric


class TestReport(BaseModel):
    """Machine-readable test report from the test harness."""

    report_id: UUID = Field(default_factory=uuid4)
    test_mode: Literal["contract_validation", "benchmark", "regression"]
    plugin_id: UUID
    dimension: str
    passed: bool
    per_metric_scores: list[EvaluationMetric] | None = None
    violations: list[str] = Field(default_factory=list)
    failure_details: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RegressionResult(BaseModel):
    """Result of a regression comparison for a single metric."""

    metric_name: str
    prior_score: float
    current_score: float
    delta: float
    exceeds_threshold: bool
