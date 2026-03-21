"""Experiment automation models."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExperimentPolicy(BaseModel):
    """Policy for automated experiment execution and promotion."""

    policy_id: UUID = Field(default_factory=uuid4)
    dimension: str
    plugin_ids: list[UUID]
    suite_id: UUID
    schedule: str
    auto_promote: bool
    significance_threshold: float
    enabled: bool
