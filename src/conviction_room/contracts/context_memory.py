"""Context/Memory dimension plugin contract (Dimension 11).

Endpoints:
- store: persist a context artifact
- retrieve: fetch relevant context for a query
- summarize: compress context to a target size

Requirements: 10.4
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)


def context_memory_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Context/Memory dimension."""
    return PluginContractBase(
        version=version,
        dimension="context_memory",
        endpoints=[
            Endpoint(
                name="store",
                method="POST",
                path="/store",
                request_schema={"type": "object", "description": "ContextArtifact"},
                response_schema={"type": "object", "description": "StoreResult"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="retrieve",
                method="POST",
                path="/retrieve",
                request_schema={"type": "object", "description": "RetrieveQuery"},
                response_schema={"type": "object", "description": "ContextResult"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="summarize",
                method="POST",
                path="/summarize",
                request_schema={"type": "object", "description": "SummarizeRequest"},
                response_schema={"type": "object", "description": "SummarizeResult"},
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
