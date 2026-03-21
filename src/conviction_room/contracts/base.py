"""Base plugin contract definitions for Conviction Room.

Every dimension's contract extends PluginContractBase, which defines the
common structure: versioned interface, endpoints, health check, lifecycle
hooks, constraints, and schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Endpoint(BaseModel):
    """An OpenAPI-compatible endpoint definition."""

    name: str
    method: Literal["GET", "POST", "PUT", "DELETE"]
    path: str
    request_schema: dict = Field(default_factory=dict)
    response_schema: dict = Field(default_factory=dict)
    error_schema: dict = Field(default_factory=dict)


class LifecycleHooks(BaseModel):
    """Lifecycle hooks that a plugin may support."""

    init: bool = False
    warmup: bool = False
    shutdown: bool = False
    readiness: bool = False


class ContractConstraints(BaseModel):
    """Operational constraints a plugin must respect."""

    max_response_time_ms: int = Field(gt=0)
    max_payload_bytes: int = Field(gt=0)
    required_error_codes: list[str] = Field(default_factory=list)


class ContractSchemas(BaseModel):
    """Top-level schemas for the contract."""

    request_schema: dict = Field(default_factory=dict)
    response_schema: dict = Field(default_factory=dict)
    error_schema: dict = Field(default_factory=dict)


class PluginContractBase(BaseModel):
    """Base contract that all dimension plugin contracts inherit from.

    Defines the common structure every plugin must satisfy:
    - Versioned interface (semver)
    - Required endpoints
    - Health-check endpoint
    - Lifecycle hooks
    - Operational constraints
    - Request/response/error schemas
    """

    version: str
    dimension: str
    endpoints: list[Endpoint]
    health_check: Endpoint = Field(
        default_factory=lambda: Endpoint(
            name="health",
            method="GET",
            path="/health",
            request_schema={},
            response_schema={},
            error_schema={},
        )
    )
    lifecycle_hooks: LifecycleHooks = Field(default_factory=LifecycleHooks)
    constraints: ContractConstraints
    schemas: ContractSchemas = Field(default_factory=ContractSchemas)
