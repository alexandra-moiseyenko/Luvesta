"""Dimension dependency graph models."""

from typing import Literal

from pydantic import BaseModel, Field


class DimensionNode(BaseModel):
    """A single node in the dimension dependency graph."""

    dimension: str
    tier: Literal["foundation", "mid-tier", "leaf"]
    depends_on: list[str] = Field(default_factory=list)


class DimensionGraph(BaseModel):
    """The full dimension dependency DAG."""

    nodes: list[DimensionNode] = Field(default_factory=list)
