"""Cost governance data models."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class CostBudget(BaseModel):
    """Budget ceiling for cost governance."""

    scope: Literal["benchmark_run", "dimension_period", "global_period"]
    dimension: str | None = None
    period: Literal["daily", "weekly"] | None = None
    max_tokens: int
    max_api_calls: int
    max_dollar_cost: float


class CostRecord(BaseModel):
    """A single cost ledger entry."""

    record_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dimension: str
    plugin_id: UUID
    token_count: int
    api_calls: int
    dollar_cost: float
    is_estimated: bool


class CostSummary(BaseModel):
    """Aggregated cost summary with breakdowns."""

    scope: str
    current_spend: float
    remaining_budget: float
    projected_spend: float
    breakdown_by_dimension: dict[str, float] = Field(default_factory=dict)
    breakdown_by_plugin: dict[str, float] = Field(default_factory=dict)
