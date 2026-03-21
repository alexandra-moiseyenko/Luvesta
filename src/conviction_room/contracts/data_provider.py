"""Data Provider Adapter dimension plugin contract (Dimension 10b).

Endpoints:
- query: search for data by entity/date/type
- fetch: retrieve a specific document or data point
- health: provider availability and rate-limit status

Requirements: 8.1
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)


def data_provider_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Data Provider Adapter dimension."""
    return PluginContractBase(
        version=version,
        dimension="data_provider",
        endpoints=[
            Endpoint(
                name="query",
                method="POST",
                path="/query",
                request_schema={"type": "object", "description": "DataQuery"},
                response_schema={"type": "array", "description": "DataResult[]"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="fetch",
                method="GET",
                path="/fetch/{ref}",
                request_schema={},
                response_schema={"type": "object", "description": "DataDocument"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="provider_health",
                method="GET",
                path="/health",
                request_schema={},
                response_schema={"type": "object", "description": "ProviderHealth"},
                error_schema={"type": "object"},
            ),
        ],
        health_check=Endpoint(
            name="health",
            method="GET",
            path="/health",
            request_schema={},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
        lifecycle_hooks=LifecycleHooks(
            init=True, warmup=True, shutdown=True, readiness=True,
        ),
        constraints=ContractConstraints(
            max_response_time_ms=10000,
            max_payload_bytes=5_242_880,
            required_error_codes=["INVALID_INPUT", "TIMEOUT", "INTERNAL"],
        ),
        schemas=ContractSchemas(
            request_schema={"type": "object"},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
    )
