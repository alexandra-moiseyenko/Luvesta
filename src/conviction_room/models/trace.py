"""Observability and trace models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TraceEvent(BaseModel):
    """Structured trace event for a plugin invocation."""

    trace_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dimension: str
    plugin_id: UUID
    input_hash: str
    output_hash: str
    latency_ms: float
    token_usage: int
    cost_usd: float
    success: bool
    error_context: dict | None = None
    experiment_id: UUID | None = None
    benchmark_run_id: UUID | None = None


class AggregateMetrics(BaseModel):
    """Aggregate metrics for a plugin over a time window."""

    plugin_id: UUID
    dimension: str
    time_window: str
    success_rate: float
    mean_latency_ms: float
    p95_latency_ms: float
    mean_cost_usd: float
    total_invocations: int
