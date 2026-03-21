"""Plugin-related data models."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PluginMetadata(BaseModel):
    """Metadata for a registered plugin."""

    plugin_id: UUID = Field(default_factory=uuid4)
    dimension: str
    name: str
    version: str
    contract_version: str
    status: Literal["active", "inactive", "deprecated"]
    endpoint_base_url: str
    config: dict[str, Any] = Field(default_factory=dict)
    health_status: Literal["healthy", "degraded", "unhealthy", "unknown"] = "unknown"
    last_health_check: datetime | None = None
    latest_benchmark_score: float | None = None
    registered_at: datetime = Field(default_factory=datetime.utcnow)
    validated_at: datetime | None = None
    contract_violations: list[str] = Field(default_factory=list)


class PluginError(BaseModel):
    """Structured error from plugin operations."""

    error_code: str
    message: str
    dimension: str | None = None
    plugin_id: UUID | None = None
    details: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: UUID | None = None
