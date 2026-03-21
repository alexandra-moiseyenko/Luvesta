"""Testability classification models."""

from typing import Literal

from pydantic import BaseModel, Field


class TestabilityClassification(BaseModel):
    """AI-testability classification for a dimension."""

    dimension: str
    tier: Literal["fully_automatable", "semi_automatable", "human_required"]
    automatable_metrics: list[str] = Field(default_factory=list)
    human_review_metrics: list[str] = Field(default_factory=list)
