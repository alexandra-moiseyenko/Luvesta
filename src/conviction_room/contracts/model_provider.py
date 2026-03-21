"""Model/Provider dimension plugin contract (Dimension 8).

Endpoints:
- complete: accept a prompt and schema, return a structured response
- usage: return token counts and cost for a request
- models: return available models and capabilities

Requirements: 10.3
"""

from __future__ import annotations

from conviction_room.contracts.base import (
    ContractConstraints,
    ContractSchemas,
    Endpoint,
    LifecycleHooks,
    PluginContractBase,
)


def model_provider_contract(version: str = "1.0.0") -> PluginContractBase:
    """Return a PluginContractBase for the Model/Provider dimension."""
    return PluginContractBase(
        version=version,
        dimension="model_provider",
        endpoints=[
            Endpoint(
                name="complete",
                method="POST",
                path="/complete",
                request_schema={"type": "object", "description": "CompletionRequest"},
                response_schema={"type": "object", "description": "CompletionResponse"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="usage",
                method="GET",
                path="/usage/{request_id}",
                request_schema={},
                response_schema={"type": "object", "description": "UsageInfo"},
                error_schema={"type": "object"},
            ),
            Endpoint(
                name="models",
                method="GET",
                path="/models",
                request_schema={},
                response_schema={"type": "array", "description": "ModelInfo[]"},
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
            max_response_time_ms=60000,
            max_payload_bytes=1_048_576,
            required_error_codes=["INVALID_INPUT", "TIMEOUT", "INTERNAL"],
        ),
        schemas=ContractSchemas(
            request_schema={"type": "object"},
            response_schema={"type": "object"},
            error_schema={"type": "object"},
        ),
    )
