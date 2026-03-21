"""Golden dataset models."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class GoldenDatasetEntry(BaseModel):
    """A single entry in a golden dataset."""

    entry_id: UUID = Field(default_factory=uuid4)
    input_payload: dict
    expected_output: dict | None = None
    quality_bounds: dict | None = None
    scenario_description: str
    tags: list[str] = Field(default_factory=list)


class GoldenDataset(BaseModel):
    """A versioned golden dataset for a dimension."""

    dataset_id: UUID = Field(default_factory=uuid4)
    dimension: str
    version: int
    entries: list[GoldenDatasetEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    prior_version_id: UUID | None = None
